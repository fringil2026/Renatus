# TASKS — living checklist (web-studio → SaaS / Renatus)

> **The one place that tracks what's left.** Update this file every time something completes:
> tick the box, move the line to **✅ Done** with a date, and add the next concrete step if one
> opens up. Companion docs: `SESSION-LOG.md` (narrative), `NEXT-STEPS.md` (commands),
> `WHAT-I-NEED-FROM-YOU.md` (operator credentials). Branch: **saas-foundation**.
> Last updated: **2026-06-29**.

How to use: an item is **[ ]** open, **[~]** in progress, **[B]** blocked (name the blocker),
**[x]** done (then move it down to ✅ Done with a date). Keep this list ordered by the shortest
path to "a customer can use it."

---

## 🔜 Open — do next (shortest path to a live, paying product)

### A · Get it online (operator — needs your accounts)
- [ ] **A.2 Vercel** — sign up, import repo, Root Directory = `web`, add env `API_BASE_URL`, deploy → `*.vercel.app` URL.
- [ ] **A.3 API host** (Render/Railway/Fly) — deploy repo via committed `render.yaml`; paste its URL into Vercel's `API_BASE_URL`.

### B · Make the diagnostic + rebuilds actually run (operator)
- [ ] **B.4 PageSpeed key** — create a free Google PSI key, hand it over (fixes unkeyed 429s).
- [ ] **B.5 Playwright Chromium** — `python3 -m playwright install chromium` on the host.
- [ ] **B.6 Claude login** — run `claude` and sign in so headless builds can run.
- [ ] **B.7 wrangler login** — `wrangler login` (your Cloudflare account) to publish rebuilt sites.

### Phase 2 · Confirm the real Claude build path (gated on B.6)
- [B] **Agent-SDK smoke test** — `pip install claude-agent-sdk` → `AGENT_SDK_SMOKE=1 python3 tests/smoke_agent_sdk.py` (expects "PONG"). *Blocked: `claude` login (B.6).*
- [ ] **Point a real build at it** — swap `LocalClaudeDriver` → `AgentSDKDriver` in `api/deps.py`; run one real `assemble`; confirm cost in `GET …/usage`.

### Phase 4 · Production bindings (each an isolated, pre-tested seam)
- [B] **4.1 Postgres** — `engine/sql_store.py` ready; swap stores in `api/deps.py`; run `tests/test_store_conformance.py` against the DB. *Blocked: Neon/Supabase DSN.*
- [B] **4.5 Stripe** — `BillingProvider` seam; real Checkout + `POST /v1/billing/webhook`; `WS_ENFORCE_BILLING=1`. *Blocked: Stripe test key + Price ID + webhook secret.*
- [ ] **4.7 Publisher** — real `publish_preview` (wrangler/Pages) replacing `UnconfiguredPublisher` (gated on B.7).
- [B] **4.6 Auth (Clerk/Auth0/Supabase)** — map vendor token → tenant in `TenantStore.resolve_token`. *Blocked: auth-vendor choice + keys.*
- [ ] **4.2 R2 artifacts** — implement `ArtifactStore` over S3/R2 *(can wait until after first customer)*.
- [ ] **4.3 Durable runner** — `Runner` over Temporal/Inngest, replacing `ThreadRunner` *(at scale)*.
- [ ] **4.4 Sandbox build worker** — run `AgentSDKDriver` in an ephemeral per-tenant sandbox (Fly) *(at scale)*.
- [ ] **Backend follow-up** — move ops launch approve/reject to an admin route for multi-tenant (per `web/README.md` §2).

### Phase 5 · Web funnel app (`web/`, spec in `web/README.md`)
- [ ] Build out funnel screens against the control-plane endpoints (stage→screen table §4); keep tenant token server-side (httpOnly).
- [ ] Build ops review console against `GET /v1/admin/launches` + approve/reject.

### Phase 6 · Deploy
- [ ] Control plane (uvicorn behind TLS, all `WS_*` env + DSNs/keys).
- [ ] Workers (sandbox runner; point durable engine at it).
- [ ] Web app to Vercel (`API_BASE_URL` + auth keys).
- [ ] Smoke the live funnel end-to-end on an owned domain.

### Phase 7 · Go-live checklist
- [ ] `tests/run_all.py` green in CI (add a GitHub Action).
- [ ] Live Agent-SDK build → real preview; cost in `GET …/usage`.
- [ ] Ownership verification on a real DNS TXT / meta tag.
- [ ] Stripe test checkout → webhook → plan flips → paywall lifts.
- [ ] Tenant isolation verified across two real tenants.
- [ ] Reviewer approval before cutover; DNS/indexable flip stays human (Hard rule — never touch MX/SPF/DKIM/DMARC).
- [ ] Backups for Postgres + R2; per-tenant concurrency/token quotas.

---

## 🧭 Decisions / legal / money (operator — no code, but needed before public launch)
- [ ] **Pricing numbers** — rebuild fee + subscription (for Stripe + paywall copy).
- [ ] **Legal pages** — Privacy + Terms + CAN-SPAM physical address (I draft; you own/review).
- [ ] **Domain (optional)** — buy + add Vercel's DNS record (`*.vercel.app` works without).
- [ ] **Budget ceilings** — Claude tokens / validation credits / hosting plans; I cap in code.
- [ ] **Launch segment + metro** for outreach (lean: nurseries / small commerce).

## 💤 Deferred (explicitly parked — see SESSION-LOG "Locked decisions")
- [ ] **Outreach automation** — Apollo/Reply.io sourcing adapter + segment (skipped for now).

---

## ✅ Done
- [x] **2026-06-21** SaaS backend foundation — headless engine + multi-tenant FastAPI control plane (metering, paywall, launch gate, ownership verify, asset upload/serve, submit-answers, tenant signup). 95 tests / 11 suites, full-funnel golden path.
- [x] **2026-06-21** Web funnel app scaffolded (`web/`, Next 16) — landing, project page, server-side API client; `next build` clean.
- [x] **2026-06-21** Deploy configs — `api/asgi.py` (uvicorn entrypoint) + `render.yaml` (API blueprint).
- [x] **2026-06-21** Phase 1 durability — `gh` installed/authed (`fringil2026`); `main` + `saas-foundation` pushed; **PR #1 open**.
- [x] **2026-06-21** Decisions recorded in memory + ADR-0001/0002.
