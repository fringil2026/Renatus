"""``BuildDriver`` backed by the Claude Agent SDK (``claude-agent-sdk``).

This is the production successor to ``LocalClaudeDriver``: instead of shelling out to the ``claude``
CLI, it drives Claude Code programmatically via the Agent SDK's ``query()`` API. Same job — run a
CLAUDE.md command phrase as a headless agent against a project workspace — but as an in-process call
with structured results (success, cost, token usage) instead of scraped stdout.

In the target architecture this driver runs **inside a per-tenant sandbox** (PRODUCT-PLAN §3.4): the
sandbox is the security boundary, the workspace is the tenant's checked-out project, and the SDK
agent executes the skills + CLAUDE.md contract there. Locally it can run against the repo root, the
same way ``claude -p`` does today.

Why a separate spike (PRODUCT-PLAN Phase 0 / Phase 2): it isolates the riskiest unknown — *can Claude
reliably drive a full build headlessly?* — from the orthogonal question of *where it runs* (the
sandbox vendor). This file is decision-independent: it needs only the SDK, not Fly/E2B/etc.

The SDK is imported lazily so the rest of the engine never hard-depends on it (it isn't needed for
the filesystem store, the orchestration logic, or the tests).

Bindings confirmed against anthropics/claude-agent-sdk-python:
  query(prompt=..., options=ClaudeAgentOptions(...)) -> AsyncIterator[Message]
  ClaudeAgentOptions(cwd, model, allowed_tools, permission_mode, system_prompt, max_turns, ...)
  AssistantMessage(content=[ContentBlock]); TextBlock(text)
  ResultMessage(is_error, total_cost_usd, usage, errors, api_error_status, result, ...)
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from .driver import AgentResult, BuildDriver

_DEFAULT_TAIL = 60


def _run_coro_sync(coro):
    """Run an async coroutine from sync code, even if a loop is already running.

    The orchestration layer is synchronous and normally has no running loop, so ``asyncio.run`` is
    the fast path. If we *are* inside a running loop (e.g. a notebook, an async server), fall back to
    a dedicated thread with its own loop so we don't raise ``RuntimeError``.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # Only the "loop already running" RuntimeError warrants the thread fallback; any other
        # RuntimeError (e.g. the coroutine itself raised) must propagate unchanged.
        if "running event loop" not in str(e):
            raise
        result: dict = {}

        def _worker() -> None:
            loop = asyncio.new_event_loop()
            try:
                result["value"] = loop.run_until_complete(coro)
            except BaseException as exc:  # noqa: BLE001
                result["error"] = exc
            finally:
                loop.close()

        t = threading.Thread(target=_worker)
        t.start()
        t.join()
        if "error" in result:
            raise result["error"]
        return result["value"]


class AgentSDKDriver(BuildDriver):
    """Drive a CLAUDE.md command as a headless Claude Code agent via the Agent SDK.

    Parameters
    ----------
    cwd:
        The agent's working directory — the project workspace (repo root locally; the tenant's
        checked-out project in a sandbox). CLAUDE.md + the skills are loaded from here, same as today.
    model:
        Model id, or ``None`` to use the CLI's configured default (faithful to today's ``claude -p``).
        Pin per ADR-0001 §6 when you want a specific tier.
    permission_mode:
        Default ``"bypassPermissions"`` — a headless build needs to edit files AND run bash
        (npm install, python skill scripts, wrangler) with no human to approve each call, and **the
        sandbox is the security boundary** (PRODUCT-PLAN §3.4). Tighten to ``"acceptEdits"`` +
        ``allowed_tools`` when running outside a sandbox.
    allowed_tools / system_prompt / max_turns:
        Optional passthroughs to ``ClaudeAgentOptions``. Left unset by default so CLAUDE.md and the
        project settings load naturally.
    """

    def __init__(
        self,
        cwd: str | Path,
        *,
        model: str | None = None,
        permission_mode: str = "bypassPermissions",
        allowed_tools: list[str] | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        tail_lines: int = _DEFAULT_TAIL,
    ) -> None:
        self._cwd = str(cwd)
        self._model = model
        self._permission_mode = permission_mode
        self._allowed_tools = allowed_tools
        self._system_prompt = system_prompt
        self._max_turns = max_turns
        self._tail_lines = tail_lines

    # -- BuildDriver ------------------------------------------------------- #
    def run(self, command: str, *, slug: str) -> AgentResult:
        return _run_coro_sync(self._run_async(command))

    # -- async core -------------------------------------------------------- #
    async def _run_async(self, command: str) -> AgentResult:
        try:
            from claude_agent_sdk import (  # type: ignore
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                TextBlock,
                query,
            )
        except ImportError as e:  # pragma: no cover - exercised only without the SDK installed
            raise RuntimeError(
                "AgentSDKDriver requires the Claude Agent SDK. Install it with "
                "`pip install claude-agent-sdk` (and ensure the `claude` CLI it wraps is on PATH)."
            ) from e

        opts: dict = {"cwd": self._cwd, "permission_mode": self._permission_mode}
        if self._model is not None:
            opts["model"] = self._model
        if self._allowed_tools is not None:
            opts["allowed_tools"] = self._allowed_tools
        if self._system_prompt is not None:
            opts["system_prompt"] = self._system_prompt
        if self._max_turns is not None:
            opts["max_turns"] = self._max_turns
        options = ClaudeAgentOptions(**opts)

        tail: list[str] = []

        def _push(text: str) -> None:
            for line in text.splitlines():
                line = line.rstrip()
                if line:
                    tail.append(line)
                    del tail[: -self._tail_lines]

        result_msg = None
        async for message in query(prompt=command, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        _push(block.text)
            elif isinstance(message, ResultMessage):
                result_msg = message

        if result_msg is None:
            # The stream ended without a terminal result — treat as a failure, not a hang.
            return AgentResult(ok=False, exit_code=1, tail=[*tail, "no ResultMessage received"])

        if result_msg.is_error:
            for err in (result_msg.errors or [])[-5:]:
                _push(str(err))
        exit_code = result_msg.api_error_status or (0 if not result_msg.is_error else 1)
        return AgentResult(
            ok=not result_msg.is_error,
            exit_code=exit_code,
            tail=tail,
            cost_usd=result_msg.total_cost_usd,
            usage=result_msg.usage,
        )
