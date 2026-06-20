"""Multi-tenant front controller.

``TenantRouter`` wraps the single-tenant ``Application`` without changing it: it resolves the bearer
token → tenant, builds (and caches) a per-tenant ``Application`` over that tenant's *own* stores, and
delegates ``dispatch``. Because it presents the same ``dispatch(Request) -> Response`` interface, the
stdlib server and the FastAPI adapter drive it unchanged — and the existing single-tenant
``Application`` (and its whole test suite) is untouched.

Isolation is structural: each tenant's ``Application`` is built from a store scoped to that tenant
(e.g. a filesystem subtree, or a tenant-filtered SQL store), so one tenant literally cannot address
another's projects. The inner apps run with auth disabled (`token=None`) because the router has
already authenticated; the router is the single auth point.
"""

from __future__ import annotations

from typing import Callable

from engine import Tenant, TenantStore

from .core import Application, Request, Response


class TenantRouter:
    """Front controller: bearer token → tenant → that tenant's Application."""

    def __init__(self, tenant_store: TenantStore, app_factory: Callable[[Tenant], Application]) -> None:
        self._tenants = tenant_store
        self._factory = app_factory
        self._apps: dict[str, Application] = {}

    def _app_for(self, tenant: Tenant) -> Application:
        app = self._apps.get(tenant.id)
        if app is None:
            app = self._factory(tenant)
            self._apps[tenant.id] = app
        return app

    def dispatch(self, request: Request) -> Response:
        if request.path == "/healthz":  # unauthenticated, tenant-agnostic liveness
            return Response(200, {"status": "ok"})
        auth = request.header("authorization") or ""
        token = auth[len("Bearer ") :] if auth.startswith("Bearer ") else ""
        tenant = self._tenants.resolve_token(token) if token else None
        if tenant is None:
            return Response(401, {"error": "invalid or missing tenant token"})
        return self._app_for(tenant).dispatch(request)
