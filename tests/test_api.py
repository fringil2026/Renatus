"""Tests for the control-plane API core — dispatch-level, no web framework, no network.

Drives ``Application.dispatch()`` directly with a temp FilesystemProjectStore + MockBuildDriver +
MockPublisher, so the routing, auth, serialization, action wiring, and error mapping are all proven
without installing FastAPI/uvicorn. Never touches real client data.

    python3 tests/test_api.py
    pytest tests/test_api.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from api.core import Application, Request  # noqa: E402
from engine import (  # noqa: E402
    FakeDnsResolver,
    FakeFetcher,
    FilesystemProjectStore,
    MockBuildDriver,
    MockPublisher,
    Ownership,
    OwnershipStatus,
    Project,
    Stage,
)
from engine.ownership import DnsResolver, HttpFetcher  # noqa: E402
from engine.runner import Runner  # noqa: E402

_NOW = "2026-06-19-2100"


def _app(
    token: str | None = None,
    *,
    publisher: MockPublisher | None = None,
    resolver: DnsResolver | None = None,
    fetcher: HttpFetcher | None = None,
    enforce_ownership: bool = True,
    runner: Runner | None = None,
) -> tuple[Application, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    store = FilesystemProjectStore(Path(tmp.name))
    app = Application(
        store,
        driver=MockBuildDriver(),
        publisher=publisher or MockPublisher(),
        token=token,
        now_fn=lambda: _NOW,
        resolver=resolver or FakeDnsResolver(),
        fetcher=fetcher or FakeFetcher(),
        enforce_ownership=enforce_ownership,
        runner=runner,  # None -> Application's default InlineRunner (synchronous, deterministic)
    )
    return app, tmp


def _verify(app: Application, slug: str) -> None:
    """Mark a project's domain ownership verified (precondition for gated actions)."""
    p = app.store.get_project(slug)
    p.ownership = Ownership(status=OwnershipStatus.VERIFIED, domain=p.domain or slug)
    app.store.save_project(p)


def _get(app: Application, path: str, **kw) -> "tuple[int, dict]":
    r = app.dispatch(Request(method="GET", path=path, **kw))
    return r.status, r.body


def _post(app: Application, path: str, body: dict | None = None, **kw) -> "tuple[int, dict]":
    r = app.dispatch(Request(method="POST", path=path, body=body, **kw))
    return r.status, r.body


# --------------------------------------------------------------------------- #
def test_health_is_unauthenticated() -> None:
    app, tmp = _app(token="secret")  # auth on, but health is open
    try:
        status, body = _get(app, "/healthz")
        assert status == 200 and body["status"] == "ok"
    finally:
        tmp.cleanup()


def test_project_crud() -> None:
    app, tmp = _app()
    try:
        status, body = _post(app, "/v1/projects", {"slug": "acme", "name": "Acme", "domain": "https://acme.example"})
        assert status == 201 and body["slug"] == "acme"

        status, body = _get(app, "/v1/projects")
        assert status == 200 and [p["slug"] for p in body["projects"]] == ["acme"]

        status, body = _get(app, "/v1/projects/acme")
        assert status == 200 and body["name"] == "Acme" and body["stage"] == "queued"

        status, body = _get(app, "/v1/projects/nope")
        assert status == 404
    finally:
        tmp.cleanup()


def test_create_project_requires_slug() -> None:
    app, tmp = _app()
    try:
        status, body = _post(app, "/v1/projects", {"name": "no slug"})
        assert status == 400 and "slug" in body["error"]
    finally:
        tmp.cleanup()


def test_duplicate_project_conflicts() -> None:
    app, tmp = _app()
    try:
        _post(app, "/v1/projects", {"slug": "acme"})
        status, _ = _post(app, "/v1/projects", {"slug": "acme"})
        assert status == 409
    finally:
        tmp.cleanup()


def test_edits_endpoints() -> None:
    app, tmp = _app()
    try:
        _post(app, "/v1/projects", {"slug": "acme", "stage": "prototype"})
        status, body = _post(app, "/v1/projects/acme/edits", {"name": "bigger hero", "request": "make it bigger"})
        assert status == 201 and body["state"] == "PENDING" and body["n"] == 1

        status, body = _get(app, "/v1/projects/acme/edits")
        assert status == 200 and len(body["edits"]) == 1
    finally:
        tmp.cleanup()


def test_assemble_action_advances_and_publishes() -> None:
    pub = MockPublisher()
    app, tmp = _app(publisher=pub)
    try:
        app.store.create_project(Project(slug="acme", name="Acme", stage=Stage.BASELINE_READY))
        _verify(app, "acme")
        status, body = _post(app, "/v1/projects/acme/actions/assemble")
        assert status == 202  # accepted -> a run
        run = body["run"]
        assert run["status"] == "succeeded"  # default inline runner is terminal on return
        assert run["result"]["ok"] is True
        assert run["result"]["preview_url"] == "https://ws-acme.pages.dev"
        # the project advanced + published
        _, proj = _get(app, "/v1/projects/acme")
        assert proj["stage"] == "awaiting-owner"
        assert pub.calls == ["acme"]
        # the run is queryable
        status, body = _get(app, f"/v1/projects/acme/runs/{run['id']}")
        assert status == 200 and body["run"]["status"] == "succeeded"
        status, body = _get(app, "/v1/projects/acme/runs")
        assert len(body["runs"]) == 1
    finally:
        tmp.cleanup()


def test_assemble_wrong_stage_conflicts() -> None:
    app, tmp = _app()
    try:
        app.store.create_project(Project(slug="acme", stage=Stage.QUEUED))
        _verify(app, "acme")  # isolate the stage gate from the ownership gate
        status, body = _post(app, "/v1/projects/acme/actions/assemble")
        assert status == 409 and "not available" in body["error"]
    finally:
        tmp.cleanup()


def test_process_edits_no_pending_conflicts() -> None:
    app, tmp = _app()
    try:
        app.store.create_project(Project(slug="acme", stage=Stage.PROTOTYPE))
        _verify(app, "acme")  # isolate the no-pending-edits check from the ownership gate
        status, body = _post(app, "/v1/projects/acme/actions/process-edits")
        assert status == 409 and "PENDING" in body["error"]
    finally:
        tmp.cleanup()


def test_diagnose_writes_report() -> None:
    app, tmp = _app()
    try:
        app.store.create_project(Project(slug="acme", domain="https://acme.example", stage=Stage.QUEUED))
        status, body = _post(app, "/v1/projects/acme/actions/diagnose")
        assert status == 202 and body["run"]["status"] == "succeeded"
        status, body = _get(app, "/v1/projects/acme/reports")
        assert any(r["kind"] == "diagnostic" for r in body["reports"])
    finally:
        tmp.cleanup()


def test_ownership_challenge_and_verify_dns() -> None:
    # Fake DNS that will contain the issued token once we read it back.
    resolver = FakeDnsResolver()
    app, tmp = _app(resolver=resolver)
    try:
        app.store.create_project(Project(slug="acme", domain="https://acme.example"))

        status, body = _post(app, "/v1/projects/acme/ownership/challenge", {"method": "dns-txt"})
        assert status == 201 and body["ownership"]["status"] == "pending"
        expected = body["expected_value"]  # "ws-site-verification=<token>"

        # before the record exists -> 422, stays pending
        status, body = _post(app, "/v1/projects/acme/ownership/verify")
        assert status == 422 and body["verified"] is False

        # owner "adds" the TXT record, then verify -> 200 verified
        resolver.records["acme.example"] = [expected]
        status, body = _post(app, "/v1/projects/acme/ownership/verify")
        assert status == 200 and body["verified"] is True
        assert body["ownership"]["status"] == "verified"

        status, body = _get(app, "/v1/projects/acme/ownership")
        assert body["ownership"]["status"] == "verified"
    finally:
        tmp.cleanup()


def test_assemble_blocked_until_ownership_verified() -> None:
    app, tmp = _app()  # enforcement on, no verification done
    try:
        app.store.create_project(Project(slug="acme", domain="https://acme.example", stage=Stage.BASELINE_READY))
        status, body = _post(app, "/v1/projects/acme/actions/assemble")
        assert status == 403 and "ownership" in body["error"].lower()
    finally:
        tmp.cleanup()


def test_enforcement_can_be_disabled() -> None:
    app, tmp = _app(enforce_ownership=False)
    try:
        app.store.create_project(Project(slug="acme", stage=Stage.BASELINE_READY))
        status, body = _post(app, "/v1/projects/acme/actions/assemble")
        assert status == 202 and body["run"]["status"] == "succeeded"  # gate off -> proceeds
    finally:
        tmp.cleanup()


def test_async_action_with_thread_runner() -> None:
    from engine import InMemoryRunStore, ThreadRunner

    runner = ThreadRunner(InMemoryRunStore())
    app, tmp = _app(runner=runner)
    try:
        app.store.create_project(Project(slug="acme", stage=Stage.BASELINE_READY))
        _verify(app, "acme")
        status, body = _post(app, "/v1/projects/acme/actions/assemble")
        assert status == 202
        run_id = body["run"]["id"]  # may be queued/running at this point

        runner.wait(timeout=10)  # let the background job finish
        status, body = _get(app, f"/v1/projects/acme/runs/{run_id}")
        assert status == 200 and body["run"]["status"] == "succeeded"
        _, proj = _get(app, "/v1/projects/acme")
        assert proj["stage"] == "awaiting-owner"
    finally:
        tmp.cleanup()


def test_launch_review_then_cutover() -> None:
    app, tmp = _app()
    try:
        app.store.create_project(Project(slug="acme", stage=Stage.FINAL))
        # cutover blocked before approval
        status, body = _post(app, "/v1/projects/acme/actions/cutover")
        assert status == 403 and "approve" in body["error"].lower()
        # customer requests launch -> pending
        status, body = _post(app, "/v1/projects/acme/launch/request")
        assert status == 200 and body["launch"]["status"] == "pending"
        # reviewer approves (dev mode: no reviewer token)
        status, body = _post(app, "/v1/projects/acme/launch/approve", {"note": "ship it"})
        assert status == 200 and body["launch"]["status"] == "approved"
        # cutover now runs -> 202 run succeeded, stage advances
        status, body = _post(app, "/v1/projects/acme/actions/cutover")
        assert status == 202 and body["run"]["status"] == "succeeded"
        _, proj = _get(app, "/v1/projects/acme")
        assert proj["stage"] == "cutover-checked"
    finally:
        tmp.cleanup()


def test_cutover_wrong_stage_conflicts() -> None:
    app, tmp = _app()
    try:
        app.store.create_project(Project(slug="acme", stage=Stage.PROTOTYPE))
        status, _ = _post(app, "/v1/projects/acme/actions/cutover")
        assert status == 409  # not at stage=final
    finally:
        tmp.cleanup()


def test_launch_reject_requires_note() -> None:
    app, tmp = _app()
    try:
        app.store.create_project(Project(slug="acme", stage=Stage.FINAL))
        _post(app, "/v1/projects/acme/launch/request")
        status, body = _post(app, "/v1/projects/acme/launch/reject", {})
        assert status == 400 and "note" in body["error"].lower()
        status, body = _post(app, "/v1/projects/acme/launch/reject", {"note": "upscaled hero"})
        assert status == 200 and body["launch"]["status"] == "rejected"
    finally:
        tmp.cleanup()


def test_reviewer_token_separates_customer_from_ops() -> None:
    # reviewer_token set, customer auth off: approve needs the reviewer bearer.
    tmp = tempfile.TemporaryDirectory()
    try:
        store = FilesystemProjectStore(Path(tmp.name))
        app = Application(
            store, driver=MockBuildDriver(), publisher=MockPublisher(), now_fn=lambda: _NOW,
            resolver=FakeDnsResolver(), fetcher=FakeFetcher(), reviewer_token="rev-secret",
        )
        store.create_project(Project(slug="acme", stage=Stage.FINAL))
        _post(app, "/v1/projects/acme/launch/request")
        status, _ = _post(app, "/v1/projects/acme/launch/approve")  # no reviewer creds
        assert status == 403
        status, body = _post(
            app, "/v1/projects/acme/launch/approve", headers={"Authorization": "Bearer rev-secret"}
        )
        assert status == 200 and body["launch"]["status"] == "approved"
    finally:
        tmp.cleanup()


def test_usage_endpoint_summarizes_runs() -> None:
    app, tmp = _app()
    try:
        app.store.create_project(Project(slug="acme", domain="https://acme.example", stage=Stage.QUEUED))
        _post(app, "/v1/projects/acme/actions/diagnose")  # one run (inline -> done)
        status, body = _get(app, "/v1/projects/acme/usage")
        assert status == 200
        assert body["usage"]["runs"] == 1
        assert body["usage"]["runs_by_kind"] == {"diagnostic": 1}
    finally:
        tmp.cleanup()


def test_paywall_gates_assemble_when_billing_enforced() -> None:
    tmp = tempfile.TemporaryDirectory()
    try:
        store = FilesystemProjectStore(Path(tmp.name))
        app = Application(
            store, driver=MockBuildDriver(), publisher=MockPublisher(), now_fn=lambda: _NOW,
            resolver=FakeDnsResolver(), fetcher=FakeFetcher(), enforce_billing=True,
        )
        store.create_project(Project(slug="acme", stage=Stage.BASELINE_READY))
        _verify(app, "acme")  # ownership ok, but plan is free
        status, body = _post(app, "/v1/projects/acme/actions/assemble")
        assert status == 402 and "free plan" in body["error"].lower()
        # diagnostic stays free even with billing enforced
        store.create_project(Project(slug="other", domain="https://o.example", stage=Stage.QUEUED))
        assert _post(app, "/v1/projects/other/actions/diagnose")[0] == 202
        # pay -> assemble proceeds
        status, body = _post(app, "/v1/projects/acme/billing/checkout")
        assert status == 200 and body["plan"] == "active"
        status, body = _post(app, "/v1/projects/acme/actions/assemble")
        assert status == 202 and body["run"]["status"] == "succeeded"
    finally:
        tmp.cleanup()


def test_auth_enforced_when_token_set() -> None:
    app, tmp = _app(token="secret")
    try:
        status, _ = _get(app, "/v1/projects")  # no header
        assert status == 401
        status, _ = _get(app, "/v1/projects", headers={"Authorization": "Bearer secret"})
        assert status == 200
    finally:
        tmp.cleanup()


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
