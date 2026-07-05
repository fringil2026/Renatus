# SESSION LOG — web-studio → SaaS (Renatus)

> Running log for future sessions. Read this first to know what's done, what's in flight, and what's
> blocked on the operator. Repo: **github.com/fringil2026/Renatus** · branch: **saas-foundation**.
> Last updated: **2026-06-21**.
>
> 📋 **Open tasks live in `docs/TASKS.md`** — the living checklist, updated every time something
> completes. This log is the narrative; TASKS.md is the actionable to-do list.

---

## Locked decisions (2026-06-21)
- **Milestone:** full production infra before go-live (not the minimal "live ASAP" path).
- **Vendor stack (recommended defaults):** Neon Postgres · Cloudflare R2 · Stripe · Vercel (web) ·
  Render (control-plane API) · Clerk (auth) · Temporal/Inngest + Fly sandbox *later, at scale*.
- **Pricing:** deferred — placeholders in Stripe + paywall copy; real numbers before launch.
- **Outreach automation:** skipped for now (Apollo/Reply.io + segment deferred).

---

## ✅ Completed
- **SaaS backend foundation** (additive; `studio.py` + `clients/` untouched):
  headless engine + multi-tenant control-plane API (FastAPI); usage metering; paywall gate;
  human-reviewed launch gate; ownership verification; asset upload/serve; submit-answers endpoint;
  platform-admin tenant signup. **95 tests / 11 suites, full-funnel golden path.**
- **Web funnel app scaffolded** (`web/`, Next 16 + app router + Tailwind): landing (domain entry →
  free diagnostic), project page (live status/runs/reports/preview), server-side API client.
  Verified with `next build`.
- **Deploy configs:** `api/asgi.py` (uvicorn entrypoint), `render.yaml` (API blueprint).
- **Phase 1 — durability:** `gh` installed + authed as `fringil2026`; `main` + `saas-foundation`
  pushed; **PR #1 open** → https://github.com/fringil2026/Renatus/pull/1
- **Memory:** decisions recorded in `~/.claude/.../memory/web-studio-saas-decisions.md`.

---

## 🔄 In progress / blocked on operator
Each item below is an independent, already-tested seam — wired the moment its credential arrives.
- **Hosting live:** Render (API) + Vercel (web) accounts → public URLs. *Blocked: accounts/keys.*
- **Phase 2 — confirm real Claude build path:** `pip install claude-agent-sdk`, `claude` login,
  `AGENT_SDK_SMOKE=1 python3 tests/smoke_agent_sdk.py`. *Blocked: `claude` login.* (Only this proves
  builds actually run via the Agent SDK.)
- **Diagnostic engine live:** PageSpeed key + `playwright install chromium` + `wrangler login`.

---

## ⏭️ Next steps (sequenced — see docs/NEXT-STEPS.md for commands)
1. Get hosting live (Render + Vercel) → public funnel URL.
2. Phase 2: confirm Claude Agent-SDK build path; point one real `assemble` at it; cost shows in
   `GET …/usage`.
3. Phase 4 production seams (each behind a tested interface):
   - **4.1 Postgres** (`engine/sql_store.py` ready) — swap in via `api/deps.py`; run
     `tests/test_store_conformance.py` against Neon.
   - **4.2 R2 artifacts** — implement `ArtifactStore` over S3/R2.
   - **4.5 Stripe** — `BillingProvider` seam: real Checkout + webhook → flip plan; `WS_ENFORCE_BILLING=1`.
   - **4.6 Auth (Clerk)** — map vendor token → tenant in `TenantStore.resolve_token`.
   - **4.7 Publisher** — real `publish_preview` (wrangler/Pages) replacing `UnconfiguredPublisher`.
   - *(4.3 durable runner / 4.4 sandbox worker — later, at scale.)*
4. Phase 5: finish `web/` funnel screens (paywall/Stripe, ownership, concept boards, edits, launch,
   ops console) per `web/FUNNEL.md`.
5. Phase 6: deploy control plane + workers + web app; smoke the live funnel on an owned domain.
6. Phase 7: go-live checklist (CI green, live build w/ cost, ownership on real DNS, Stripe test→webhook,
   tenant isolation, reviewer-gated cutover, backups + quotas).

---

## What's needed from the operator
Tracked in **docs/WHAT-I-NEED-FROM-YOU.md** (+ generated PDF). Short version: `claude`/`wrangler`
logins + Playwright install (local); Render + Vercel + PageSpeed (hosting/diagnostic); Neon + R2 +
Clerk (prod infra); Stripe test keys (payments); pricing + legal pages before public launch.

---

## Hard rules (never violate — see CLAUDE.md)
- Never touch **MX/SPF/DKIM/DMARC** records.
- The DNS / indexable cutover flip stays a **human step**.
- Reviewer approval required before cutover.
- Branch stays **additive** to the live studio (`studio.py`, `clients/`).
