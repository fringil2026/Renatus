"""LIVE smoke test for AgentSDKDriver — proves Claude can actually be driven via the Agent SDK.

This one costs real tokens and needs the SDK + a working `claude` login, so it is **opt-in only**:

    pip install claude-agent-sdk          # and have the `claude` CLI authenticated
    AGENT_SDK_SMOKE=1 python3 tests/smoke_agent_sdk.py

Without ``AGENT_SDK_SMOKE=1`` (or without the SDK) it skips and exits 0 — so CI never burns spend.

It runs a trivial one-turn agent (no build, no file writes) in a throwaway temp dir and checks that
a successful AgentResult with the expected token comes back. This is the Phase 0 milestone probe:
"can Claude be driven headlessly via the SDK at all?" — deliberately the cheapest possible proof,
separate from a full build (which the orchestration layer drives once this is green).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import AgentSDKDriver  # noqa: E402


def main() -> int:
    if os.environ.get("AGENT_SDK_SMOKE") != "1":
        print("SKIP: set AGENT_SDK_SMOKE=1 to run the live Agent SDK smoke test (it spends tokens).")
        return 0
    if importlib.util.find_spec("claude_agent_sdk") is None:
        print("SKIP: claude-agent-sdk is not installed (`pip install claude-agent-sdk`).")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        driver = AgentSDKDriver(tmp, permission_mode="bypassPermissions", max_turns=2)
        # A read-only, single-turn prompt — no build, no spend beyond one tiny turn.
        result = driver.run(
            "Reply with exactly the single word PONG and nothing else. Do not use any tools.",
            slug="smoke",
        )

    print(f"ok={result.ok} exit={result.exit_code} cost_usd={result.cost_usd}")
    print("tail:")
    for line in result.tail[-10:]:
        print(f"  {line}")

    if not result.ok:
        print("\nFAIL: driver returned an error result")
        return 1
    if not any("PONG" in line for line in result.tail):
        print("\nFAIL: expected 'PONG' in the agent's output")
        return 1
    print("\nPASS: Claude was driven headlessly via the Agent SDK and returned the expected output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
