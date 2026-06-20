"""The build-execution seam.

The studio's heavy work — scrape, extract, assemble Astro, run the parity loop — is performed by a
headless Claude agent that reads the CLAUDE.md contract and the skills, triggered by a command phrase
(today: ``claude -p "Assemble prototype for <slug>"`` from the repo root, see studio.py ``run_advance``).
``BuildDriver`` abstracts that execution so orchestration is deterministic and unit-testable:

* ``LocalClaudeDriver`` — shells out to the ``claude`` CLI, exactly like ``studio.py`` today.
* ``MockBuildDriver`` — scripted results for tests; records the commands it was asked to run.
* the production driver (later) — drives the Claude Agent SDK inside a per-tenant sandbox.

The transient-vs-terminal classifier is ported verbatim from ``studio.py`` so the engine treats
budget/rate/overload failures as *resumable*, not real (SYSTEM.md §3d).
"""

from __future__ import annotations

import subprocess
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Ported verbatim from studio.py — budget/rate/overload signatures = transient (resumable).
TRANSIENT_MARKERS = (
    "spend limit", "usage limit", "rate limit", "rate_limit", "overloaded", "overload",
    "monthly spend", "quota", "too many requests", " 429", " 503", " 502", " 529", "exceeded",
)


def is_transient_failure(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in TRANSIENT_MARKERS)


@dataclass(slots=True)
class AgentResult:
    """Outcome of one agent run."""

    ok: bool
    exit_code: int = 0
    tail: list[str] = field(default_factory=list)  # last ~60 output lines
    # Populated by drivers that surface structured telemetry (e.g. AgentSDKDriver); used for
    # per-build metering (PRODUCT-PLAN §3.2/§9). Subprocess drivers leave these None.
    cost_usd: float | None = None
    usage: dict | None = None

    @property
    def transient(self) -> bool:
        """A failure that should PAUSE (resumable), not fail terminally."""
        if self.ok:
            return False
        probe = " / ".join(self.tail[-6:])[:400]
        return is_transient_failure(probe)

    @property
    def tail_text(self) -> str:
        return (" / ".join(self.tail[-6:]))[:400]


class BuildDriver(ABC):
    """Runs a CLAUDE.md command phrase as a headless agent against a project workspace."""

    @abstractmethod
    def run(self, command: str, *, slug: str) -> AgentResult:
        """Execute ``command`` (e.g. ``"Assemble prototype for acme"``) and return the result."""


class LocalClaudeDriver(BuildDriver):
    """Shells out to the ``claude`` CLI from a fixed working directory (the studio.py model).

    A global semaphore paces concurrent spawns so a burst can never blow the API budget
    (studio.py ``CLAUDE_SEM`` / ``MAX_CLAUDE_JOBS``).
    """

    def __init__(
        self,
        cwd: str,
        *,
        claude_bin: str = "claude",
        max_jobs: int = 3,
        tail_lines: int = 60,
        semaphore: threading.Semaphore | None = None,
    ) -> None:
        self._cwd = cwd
        self._bin = claude_bin
        self._tail_lines = tail_lines
        self._sem = semaphore or threading.Semaphore(max_jobs)

    def run(self, command: str, *, slug: str) -> AgentResult:
        tail: list[str] = []
        with self._sem:
            try:
                proc = subprocess.Popen(
                    [self._bin, "-p", command],
                    cwd=self._cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except OSError as e:
                return AgentResult(ok=False, exit_code=127, tail=[f"failed to start: {e}"])
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    tail.append(line)
                    del tail[: -self._tail_lines]
            rc = proc.wait()
        return AgentResult(ok=(rc == 0), exit_code=rc, tail=tail)


class MockBuildDriver(BuildDriver):
    """Test double. Returns scripted results by command-prefix and records every call."""

    def __init__(self, default: AgentResult | None = None) -> None:
        self.calls: list[str] = []
        self._default = default or AgentResult(ok=True)
        self._scripted: list[tuple[str, AgentResult]] = []

    def when(self, command_contains: str, result: AgentResult) -> "MockBuildDriver":
        self._scripted.append((command_contains, result))
        return self

    def run(self, command: str, *, slug: str) -> AgentResult:
        self.calls.append(command)
        for needle, result in self._scripted:
            if needle in command:
                return result
        return self._default
