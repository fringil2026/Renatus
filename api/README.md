# api/ — control-plane HTTP API

The multi-tenant backend over the engine — the eventual replacement for `studio.py`'s `/api/*`
handlers. Structured as a **framework-agnostic core** plus thin adapters, so the web framework is a
swappable detail and the logic is testable with zero web dependencies.

```
core.py         Application — routing, auth seam, serialization, action wiring (no framework)
deps.py         build_default_app() — picks concrete engine impls (store/driver/publisher)
server.py       stdlib http.server adapter (dev/local, runnable now): python3 -m api.server
fastapi_app.py  FastAPI adapter (ADR-0001 §2 production target; import-guarded)
```

## Status — skeleton built & tested
- ✅ Projects: `GET/POST /v1/projects`, `GET /v1/projects/{slug}`
- ✅ Ledgers: `GET /v1/projects/{slug}/{edits,decisions,incidents,reports}`, `POST .../edits`
- ✅ Actions (async): `POST /v1/projects/{slug}/actions/{assemble,process-edits,diagnose}` —
  cheap preconditions checked synchronously (403/409), then the work is **enqueued → `202 + run id`**.
  Poll `GET /v1/projects/{slug}/runs` and `GET /v1/projects/{slug}/runs/{run_id}` for status/result.
  Backed by the `Runner` seam (`engine/runner.py`): `InlineRunner` (default/tests), `ThreadRunner`
  (dev server — real background, runs persisted to disk via `FilesystemRunStore`). Production swaps a
  Temporal/Inngest-backed runner behind the same interface.
- ✅ Ownership: `GET /v1/projects/{slug}/ownership`, `POST .../ownership/{challenge,verify}` —
  DNS-TXT / meta-tag / HTTP-file proof of domain control (`engine.ownership`). Expensive actions
  (assemble, process-edits) are **gated behind verified ownership** → `403` until verified;
  `diagnose` stays open (the free lead-gen). Toggle with `enforce_ownership` / `$WS_ENFORCE_OWNERSHIP`.
- ✅ Auth seam: bearer-token check (dev mode = off when no token); `/healthz` open
- ✅ Tested at the dispatch level (`tests/test_api.py`, 10/10) + a real-HTTP smoke of the dev server

## Known seams (intentionally stubbed for the skeleton)
- **Tenancy** — `_authenticate` resolves the caller but the store isn't yet per-tenant; production
  scopes the store from the auth context (PRODUCT-PLAN §3.5).
- **Durable workflows** — actions are async via the `Runner` seam; the dev `ThreadRunner` persists
  runs to disk but doesn't survive a crash mid-run. Production swaps a Temporal/Inngest runner for
  true crash-recovery (the orphaned-build failure mode in SYSTEM.md §3d).
- **Persistence** — `FilesystemProjectStore` for dev; swap a Postgres store via `deps.build_default_app`.
- **Deploy** — `UnconfiguredPublisher` (dev API doesn't deploy); inject a real publisher in production.

## Run it
```
python3 -m api.server                         # dev API on :8099, auth off
WS_API_TOKEN=secret python3 -m api.server     # require Authorization: Bearer secret
```
Production (after `pip install fastapi uvicorn`): `create_fastapi_app(build_default_app())`.
