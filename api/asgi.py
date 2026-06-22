"""ASGI entrypoint for production hosting.

    pip install -e '.[api]'
    uvicorn api.asgi:app --host 0.0.0.0 --port $PORT

Single-tenant by default. For multi-tenant, swap `build_default_app()` for `build_tenant_router()`
(set WS_ADMIN_TOKEN and mint tenants via POST /v1/tenants).
"""

from __future__ import annotations

from .deps import build_default_app
from .fastapi_app import create_fastapi_app

app = create_fastapi_app(build_default_app())
