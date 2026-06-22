"""FastAPI adapter — the production HTTP surface per ADR-0001 §2.

A thin shell over ``api.core.Application``: it translates FastAPI requests into the core's
transport-neutral ``Request`` and renders the core's ``Response`` back. All real logic stays in the
core, so this file carries no business rules — only wiring.

FastAPI isn't a hard dependency of the repo (the engine + the stdlib dev server need none), so the
import is deferred into ``create_fastapi_app``. Install for production with:

    pip install fastapi uvicorn

    # serve:
    from api.deps import build_default_app
    from api.fastapi_app import create_fastapi_app
    app = create_fastapi_app(build_default_app())
    # uvicorn api_main:app   (where api_main.py exposes `app`)
"""

from __future__ import annotations

from typing import Any

from .core import Application, Request


def create_fastapi_app(application: Application) -> Any:
    from fastapi import FastAPI
    from fastapi import Request as FastAPIRequest
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Web Studio Control Plane")

    @app.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def _catch_all(full_path: str, request: FastAPIRequest) -> JSONResponse:  # noqa: ANN202
        body: dict | None = None
        if request.method == "POST":
            raw = await request.body()
            if raw:
                import json

                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        resp = application.dispatch(
            Request(
                method=request.method,
                path="/" + full_path,
                body=body,
                headers=dict(request.headers),
                query=dict(request.query_params),
            )
        )
        if resp.raw is not None:  # binary/static asset
            from fastapi import Response as FastAPIResponse

            return FastAPIResponse(content=resp.raw, media_type=resp.content_type, status_code=resp.status)
        return JSONResponse(resp.body, status_code=resp.status)

    return app
