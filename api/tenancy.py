"""Multi-tenant front controller + platform-admin surface.

``TenantRouter`` wraps the single-tenant ``Application`` without changing it: it resolves the bearer
token → tenant, builds (and caches) a per-tenant ``Application`` over that tenant's *own* stores, and
delegates ``dispatch``. Same ``dispatch(Request) -> Response`` interface, so the stdlib server and the
FastAPI adapter drive it unchanged — and the single-tenant ``Application`` (and its whole test suite)
is untouched.

It also hosts the **platform-admin** endpoints (tenant signup + the cross-tenant launch queue) — these
are platform-level, not tenant-scoped, so the router handles them directly behind a separate
``admin_token`` (distinct from any tenant or reviewer token). The auth vendor that issues tenant
tokens in production plugs into ``POST /v1/tenants``; here it mints a token directly.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Callable

from engine import Tenant, TenantStore

from .core import Application, Request, Response


class TenantRouter:
    """Front controller: bearer token → tenant → that tenant's Application; plus platform admin."""

    def __init__(
        self,
        tenant_store: TenantStore,
        app_factory: Callable[[Tenant], Application],
        *,
        admin_token: str | None = None,
    ) -> None:
        self._tenants = tenant_store
        self._factory = app_factory
        self._admin_token = admin_token  # None = admin surface disabled
        self._apps: dict[str, Application] = {}

    def _app_for(self, tenant: Tenant) -> Application:
        app = self._apps.get(tenant.id)
        if app is None:
            app = self._factory(tenant)
            self._apps[tenant.id] = app
        return app

    @staticmethod
    def _bearer(request: Request) -> str:
        auth = request.header("authorization") or ""
        return auth[len("Bearer ") :] if auth.startswith("Bearer ") else ""

    def dispatch(self, request: Request) -> Response:
        if request.path == "/healthz":  # unauthenticated, tenant-agnostic liveness
            return Response(200, {"status": "ok"})
        # Platform-admin routes are cross-tenant — handled here, not delegated to a tenant app.
        if request.path == "/v1/tenants" or request.path.startswith("/v1/admin/"):
            return self._dispatch_admin(request)
        tenant = self._tenants.resolve_token(self._bearer(request))
        if tenant is None:
            return Response(401, {"error": "invalid or missing tenant token"})
        return self._app_for(tenant).dispatch(request)

    # -- platform admin ---------------------------------------------------- #
    def _dispatch_admin(self, request: Request) -> Response:
        if self._admin_token is None:
            return Response(403, {"error": "admin surface is not enabled"})
        if self._bearer(request) != self._admin_token:
            return Response(403, {"error": "platform-admin authorization required"})

        if request.path == "/v1/tenants" and request.method == "POST":
            return self._create_tenant(request)
        if request.path == "/v1/tenants" and request.method == "GET":
            return Response(200, {"tenants": [self._tenant_public(t) for t in self._tenants.list()]})
        if request.path == "/v1/admin/launches" and request.method == "GET":
            return self._launch_queue(request)
        return Response(404, {"error": f"no admin route for {request.method} {request.path}"})

    @staticmethod
    def _tenant_public(t: Tenant) -> dict:
        # Token is returned only at creation; the list view omits it.
        return {"id": t.id, "name": t.name, "created": t.created}

    def _create_tenant(self, request: Request) -> Response:
        body = request.body or {}
        name = body.get("name", "")
        tenant = Tenant(
            id="t_" + secrets.token_hex(6),
            name=name,
            api_token=secrets.token_hex(16),
            created=datetime.now(timezone.utc).isoformat(),
        )
        self._tenants.create(tenant)
        # api_token is shown ONCE here (the caller must store it).
        return Response(201, {"id": tenant.id, "name": tenant.name, "api_token": tenant.api_token})

    def _launch_queue(self, request: Request) -> Response:
        """Cross-tenant review queue for the ops console — projects with a launch review."""
        want = request.query.get("status")  # e.g. "pending"; omit for all reviews
        items: list[dict] = []
        for tenant in self._tenants.list():
            app = self._app_for(tenant)
            store = app.store
            for slug in store.list_projects():
                p = store.get_project(slug)
                if p is None or p.launch_review is None:
                    continue
                lr = p.launch_review
                if want and lr.status.value != want:
                    continue
                items.append({
                    "tenant_id": tenant.id,
                    "slug": slug,
                    "stage": p.stage.value,
                    "preview_url": p.preview_url,
                    "launch": lr.to_dict(),
                })
        return Response(200, {"launches": items})
