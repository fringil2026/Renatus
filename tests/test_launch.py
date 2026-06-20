"""Tests for the launch-review gate (engine.launch) + the run_cutover orchestration entrypoint.

Pure state-machine logic + a stage-gated cutover via mocks. No network/Claude.

    python3 tests/test_launch.py
    pytest tests/test_launch.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    FilesystemProjectStore,
    LaunchError,
    LaunchReview,
    LaunchStatus,
    MockBuildDriver,
    NotApprovedError,
    PreconditionError,
    Project,
    Stage,
    approve,
    reject,
    request_review,
    require_launch_approved,
    run_cutover,
)


# --------------------------------------------------------------------------- #
# engine.launch state machine
# --------------------------------------------------------------------------- #
def test_request_then_approve() -> None:
    lr = request_review(None, now="t1")
    assert lr.status is LaunchStatus.PENDING and lr.requested_at == "t1"
    lr = approve(lr, reviewer="ops@studio", now="t2", note="looks good")
    assert lr.status is LaunchStatus.APPROVED and lr.reviewer == "ops@studio" and lr.is_approved


def test_approve_requires_pending() -> None:
    try:
        approve(None, reviewer="ops", now="t")
    except LaunchError:
        pass
    else:
        raise AssertionError("expected LaunchError approving with no pending review")


def test_reject_requires_note_and_pending() -> None:
    lr = request_review(None, now="t1")
    try:
        reject(lr, reviewer="ops", now="t2", note="")
    except LaunchError:
        pass
    else:
        raise AssertionError("expected LaunchError rejecting without a note")
    lr = reject(lr, reviewer="ops", now="t2", note="hero image is upscaled")
    assert lr.status is LaunchStatus.REJECTED and lr.note == "hero image is upscaled"
    # cannot approve a rejected review without re-requesting
    try:
        approve(lr, reviewer="ops", now="t3")
    except LaunchError:
        pass
    else:
        raise AssertionError("expected LaunchError approving a REJECTED review")
    # but the customer may re-request after addressing the note
    assert request_review(lr, now="t4").status is LaunchStatus.PENDING


def test_require_launch_approved_gate() -> None:
    try:
        require_launch_approved(Project(slug="acme"))
    except NotApprovedError:
        pass
    else:
        raise AssertionError("expected NotApprovedError without an approved review")
    ok = Project(slug="acme", launch_review=LaunchReview(status=LaunchStatus.APPROVED))
    require_launch_approved(ok)  # must not raise


# --------------------------------------------------------------------------- #
# run_cutover orchestration
# --------------------------------------------------------------------------- #
def test_run_cutover_advances_stage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = FilesystemProjectStore(Path(tmp))
        store.create_project(Project(slug="acme", stage=Stage.FINAL))
        outcome = run_cutover(store, MockBuildDriver(), "acme", now="2026-06-20-1200")
        assert outcome.ok
        assert store.get_project("acme").stage is Stage.CUTOVER_CHECKED
        assert any(r.kind == "cutover" for r in store.list_reports("acme"))


def test_run_cutover_wrong_stage_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = FilesystemProjectStore(Path(tmp))
        store.create_project(Project(slug="acme", stage=Stage.PROTOTYPE))
        try:
            run_cutover(store, MockBuildDriver(), "acme", now="2026-06-20-1200")
        except PreconditionError:
            pass
        else:
            raise AssertionError("expected PreconditionError running cutover before stage=final")


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
