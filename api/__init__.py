"""Web Studio control-plane API.

A framework-agnostic core (`core.Application`) over the engine, with two adapters:
the stdlib dev server (`server.serve`) and the production FastAPI app (`fastapi_app.create_fastapi_app`).
See `api/README.md` and `docs/adr/0001-foundational-decisions.md`.
"""

from __future__ import annotations

from .core import ApiError, Application, Request, Response
from .deps import build_default_app, build_tenant_router
from .tenancy import TenantRouter

__all__ = [
    "ApiError",
    "Application",
    "Request",
    "Response",
    "TenantRouter",
    "build_default_app",
    "build_tenant_router",
]
