"""Tests for multi-tenancy: TenantStore + the TenantRouter front controller (isolation).

Proves the router authenticates by token, resolves the tenant, and that each tenant's data is
isolated (one tenant cannot see or address another's projects). No network.

    python3 tests/test_tenancy.py
    pytest tests/test_tenancy.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from api.core import Application, Request  # noqa: E402
from api.tenancy import TenantRouter  # noqa: E402
from engine import (  # noqa: E402
    FakeDnsResolver,
    FakeFetcher,
    FilesystemProjectStore,
    FilesystemTenantStore,
    InlineRunner,
    InMemoryRunStore,
    InMemoryTenantStore,
    MockBuildDriver,
    MockPublisher,
    Tenant,
)


def _router(base: Path) -> TenantRouter:
    tenants = InMemoryTenantStore(
        [Tenant(id="t1", api_token="tok1"), Tenant(id="t2", api_token="tok2")]
    )

    def factory(tenant: Tenant) -> Application:
        root = base / tenant.id
        return Application(
            FilesystemProjectStore(root),
            driver=MockBuildDriver(),
            publisher=MockPublisher(),
            token=None,
            enforce_ownership=False,
            runner=InlineRunner(InMemoryRunStore()),
            resolver=FakeDnsResolver(),
            fetcher=FakeFetcher(),
        )

    return TenantRouter(tenants, factory)


def _req(method: str, path: str, token: str | None = None, body: dict | None = None) -> Request:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return Request(method=method, path=path, body=body, headers=headers)


# --------------------------------------------------------------------------- #
def test_tenant_store_resolve_token() -> None:
    s = InMemoryTenantStore([Tenant(id="t1", api_token="abc")])
    assert s.resolve_token("abc").id == "t1"
    assert s.resolve_token("nope") is None
    assert s.resolve_token("") is None


def test_filesystem_tenant_store_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = FilesystemTenantStore(Path(tmp))
        s.create(Tenant(id="t1", name="Acme", api_token="tok"))
        assert s.get("t1").name == "Acme"
        assert s.resolve_token("tok").id == "t1"
        assert [t.id for t in s.list()] == ["t1"]


def test_healthz_is_open() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = _router(Path(tmp))
        resp = r.dispatch(_req("GET", "/healthz"))
        assert resp.status == 200 and resp.body["status"] == "ok"


def test_auth_required() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = _router(Path(tmp))
        assert r.dispatch(_req("GET", "/v1/projects")).status == 401          # no token
        assert r.dispatch(_req("GET", "/v1/projects", token="bad")).status == 401  # unknown token


def test_tenant_isolation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = _router(Path(tmp))
        # t1 creates a project
        assert r.dispatch(_req("POST", "/v1/projects", "tok1", {"slug": "acme"})).status == 201
        # t1 sees it
        resp = r.dispatch(_req("GET", "/v1/projects", "tok1"))
        assert [p["slug"] for p in resp.body["projects"]] == ["acme"]
        # t2 does NOT see it
        resp = r.dispatch(_req("GET", "/v1/projects", "tok2"))
        assert resp.body["projects"] == []
        # t2 cannot address it
        assert r.dispatch(_req("GET", "/v1/projects/acme", "tok2")).status == 404
        # t1 still can
        assert r.dispatch(_req("GET", "/v1/projects/acme", "tok1")).status == 200


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
