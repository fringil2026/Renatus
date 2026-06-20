"""Golden-path integration test — the entire customer funnel through the API, gates enforced.

Walks one project from signup to launch-ready, hitting every real endpoint in the order the web app
(web/README.md) would, with ownership + billing enforced and a reviewer approval. Proves the
endpoints *compose* into the lifecycle — not just that each works in isolation. Uses mocks for Claude
+ deploy + DNS, so it's deterministic and offline.

    python3 tests/test_funnel.py
    pytest tests/test_funnel.py
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
    InlineRunner,
    InMemoryRunStore,
    MockBuildDriver,
    MockPublisher,
    Project,
    Stage,
)

_NOW = "2026-06-20-1500"


def _app():
    tmp = tempfile.TemporaryDirectory()
    resolver = FakeDnsResolver()  # shared — the test injects the TXT record after the challenge
    app = Application(
        FilesystemProjectStore(Path(tmp.name)),
        driver=MockBuildDriver(),
        publisher=MockPublisher(),
        token=None,                       # customer auth off for the test
        now_fn=lambda: _NOW,
        resolver=resolver,
        fetcher=FakeFetcher(),
        runner=InlineRunner(InMemoryRunStore()),
        enforce_ownership=True,           # gates ON — this is the real path
        enforce_billing=True,
        reviewer_token="rev",             # ops approval distinct from the customer
    )
    return app, resolver, tmp


def _post(app, path, body=None, **kw):
    r = app.dispatch(Request(method="POST", path=path, body=body, **kw))
    return r.status, r.body


def _get(app, path, **kw):
    r = app.dispatch(Request(method="GET", path=path, **kw))
    return r.status, r.body


def _ok_run(status_body) -> None:
    status, body = status_body
    assert status == 202, f"expected 202, got {status}: {body}"
    assert body["run"]["status"] == "succeeded", body["run"]


def test_full_funnel_golden_path() -> None:
    app, resolver, tmp = _app()
    try:
        S = "acme-orchids"

        # 1. create + 2. free diagnostic (no gates)
        assert _post(app, "/v1/projects", {"slug": S, "domain": "https://acme.example"})[0] == 201
        _ok_run(_post(app, f"/v1/projects/{S}/actions/diagnose"))

        # rebuild is gated until paid AND verified
        assert _post(app, f"/v1/projects/{S}/actions/baseline")[0] == 403  # unverified

        # 3. pay (dev checkout stub flips the plan)
        assert _post(app, f"/v1/projects/{S}/billing/checkout")[1]["plan"] == "active"

        # 4. verify domain ownership (DNS-TXT)
        status, body = _post(app, f"/v1/projects/{S}/ownership/challenge", {"method": "dns-txt"})
        assert status == 201
        resolver.records["acme.example"] = [body["expected_value"]]  # owner "adds" the TXT record
        assert _post(app, f"/v1/projects/{S}/ownership/verify")[0] == 200

        # 5. baseline → 6. concept boards (intake pack) → 7. prototype
        _ok_run(_post(app, f"/v1/projects/{S}/actions/baseline"))
        _ok_run(_post(app, f"/v1/projects/{S}/actions/intake-pack"))
        _ok_run(_post(app, f"/v1/projects/{S}/actions/assemble"))
        assert _get(app, f"/v1/projects/{S}")[1]["stage"] == "awaiting-owner"

        # 8. an edit
        assert _post(app, f"/v1/projects/{S}/edits", {"name": "bigger hero", "request": "enlarge"})[0] == 201
        _ok_run(_post(app, f"/v1/projects/{S}/actions/process-edits"))

        # 9. owner answers → finalize
        assert _post(app, f"/v1/projects/{S}/answers", {"content": "Q1: ...\nQ2: ..."})[0] == 200
        assert _get(app, f"/v1/projects/{S}")[1]["stage"] == "answers-received"
        _ok_run(_post(app, f"/v1/projects/{S}/actions/finish"))
        assert _get(app, f"/v1/projects/{S}")[1]["stage"] == "final"

        # 10. request launch → reviewer approves → cutover prechecks
        assert _post(app, f"/v1/projects/{S}/launch/request")[1]["launch"]["status"] == "pending"
        # customer cannot approve their own launch
        assert _post(app, f"/v1/projects/{S}/launch/approve")[0] == 403
        # the reviewer can
        approve = app.dispatch(Request(
            method="POST", path=f"/v1/projects/{S}/launch/approve",
            headers={"Authorization": "Bearer rev"},
        ))
        assert approve.status == 200 and approve.body["launch"]["status"] == "approved"
        _ok_run(_post(app, f"/v1/projects/{S}/actions/cutover"))

        # launch-ready (DNS go-live stays a human step beyond this point)
        assert _get(app, f"/v1/projects/{S}")[1]["stage"] == "cutover-checked"

        # usage was metered across the journey
        usage = _get(app, f"/v1/projects/{S}/usage")[1]["usage"]
        assert usage["runs"] >= 6  # diagnose, baseline, intake-pack, assemble, process-edits, finish, cutover
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
