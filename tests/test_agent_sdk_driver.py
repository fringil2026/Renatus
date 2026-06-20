"""Structural tests for AgentSDKDriver — runnable WITHOUT the Claude Agent SDK installed.

These prove the wiring: the driver conforms to the BuildDriver interface, constructs without
importing the SDK, bridges async→sync, and raises a clear, actionable error when the SDK is absent.
They intentionally do NOT run a live build (that needs the SDK + credentials + spend) — that path is
the gated smoke test in ``tests/smoke_agent_sdk.py``.

    python3 tests/test_agent_sdk_driver.py
    pytest tests/test_agent_sdk_driver.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import AgentSDKDriver, BuildDriver  # noqa: E402
from engine.agent_sdk_driver import _run_coro_sync  # noqa: E402

_SDK_INSTALLED = importlib.util.find_spec("claude_agent_sdk") is not None


def test_is_a_build_driver() -> None:
    assert issubclass(AgentSDKDriver, BuildDriver)


def test_constructs_without_sdk() -> None:
    # Construction must not import the SDK (lazy import happens only in run()).
    d = AgentSDKDriver("/tmp/workspace", model="claude-fable-5", max_turns=40)
    assert d._cwd == "/tmp/workspace"
    assert d._permission_mode == "bypassPermissions"  # headless default


def test_async_to_sync_bridge() -> None:
    async def _coro() -> int:
        return 7

    assert _run_coro_sync(_coro()) == 7


def test_coroutine_error_propagates_unchanged() -> None:
    async def _boom() -> None:
        raise ValueError("kaboom")

    try:
        _run_coro_sync(_boom())
    except ValueError as e:
        assert "kaboom" in str(e)
    else:
        raise AssertionError("expected the coroutine's ValueError to propagate")


def test_missing_sdk_raises_actionable_error() -> None:
    if _SDK_INSTALLED:
        print("  (skip test_missing_sdk_raises_actionable_error — SDK is installed)")
        return
    d = AgentSDKDriver(_REPO)
    try:
        d.run("Diagnose site https://example.com", slug="x")
    except RuntimeError as e:
        assert "claude-agent-sdk" in str(e)  # tells the operator how to fix it
    else:
        raise AssertionError("expected RuntimeError when the SDK is not installed")


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    total = len(tests)
    print(f"\n{total - failed}/{total} passed" + ("" if not failed else f", {failed} FAILED"))
    print(f"(Claude Agent SDK installed: {_SDK_INSTALLED})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
