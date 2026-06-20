"""Stdlib ``http.server`` adapter — a zero-dependency dev server for the control plane.

Runnable now (no FastAPI/uvicorn needed), mirroring how ``studio.py`` serves the operator dashboard.
Production uses ``api/fastapi_app.py`` instead; both are thin shells over ``api.core.Application``.

    python3 -m api.server                  # serves the dev app on :8099
    WS_API_TOKEN=secret python3 -m api.server   # require Authorization: Bearer secret
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import Application, Request
from .deps import build_default_app


def _make_handler(app: Application) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _dispatch(self, method: str) -> None:
            path, _, raw_query = self.path.partition("?")
            query = {}
            for pair in raw_query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    query[k] = v
            body = None
            length = int(self.headers.get("content-length") or 0)
            if length:
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    self._write(400, {"error": "invalid JSON body"})
                    return
            req = Request(
                method=method,
                path=path,
                body=body,
                headers={k: v for k, v in self.headers.items()},
                query=query,
            )
            resp = app.dispatch(req)
            self._write(resp.status, resp.body)

        def _write(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def log_message(self, *args) -> None:  # quiet by default
            pass

    return Handler


def serve(app: Application, *, host: str = "127.0.0.1", port: int = 8099) -> None:
    httpd = ThreadingHTTPServer((host, port), _make_handler(app))
    print(f"control-plane API on http://{host}:{port}  (auth {'on' if app._token else 'off'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


def main() -> None:
    serve(build_default_app(), port=int(os.environ.get("PORT", "8099")))


if __name__ == "__main__":
    main()
