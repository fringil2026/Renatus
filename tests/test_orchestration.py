"""Tests for the engine's headless command entrypoints + stage machine.

Uses a temp FilesystemProjectStore + MockBuildDriver + MockPublisher, so the deterministic
orchestration (gates, publish-always, failure policy, reporting) is exercised without running Claude
or wrangler. Never touches real client data.

    python3 tests/test_orchestration.py     # standalone
    pytest tests/test_orchestration.py       # also works
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    AgentResult,
    Command,
    EditState,
    FilesystemProjectStore,
    MockBuildDriver,
    MockPublisher,
    PreconditionError,
    Project,
    Stage,
    assemble_prototype,
    available_commands,
    can_transition,
    command_available,
    process_edits,
    run_baseline,
    run_diagnostic,
    run_finish,
    run_intake_pack,
)


def _store() -> tuple[FilesystemProjectStore, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    return FilesystemProjectStore(Path(tmp.name)), tmp


def _project(store: FilesystemProjectStore, stage: Stage) -> None:
    store.create_project(
        Project(slug="acme", name="Acme", domain="https://acme.example", stage=stage)
    )


# --------------------------------------------------------------------------- #
# Stage machine
# --------------------------------------------------------------------------- #
def test_stage_machine_transitions() -> None:
    assert can_transition(Stage.BASELINE_READY, Stage.PROTOTYPE)
    assert can_transition(Stage.PROTOTYPE, Stage.AWAITING_OWNER)
    assert not can_transition(Stage.QUEUED, Stage.FINAL)
    assert can_transition(Stage.FINAL, Stage.FINAL)  # no-op allowed


def test_command_availability() -> None:
    assert command_available(Command.ASSEMBLE, Stage.BASELINE_READY)
    assert not command_available(Command.ASSEMBLE, Stage.QUEUED)
    assert command_available(Command.PROCESS_EDITS, Stage.PROTOTYPE)
    assert not command_available(Command.PROCESS_EDITS, Stage.BASELINE_READY)
    assert command_available(Command.DIAGNOSE, Stage.QUEUED)  # read-only, anywhere
    assert Command.ASSEMBLE in available_commands(Stage.BASELINE_READY)


# --------------------------------------------------------------------------- #
# assemble_prototype
# --------------------------------------------------------------------------- #
def test_assemble_happy_path() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.BASELINE_READY)
        driver, pub = MockBuildDriver(), MockPublisher()
        out = assemble_prototype(store, driver, "acme", publisher=pub, now="2026-06-19-2100")
        assert out.ok and not out.paused
        assert out.preview_url == "https://ws-acme.pages.dev"
        assert driver.calls == ["Assemble prototype for acme"]
        p = store.get_project("acme")
        assert p.stage is Stage.AWAITING_OWNER          # prototype -> awaiting-owner
        assert p.preview_url == "https://ws-acme.pages.dev"
        assert not p.preview_stale
        assert any(r.kind == "assemble" for r in store.list_reports("acme"))
    finally:
        tmp.cleanup()


def test_assemble_wrong_stage_refused() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.QUEUED)
        try:
            assemble_prototype(store, MockBuildDriver(), "acme", publisher=MockPublisher(), now="t")
        except PreconditionError:
            pass
        else:
            raise AssertionError("expected PreconditionError assembling at stage=queued")
    finally:
        tmp.cleanup()


def test_assemble_blocked_by_open_concept_decision() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.BASELINE_READY)
        store.create_decision("acme", "design concept", "question: which board?\n")  # OPEN
        try:
            assemble_prototype(store, MockBuildDriver(), "acme", publisher=MockPublisher(), now="t")
        except PreconditionError as e:
            assert "concept" in str(e).lower()
        else:
            raise AssertionError("expected PreconditionError with an open concept decision")
        # once resolved, it proceeds
        store.resolve_decision("acme", 1, choice="B")
        out = assemble_prototype(
            store, MockBuildDriver(), "acme", publisher=MockPublisher(), now="2026-06-19-2200"
        )
        assert out.ok
    finally:
        tmp.cleanup()


def test_assemble_transient_pauses() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.BASELINE_READY)
        driver = MockBuildDriver(default=AgentResult(ok=False, exit_code=1, tail=["error: rate limit exceeded"]))
        out = assemble_prototype(store, driver, "acme", publisher=MockPublisher(), now="t")
        assert not out.ok and out.paused
        p = store.get_project("acme")
        assert p.extra.get("paused") is True
        assert p.extra.get("paused_kind") == "assemble"
        assert p.stage is Stage.BASELINE_READY  # stage unchanged on pause
    finally:
        tmp.cleanup()


def test_assemble_hard_failure_flags_not_stage() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.BASELINE_READY)
        driver = MockBuildDriver(default=AgentResult(ok=False, exit_code=1, tail=["TypeError: boom"]))
        out = assemble_prototype(store, driver, "acme", publisher=MockPublisher(), now="t")
        assert not out.ok and not out.paused
        p = store.get_project("acme")
        assert p.extra.get("advance_failed") is True
        assert p.stage is Stage.BASELINE_READY  # hard failure leaves stage for a rerun
    finally:
        tmp.cleanup()


def test_assemble_deploy_failure_marks_stale() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.BASELINE_READY)
        out = assemble_prototype(
            store, MockBuildDriver(), "acme", publisher=MockPublisher(fail=True), now="2026-06-19-2100"
        )
        assert out.ok and out.preview_url is None  # build ok, deploy failed
        p = store.get_project("acme")
        assert p.preview_stale is True             # never a silent stale URL
        assert p.stage is Stage.AWAITING_OWNER     # the work still completed
    finally:
        tmp.cleanup()


# --------------------------------------------------------------------------- #
# process_edits / diagnostic
# --------------------------------------------------------------------------- #
def test_process_edits_requires_pending() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.PROTOTYPE)
        try:
            process_edits(store, MockBuildDriver(), "acme", publisher=MockPublisher(), now="t")
        except PreconditionError:
            pass
        else:
            raise AssertionError("expected PreconditionError with no pending edits")
    finally:
        tmp.cleanup()


def test_process_edits_happy_path() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.PROTOTYPE)
        store.create_edit("acme", "bigger hero", "## Requested change\nbigger\n")
        assert store.pending_edits("acme")[0].state is EditState.PENDING
        out = process_edits(
            store, MockBuildDriver(), "acme", publisher=MockPublisher(), now="2026-06-19-2100"
        )
        assert out.ok
        assert out.preview_url == "https://ws-acme.pages.dev"
        assert any(r.kind == "process-edits" for r in store.list_reports("acme"))
    finally:
        tmp.cleanup()


def test_baseline_advances_to_baseline_ready() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.QUEUED)
        out = run_baseline(store, MockBuildDriver(), "acme", now="2026-06-20-1200")
        assert out.ok
        assert store.get_project("acme").stage is Stage.BASELINE_READY
        assert any(r.kind == "baseline" for r in store.list_reports("acme"))
    finally:
        tmp.cleanup()


def test_intake_pack_stays_baseline_ready() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.BASELINE_READY)
        out = run_intake_pack(store, MockBuildDriver(), "acme", now="2026-06-20-1200")
        assert out.ok
        assert store.get_project("acme").stage is Stage.BASELINE_READY  # concept decision unblocks assemble
        assert any(r.kind == "intake-pack" for r in store.list_reports("acme"))
    finally:
        tmp.cleanup()


def test_finish_advances_to_final() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.ANSWERS_RECEIVED)
        out = run_finish(
            store, MockBuildDriver(), "acme", publisher=MockPublisher(), now="2026-06-20-1200"
        )
        assert out.ok
        assert store.get_project("acme").stage is Stage.FINAL
        assert any(r.kind == "finish" for r in store.list_reports("acme"))
    finally:
        tmp.cleanup()


def test_finish_wrong_stage_refused() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.PROTOTYPE)
        try:
            run_finish(store, MockBuildDriver(), "acme", publisher=MockPublisher(), now="2026-06-20-1200")
        except PreconditionError:
            pass
        else:
            raise AssertionError("expected PreconditionError finishing before answers-received")
    finally:
        tmp.cleanup()


def test_diagnostic_runs_readonly() -> None:
    store, tmp = _store()
    try:
        _project(store, Stage.QUEUED)
        driver = MockBuildDriver()
        out = run_diagnostic(store, driver, "acme", now="2026-06-19-2100")
        assert out.ok
        assert driver.calls == ["Diagnose site https://acme.example"]
        assert out.preview_url is None  # read-only — no publish
        assert any(r.kind == "diagnostic" for r in store.list_reports("acme"))
    finally:
        tmp.cleanup()


# --------------------------------------------------------------------------- #
# Standalone runner
# --------------------------------------------------------------------------- #
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
