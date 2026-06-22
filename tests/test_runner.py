"""Tests for the durable-workflow seam: Run/RunStore + InlineRunner/ThreadRunner.

No network, no Claude. Jobs are plain callables returning a CommandOutcome, so run-state transitions,
persistence, failure capture, and background execution are all deterministic.

    python3 tests/test_runner.py
    pytest tests/test_runner.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    CommandOutcome,
    FilesystemRunStore,
    InlineRunner,
    InMemoryRunStore,
    Run,
    RunStatus,
    ThreadRunner,
)


def _ok() -> CommandOutcome:
    return CommandOutcome(ok=True, preview_url="https://ws-acme.pages.dev", message="ok")


def _paused() -> CommandOutcome:
    return CommandOutcome(ok=False, paused=True, message="paused")


# --------------------------------------------------------------------------- #
def test_inline_success() -> None:
    runner = InlineRunner(InMemoryRunStore(), now_fn=lambda: "t")
    run = runner.submit("acme", "assemble", _ok)
    assert run.status is RunStatus.SUCCEEDED  # terminal on return
    assert run.result["ok"] is True and run.result["preview_url"].endswith("pages.dev")
    assert runner.runs.get(run.id).status is RunStatus.SUCCEEDED
    assert [r.id for r in runner.runs.list("acme")] == [run.id]
    assert runner.runs.list("other") == []


def test_inline_paused() -> None:
    runner = InlineRunner(InMemoryRunStore(), now_fn=lambda: "t")
    run = runner.submit("acme", "assemble", _paused)
    assert run.status is RunStatus.PAUSED


def test_inline_failure_captured() -> None:
    def boom() -> CommandOutcome:
        raise RuntimeError("kaboom")

    runner = InlineRunner(InMemoryRunStore(), now_fn=lambda: "t")
    run = runner.submit("acme", "assemble", boom)
    assert run.status is RunStatus.FAILED
    assert "kaboom" in run.error  # the worker captured the error instead of crashing


def test_thread_runner_runs_in_background() -> None:
    runner = ThreadRunner(InMemoryRunStore(), now_fn=lambda: "t")
    run = runner.submit("acme", "diagnostic", _ok)
    assert run.id  # returned immediately (queued/running snapshot)
    runner.wait(timeout=10)
    assert runner.runs.get(run.id).status is RunStatus.SUCCEEDED


def test_filesystem_run_store_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = FilesystemRunStore(Path(tmp))
        store.create(Run(id="run_abc", slug="acme", kind="assemble", status=RunStatus.QUEUED, created="t1"))
        store.save(Run(id="run_abc", slug="acme", kind="assemble", status=RunStatus.SUCCEEDED, created="t1"))
        got = store.get("run_abc")
        assert got is not None and got.status is RunStatus.SUCCEEDED
        assert [r.id for r in store.list("acme")] == ["run_abc"]
        assert [r.id for r in store.list()] == ["run_abc"]  # all-projects scan


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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
