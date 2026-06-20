# Architecture map (SaaS foundation)

Navigational guide to the tool→product migration. Background + rationale: **PRODUCT-PLAN.md**;
locked choices: **docs/adr/0001-foundational-decisions.md**.

> The legacy single-operator studio (`studio.py` + `clients/`) is **untouched and still runs**. The
> new code below is additive and lives behind interfaces; nothing depends on it yet.

## The layers (request flows top → bottom)

```
api/            control plane — framework-agnostic core + stdlib & FastAPI adapters
  tenancy.py      TenantRouter — token -> tenant -> isolated Application; + platform-admin
                    (tenant signup, cross-tenant launch queue) behind an admin token
  core.py         routing · bearer-auth seam · ownership/launch/paywall gates · async actions · assets
  server.py       stdlib http.server dev adapter   |  fastapi_app.py  production adapter
  deps.py         wires concrete engine impls (build_default_app / build_tenant_router)
        │
engine/         headless, storage-agnostic rebuild engine (the moat)
  tenancy         Tenant + TenantStore (the multi-tenant identity registry)
  orchestration   baseline / intake-pack / assemble / process_edits / diagnose / finish / cutover
  transitions     stage machine (valid transitions + command availability)
  ownership       domain verification (DNS-TXT / meta-tag / HTTP-file) — the abuse gate
  launch          human-reviewed-launch gate (request/approve/reject) — gates cutover (ADR-0002 #2)
  metering        per-run cost/token aggregation (UsageSummary)        (ADR-0002 #3)
  billing         entitlement/paywall — free diagnostic, paid rebuild  (ADR-0002 #4)
  runner + runs   durable-workflow seam (InlineRunner / ThreadRunner; Run + RunStore)
  driver          BuildDriver seam: LocalClaudeDriver (claude -p) · AgentSDKDriver
  publish         Publisher seam (studio-owned deploy net)
  store           ProjectStore / ArtifactStore interfaces
  fs_store        FilesystemProjectStore (over clients/<slug>/)   |  sql_store  SQL backend
  models          typed domain (Stage, Project, Edit, Decision, Incident, Report, Ownership, …)
```

Everything crosses a layer through an **interface**, each with a working impl plus a tested seam for
the production swap.

## Run it

```sh
python3 tests/run_all.py                 # whole suite (no deps); incl. the full-funnel golden path
python3 -m api.server                     # dev control-plane API on :8099 (stdlib, no deps)
WS_API_TOKEN=secret python3 -m api.server # with bearer auth
AGENT_SDK_SMOKE=1 python3 tests/smoke_agent_sdk.py   # opt-in: live Claude via the Agent SDK
```

Optional extras (`pip install -e '.[api,agent,postgres,dns]'`) enable FastAPI, the Agent SDK,
Postgres, and faster DNS respectively — none are needed for the core or the test suite.

## Production bindings (the remaining swaps — all behind existing interfaces)

| Concern | Built & tested (dev) | Production binding |
|---|---|---|
| State store | `FilesystemProjectStore`, `SqlProjectStore` (sqlite) | `SqlProjectStore(psycopg.connect(...), placeholder="%s")` |
| Run store | `Filesystem`/`InMemory`/`SqlRunStore` | `SqlRunStore` on Postgres |
| Artifacts | in-memory / filesystem | R2/S3 `ArtifactStore` via `artifacts_factory` |
| Claude execution | `LocalClaudeDriver` (`claude -p`) | `AgentSDKDriver` in a per-tenant sandbox (`workers/`) |
| Async runs | `ThreadRunner` (durable to disk) | Temporal/Inngest `Runner` |
| HTTP | stdlib `api/server.py` | `api/fastapi_app.py` + uvicorn |
| Multi-tenancy | `TenantRouter` + per-tenant isolated stores (filesystem subtree) | tenant-filtered SQL store; external token issuer (Clerk/Auth0/Supabase) feeds the same token→tenant seam |

## Where to start reading
New to this? Read **PRODUCT-PLAN.md** (the why), then `engine/store.py` (the central seam), then
`engine/orchestration.py` (what the engine actually does), then `api/core.py` (how it's exposed).
