"""Tests for usage metering (engine.metering) + the billing entitlement (engine.billing)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    PLAN_ACTIVE,
    PLAN_FREE,
    NotPaidError,
    Project,
    Run,
    RunStatus,
    get_plan,
    is_paid,
    require_paid_plan,
    set_plan,
    summarize_runs,
)


def _run(kind: str, cost: float | None, intok: int, outtok: int) -> Run:
    return Run(
        id=f"run_{kind}", slug="acme", kind=kind, status=RunStatus.SUCCEEDED, created="t",
        result={"ok": True, "cost_usd": cost, "usage": {"input_tokens": intok, "output_tokens": outtok}},
    )


# --------------------------------------------------------------------------- #
def test_summarize_runs_totals() -> None:
    runs = [
        _run("assemble", 0.42, 1000, 500),
        _run("process-edits", 0.10, 200, 100),
        _run("diagnostic", None, 0, 0),  # no cost reported (mock/subprocess driver)
    ]
    s = summarize_runs(runs)
    assert s.runs == 3
    assert abs(s.cost_usd - 0.52) < 1e-9
    assert s.input_tokens == 1200 and s.output_tokens == 600
    assert s.runs_by_kind == {"assemble": 1, "process-edits": 1, "diagnostic": 1}


def test_summarize_empty() -> None:
    s = summarize_runs([])
    assert s.runs == 0 and s.cost_usd == 0.0
    assert s.to_dict()["runs_by_kind"] == {}


def test_summary_to_dict_rounds() -> None:
    s = summarize_runs([_run("assemble", 0.1234567, 0, 0)])
    assert s.to_dict()["cost_usd"] == 0.123457


def test_billing_entitlement() -> None:
    p = Project(slug="acme")
    assert get_plan(p) == PLAN_FREE and not is_paid(p)
    try:
        require_paid_plan(p)
    except NotPaidError:
        pass
    else:
        raise AssertionError("expected NotPaidError on the free plan")
    set_plan(p, PLAN_ACTIVE)
    assert is_paid(p)
    require_paid_plan(p)  # must not raise
    # plan persists in extra (round-trips via Project.to_dict/from_dict)
    assert Project.from_dict("acme", p.to_dict()).extra.get("plan") == PLAN_ACTIVE


def _run_all() -> int:
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
    raise SystemExit(_run_all())
