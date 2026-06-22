# NEXT-STEPS — operator runbook (SaaS foundation → production)

Where we are: the multi-tenant control-plane **backend is complete and tested** on the
`saas-foundation` branch (95 tests, 11 suites; full-funnel golden path). `studio.py` + `clients/` are
untouched. What remains is durability (push/PR), one live confirmation, the vendor bindings, and the
web app. This is the sequenced path. Commands assume repo root `/Users/ericliu/web-studio`.

> Tip: to run a shell command in this Claude session, prefix it with `!` (e.g. `! claude` for an
> interactive login). Anything below you can also just run in your own terminal.

---

## Phase 0 — See it work locally (~10 min, no installs)

```sh
python3 tests/run_all.py                      # 95/95 across 11 suites
python3 -m api.server                         # dev control-plane API on http://127.0.0.1:8099
```
In another terminal, walk the funnel (auth off in dev; ownership/billing default off for the
single-tenant dev app, so this is the happy path):
```sh
curl -s localhost:8099/healthz
curl -s -X POST localhost:8099/v1/projects -d '{"slug":"demo","domain":"https://demo.example"}'
curl -s -X POST localhost:8099/v1/projects/demo/actions/diagnose      # 202 + run id
curl -s localhost:8099/v1/projects/demo/runs                          # see the run
```
Multi-tenant dev surface (token→tenant + admin): edit `api/server.py:main()` to serve
`build_tenant_router()` instead of `build_default_app()`, set `WS_ADMIN_TOKEN=...`, then
`POST /v1/tenants` (admin) to mint a tenant token. (The single-tenant app is the default; swapping is
one line.)

Knobs (env vars): `PORT`, `WS_API_TOKEN` (customer auth), `WS_REVIEWER_TOKEN` (ops approve),
`WS_ADMIN_TOKEN` (platform admin), `WS_ENFORCE_OWNERSHIP` (default on), `WS_ENFORCE_BILLING` (default
off), `WS_CLIENTS_ROOT` / `WS_TENANTS_ROOT` (data roots).

---

## Phase 1 — Make it durable: push + PR (do this first)

```sh
git -C /Users/ericliu/web-studio remote -v          # confirm a remote exists; if not, add one:
# git -C /Users/ericliu/web-studio remote add origin <git-url>
git -C /Users/ericliu/web-studio push -u origin saas-foundation
gh pr create --base main --head saas-foundation \
  --title "SaaS foundation: headless engine + multi-tenant control plane" \
  --body "See PRODUCT-PLAN.md, docs/ARCHITECTURE.md, docs/adr/0001+0002. 95 tests, full-funnel golden path."
```
Review the diff on GitHub. The branch is additive — it doesn't touch `studio.py` or `clients/`, so it
can merge without disrupting the live studio.

---

## Phase 2 — Confirm the real Claude build path (only you can do this)

This is the one thing the sandbox can't verify: that Claude actually drives a build via the Agent SDK.
```sh
pip install claude-agent-sdk          # the Agent SDK (extra: pip install -e '.[agent]')
! claude                              # authenticate the CLI it wraps (interactive)
AGENT_SDK_SMOKE=1 python3 tests/smoke_agent_sdk.py   # one tiny live turn → expects "PONG"
```
If green, the `AgentSDKDriver` path is real. Next, point a build at it: in `api/deps.py`, swap
`LocalClaudeDriver(...)` for `AgentSDKDriver(cwd=...)` and run one real `assemble` against a test
project. Expect token cost to show up in `GET …/usage`.

---

## Phase 3 — Lock the vendor choices (quick; ADR-0001 defaults in parens)

| Concern | Pick (recommended default) |
|---|---|
| Auth/token issuer | Clerk / Auth0 / Supabase Auth — issues the tenant bearer; feeds `POST /v1/tenants` |
| Database | **Postgres** (Neon/Supabase/RDS) |
| Object storage | **Cloudflare R2** (zero-egress, same vendor as Pages) |
| Durable workflow engine | **Temporal** (or Inngest for managed) |
| Build sandbox | **Fly Machines** (or E2B / Cloud Run jobs) |
| Payments | **Stripe** |
| Hosting (control plane) | a small VM/container (Fly/Render/Railway) running FastAPI+uvicorn |
| Hosting (web app) | **Vercel** (or Cloudflare Pages) |

Record any deviations as a new ADR (`docs/adr/0003-*.md`).

---

## Phase 4 — Wire the production bindings (each is an isolated seam; add a test per swap)

Order them by what unblocks the most. Each lives behind an interface that's already tested with a
fake/dev impl, so the swap is local.

1. **Postgres state** (`engine/sql_store.py` is ready):
   - `pip install 'psycopg[binary]'` (extra `.[postgres]`).
   - In `api/deps.py`, replace `FilesystemProjectStore(root)` with
     `SqlProjectStore(psycopg.connect(DSN), placeholder="%s")` and `FilesystemRunStore` with
     `SqlRunStore(...)`. The SQL is already `ON CONFLICT`-portable; only the placeholder + JSONB type
     differ. Run `tests/test_store_conformance.py` pointed at Postgres to confirm parity.
2. **R2 artifacts**: implement `ArtifactStore` (engine/store.py) over S3/R2 (boto3 or aws sdk), and
   pass it as `artifacts_factory` to `SqlProjectStore`. (Today: in-memory/filesystem.)
3. **Durable runner**: implement `Runner` (engine/runner.py interface) over Temporal/Inngest so a
   crashed worker resumes (replaces `ThreadRunner`). Inject via `deps`.
4. **Sandboxed build worker** (`workers/`): run `AgentSDKDriver` inside an ephemeral per-tenant
   sandbox (Fly Machine), scoped creds + egress, torn down after. The control plane enqueues; the
   worker pulls the job and runs the agent.
5. **Stripe** (the last funnel gap, #8): add a `BillingProvider` seam in `engine/billing.py`
   (`create_checkout`, `parse_webhook`), replace the dev `billing/checkout` stub with a real Checkout
   session, and add a platform webhook (`POST /v1/billing/webhook`) that verifies the signature and
   flips the plan (`set_plan(..., PLAN_ACTIVE)`). Set `WS_ENFORCE_BILLING=1` to turn the paywall on.
6. **Auth**: front the API with the chosen vendor; map the vendor token → tenant in the
   `TenantStore.resolve_token` seam (or exchange vendor JWT → tenant bearer at the edge).
7. **Studio-owned deploy** (`Publisher`): implement a real `publish_preview` (wrangler/Pages API with
   the tenant's scoped token) to replace `UnconfiguredPublisher`.

Small backend follow-up (noted in `web/README.md` §2): move ops launch approve/reject to an admin
route for multi-tenant (tenant-scoped works single-tenant today).

---

## Phase 5 — Build the web app (`web/`, spec in `web/README.md`)

Needs a real Node environment (can't run in the current sandbox).
```sh
cd web && npx create-next-app@latest . --ts --app
```
Implement the funnel screens (web/README §1) calling the control-plane endpoints; the API contract +
each step's calls are already mapped there. Use the stage→screen table (§4) to drive UI. Keep the
tenant token server-side (httpOnly); never expose the reviewer/admin tokens to customer sessions.
Build the ops review console (§2) against `GET /v1/admin/launches` + approve/reject.

---

## Phase 6 — Deploy
1. **Control plane:** `pip install -e '.[api]'`, serve `create_fastapi_app(build_tenant_router())`
   with uvicorn behind TLS; set all `WS_*` env vars + DSNs/keys.
2. **Workers:** deploy the sandbox runner; point the durable engine at it.
3. **Web app:** deploy to Vercel; set `API_BASE_URL` + the auth vendor keys.
4. **Smoke the live funnel** end-to-end on a domain you own (mirror `tests/test_funnel.py` by hand).

---

## Phase 7 — Go-live checklist
- [ ] `tests/run_all.py` green in CI (add a GitHub Action running it).
- [ ] Live Agent-SDK build produces a real preview; cost shows in `GET …/usage`.
- [ ] Ownership verification works on a real DNS TXT / meta tag.
- [ ] Stripe test-mode checkout → webhook → plan flips → paywall lifts.
- [ ] Tenant isolation verified across two real tenants.
- [ ] Reviewer approval required before cutover; **DNS/indexable flip stays a human step** (Hard rule —
      never touch MX/SPF/DKIM/DMARC).
- [ ] Backups for Postgres + R2; per-tenant concurrency/token quotas set.

---

## The shortest path to "a customer can use it"
Phase 1 (push/PR) → Phase 2 (confirm Claude) → Phase 4.1 + 4.5 + 4.7 (Postgres, Stripe, real deploy) →
Phase 5 (web app) → Phase 6 (deploy). Everything else (R2, Temporal, sandbox hardening) can come after
a first paying customer, since the filesystem/thread/in-process impls work for low volume.
