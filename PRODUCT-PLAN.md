# PRODUCT-PLAN.md — Web Studio → Claude-integrated SaaS

**Status:** DRAFT brain-dump + action plan. This is the "write everything down first" doc. Once it
reads right, we carve it into a phased build (issues/milestones) and start structuring the website.

**The one-line vision:** turn the internal, single-operator Web Studio into a self-serve product
where a business owner enters their own website, and Claude rebuilds it — diagnostic → concept →
prototype → edits → launch — with the same quality doctrine the studio already enforces, but with
zero operator in the loop.

---

## 1 · Where we are today (honest inventory)

The studio today is an **artisan tool for one operator**, not a product:

- **`studio.py`** (3.4k LOC) — a single-process Python HTTP dashboard at `localhost:8788`. Shared
  token auth, ~20 `/api/*` endpoints, an in-memory driver thread + a "reaper" loop for builds, a
  concurrency semaphore (`MAX_CLAUDE_JOBS=2`). One operator, one machine.
- **State lives in the filesystem.** Every client is `clients/<slug>/` with `status.json` as the
  source of truth and filename-as-state conventions (`NNN-PENDING-…` edits, `NNN-OPEN-…` decisions/
  incidents, `reports/`). Elegant for one operator; not multi-tenant, not concurrent-safe across
  machines, not queryable.
- **The engine is `claude -p` subprocesses.** Heavy work (assemble, full-build, overhaul, diagnostic)
  is spawned as headless Claude Code jobs on the operator's authed machine, reading the skills and
  CLAUDE.md contract. The operator's own Claude + Cloudflare + (rehearsal) Stripe/Supabase/Resend
  credentials do the work.
- **The real assets (the crown jewels):**
  - **Skills** (`.claude/skills/`): `site-baseline` (the 5-rung scrape ladder + extractors),
    `apply-intake`, `cutover`, `site-diagnostic` — Python scripts + model instructions.
  - **Archetypes** (`templates/`): `ecommerce-catalog`, `nerc-cip-base`, `intake-template` — Astro 5 +
    Tailwind 4 static sites with component catalogs.
  - **Playbooks** (`playbooks/`): industry-specific build/diagnostic standards, auto-generated as new
    industries appear.
  - **The doctrine** (CLAUDE.md + SYSTEM.md): parity verification loop, Design QA gate, purpose-first
    reconstruction, product correspondence, decision/incident/report conventions, rehearsal mode,
    creativity tiers, the publish-always rule. *This is what makes the output good.*
- **Deploy model:** per-client Cloudflare Pages project `ws-<slug>`; previews are permanently
  noindex; launch is a separate human-gated cutover (DNS, with email-DNS untouchability as a hard rule).
- **Existing cloud plan** (`deploy/MIGRATION.md`): lift-and-shift to a Hetzner VPS + ttyd web
  terminal + Cloudflare Access. **Still single-operator.** This product plan supersedes that for the
  SaaS goal (the VPS plan remains valid as an interim "always-on for me" step).
- **~26 active clients**, almost all orchid/plant nurseries (ecommerce-catalog). The catalog/
  correspondence machinery is battle-tested on a real vertical.

**Takeaway:** we have a proven *rebuild engine and quality system*. We do **not** have any of the
SaaS scaffolding (accounts, multi-tenancy, durable orchestration, customer UX, billing, ownership
enforcement, isolation). The work is to wrap the engine in a real product, not to reinvent the engine.

---

## 2 · The gap: tool → product

| Concern | Today (single-operator tool) | Needed (multi-tenant SaaS) |
|---|---|---|
| Identity | one shared `STUDIO_TOKEN` | real accounts, orgs, roles, SSO-ready |
| Tenancy | one operator owns all `clients/` | hard tenant isolation; a customer sees only their sites |
| State | `status.json` + filenames on disk | Postgres (queryable, transactional) + object storage |
| Orchestration | in-memory thread + reaper + semaphore | durable job/workflow engine, horizontally scalable |
| Compute | `claude -p` on operator's machine | sandboxed per-tenant build workers (isolated, ephemeral) |
| Claude access | operator's personal Claude login | platform-owned API keys via the Claude Agent SDK, metered |
| Secrets | operator's Cloudflare/Stripe/Resend creds | per-tenant credential vault; platform creds for shared infra |
| UX | operator dashboard (dense, expert) | customer funnel (guided, forgiving, status-driven) |
| Authorization | operator only rebuilds sites they/clients own | **programmatic domain-ownership verification** (critical) |
| Billing | none | Stripe plans + usage metering (Claude tokens are the cost driver) |
| Abuse/safety | trusted operator | public input = scraping/copyright/abuse surface to defend |
| Deploy | operator runs `wrangler` | platform-managed deploys + customer-domain cutover flow |

---

## 3 · Target architecture (proposed)

A clean separation: **a thin product layer** (accounts, UI, billing, orchestration) **wrapping a
headless rebuild engine** (the existing skills + doctrine), with **per-tenant sandboxed workers**
doing the actual Claude-driven builds.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Customer web app (Next.js/React)                                     │
│   signup → verify ownership → diagnostic → concept boards → prototype │
│   → edits → review/approve → publish → launch (cutover)               │
└───────────────┬─────────────────────────────────────────────────────┘
                │ HTTPS / authed API
┌───────────────▼─────────────────────────────────────────────────────┐
│  Control plane (API + orchestrator)                                   │
│   Auth · Tenancy · Billing/metering · Job/workflow engine ·           │
│   Project state (Postgres) · Object storage (R2/S3) · Webhooks        │
└───────────────┬─────────────────────────────────────────────────────┘
                │ enqueue durable workflows (assemble, full-build, edit, diagnostic)
┌───────────────▼─────────────────────────────────────────────────────┐
│  Build workers — ephemeral, per-tenant sandboxes                      │
│   Claude Agent SDK drives the SKILLS + CLAUDE.md contract:            │
│   scrape ladder · extract · assemble Astro · parity loop · QA gate    │
│   npm build · publish to Cloudflare Pages                             │
│   (no network/credential access beyond what the job needs)            │
└───────────────┬─────────────────────────────────────────────────────┘
                │ deploy
┌───────────────▼─────────────────────────────────────────────────────┐
│  Hosting — per-customer Cloudflare Pages project + custom domain      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.1 The rebuild engine, made headless
The single most important refactor: **decouple the skills/scripts from operator/filesystem
assumptions** so they run as a parameterized service.
- Replace direct `clients/<slug>/...` filesystem reads/writes with a **storage interface**
  (`ProjectStore`) that today can be filesystem (dev) and in prod is Postgres + object storage. The
  filename-as-state conventions become rows/enums; artifacts (scrapes, assets, `dist/`) become object
  storage blobs.
- Each skill becomes invokable with an explicit context (tenant id, project id, paths/handles) rather
  than "the cwd is a client folder."
- The CLAUDE.md contract stays the brain of the build agent — it's loaded into the worker's Claude
  Agent SDK system context. (We just shrank it ~20%; keep it tight — it's loaded every build.)

### 3.2 Claude integration (the "Claude-integrated" core)
- Use the **Claude Agent SDK** to run each rebuild as an agent that has the skills as tools and the
  CLAUDE.md doctrine as its operating contract. Default to the **latest, most capable model**
  (currently the Claude Fable 5 / `claude-fable-5` tier; revisit per the `claude-api` reference at
  build time). Cheaper tiers (Haiku/Sonnet) for mechanical sub-steps (extraction, classification) to
  control cost.
- **Token cost is the primary variable cost** — meter per project/build and surface it in billing.
- Builds are **long-running and multi-step** → model them as durable workflows (next section), not a
  single API call. The existing `full-build-progress.json` resumable step artifact is literally a
  hand-rolled durable workflow; formalize it.

### 3.3 Orchestration
Replace the in-memory driver thread + reaper + `CLAUDE_SEM` with a **durable workflow engine**
(candidates: Temporal, Inngest, or a queue+workers with a state machine in Postgres). Map directly:

| Today | Becomes |
|---|---|
| `status.json` stage machine | a workflow state machine per project |
| `full-build-progress.json` resumable steps | durable workflow steps (auto-resume on worker crash) |
| `version_reaper_loop()` auto-resume | the engine's built-in retry/recovery |
| `CLAUDE_SEM` / `MAX_CLAUDE_JOBS` | per-tenant + global concurrency limits / rate limits |
| `is_transient_failure()` pause-vs-fail | retry policy (backoff on rate/budget; terminal on real) |
| decisions inbox (human fork) | a workflow "wait for human signal" + a UI task |

### 3.4 Sandboxing (non-negotiable for a public product)
Builds run scraping, `npm install`, and code generation — untrusted-ish and per-tenant. Each build
runs in an **ephemeral isolated sandbox** (candidates: Fly Machines, E2B, Cloud Run jobs, Firecracker
microVMs, or gVisor containers). Properties: no access to other tenants' data, scoped egress, scoped
credentials (a job gets only the deploy token for its own Pages project), torn down after the job.

### 3.5 Data model (first sketch)
- `organizations`, `users`, `memberships` (roles: owner/admin/member)
- `projects` (the unit of work — one website rebuild): `org_id`, `domain`, `ownership_status`,
  `stage`, `archetype`, `playbook`, `design_mode`, `catalog_source/owner`, timestamps
- `runs` (a workflow execution: diagnostic / assemble / full-build / edit-batch / cutover): status,
  steps[], token_usage, logs ref
- `edits`, `decisions`, `incidents`, `reports` (the filename-state conventions become tables; status
  enums replace filename suffixes; immutability becomes an append-only/no-update rule)
- `artifacts` (object-storage pointers: scrapes, assets, screenshots, `dist/`, concept boards)
- `versions` (multi-version builds: idx, mode, preview_url, chosen)
- `deployments` (Pages project, preview_url, custom_domain, indexable, launched_at)
- `credentials` (per-tenant, encrypted: their Cloudflare/Stripe/Resend/GA4 when they bring their own)
- `usage_events` (token + build metering → billing)

### 3.6 Hosting & deploy
- Keep the **per-project Cloudflare Pages** model (already proven). Platform owns the Cloudflare
  account or, better, deploys into **the customer's own Cloudflare** via OAuth (cleaner ownership +
  billing). Decision in §6.
- Previews stay permanently noindex. **Launch/cutover** is a guided, human-confirmed flow — the
  email-DNS untouchability hard rule becomes an explicit product guardrail (we never touch MX/SPF/
  DKIM/DMARC; the UI walks them through only the records that matter and refuses the rest).

---

## 4 · The customer journey (product funnel)

This is the website we'll structure. Each step maps to existing engine capability.

1. **Sign up / create org.** Email + OAuth. Pick a plan (or free diagnostic).
2. **Enter your domain.** → runs the **site-diagnostic** engine (already exists): a two-axis,
   industry-aware rebuild verdict + top problems. *This is the hook/lead-gen — it's the same engine
   the outreach pipeline uses, pointed at self-serve.* Free or low-cost.
3. **Verify ownership.** Before any deeper scrape or build: prove they control the domain (DNS TXT
   record, a meta tag, or host OAuth). **Gate everything destructive/expensive behind this.**
4. **Baseline + concept boards.** The scrape ladder runs; we present 3 concept boards across the
   creativity spectrum (A classic / B confident / C bold) + the optional 🔥 push-further and 🎨
   creative overhaul. Customer picks a direction.
5. **Prototype.** Assemble to the chosen concept; parity floor + Design QA gate + verification loop
   run automatically. Customer gets a live private preview URL.
6. **Edits.** Conversational change requests → the edit ledger → reprocessed → preview refreshes.
   (The customer talks; Claude authors the structured edit, shows it, applies it.)
7. **Owner answers / deliverables.** The questionnaire becomes an in-app form; uploads (logo, photos,
   copy, integrations) flow into the deliverables tracker. Marketplace sellers can import an Etsy/eBay
   export instead of a scrape (owner-authorized only).
8. **Backend (commerce).** For shops: configure backend (Supabase/Stripe/Resend) — rehearsal/TEST
   mode first, then swap to their real accounts (the un-rehearsal checklist).
9. **Review & approve.** A clear FOR-REVIEW list (unverified facts, image provenance, blanks). Nothing
   launches with fabricated facts or unprovenanced images — the honesty rules become product policy.
10. **Publish / launch.** Cutover prechecks (launch_check / redirect_check / zone_diff) run; the
    customer confirms; we flip indexable + guide the DNS switch. Redirects at the edge, never in JS.
11. **Post-launch.** Ongoing edits, analytics handoff (reuse their existing GA4), support.

---

## 5 · What we preserve vs rebuild

**Preserve (the moat — do not rewrite):**
- All four skills + their Python scripts (scrape ladder, extractors, diagnostic, cutover checks).
- The archetypes + component catalogs + playbooks.
- The doctrine in CLAUDE.md/SYSTEM.md (parity loop, QA gate, purpose-first, correspondence, honesty/
  provenance, rehearsal, creativity tiers, publish-always, decisions/incidents/reports).
- The per-project Cloudflare Pages deploy pattern.

**Rebuild / replace:**
- `studio.py` → split into (a) a real backend API + (b) a customer web app + (c) a workflow
  orchestrator. Its *logic* (stage gates, full-build chain, publish net, resume, concurrency, version
  builds) is the spec for the new orchestrator — port the behavior, drop the single-process form.
- Filesystem state → Postgres + object storage behind a `ProjectStore` interface.
- `claude -p` on the operator's box → Claude Agent SDK in per-tenant sandboxes with platform API keys.
- Shared token auth → real auth + multi-tenant authorization.

**New (didn't exist):**
- Accounts/orgs/billing/metering, ownership verification, sandbox infra, customer UX, abuse defense,
  observability/support tooling.

---

## 6 · Open product decisions (resolve before/at structuring)

These genuinely change the build; capture answers here, then proceed.

1. **Whose Cloudflare/hosting?** Platform-owned (simplest UX, we carry hosting cost + risk) vs deploy
   into the **customer's own Cloudflare via OAuth** (cleaner ownership/billing, more setup friction).
   *Leaning: customer-owned via OAuth for launched sites; platform-owned for throwaway previews.*
2. **Whose Claude?** Platform API keys, metered into the price (recommended — "Claude-integrated"
   should feel built-in) vs BYO-key power-user tier.
3. **Pricing shape.** Free diagnostic → one-time rebuild fee, or subscription (hosting + edits), or
   usage-based? (Token cost + build compute are the COGS to cover.)
4. **Self-serve vs assisted.** Fully self-serve, or "Claude builds, a human reviews before launch"
   (higher trust, higher cost)? Could be tiered.
5. **Ownership verification method(s).** DNS TXT / meta tag / host OAuth — which to support at launch?
   (At least one is mandatory before scrape-heavy or launch steps.)
6. **Vertical focus at launch.** Start where we're strong (ecommerce-catalog / nurseries +
   small-shop commerce) or go horizontal? *Leaning: launch the proven commerce vertical first.*
7. **Marketplace sellers as a wedge.** Etsy/eBay sellers with no real site are a clean, high-intent
   self-serve segment (import flow already exists). Possibly the best beachhead.
8. **Build stack for the product layer.** Next.js + (FastAPI or Node) + Postgres + R2; workflow engine
   (Temporal/Inngest); sandbox provider (Fly/E2B/Cloud Run). Pick once, in Phase 0.
9. **Where the engine refactor happens.** Same repo (monorepo: `engine/`, `api/`, `web/`,
   `workers/`) vs split repos. *Leaning: monorepo to keep the doctrine + skills co-located.*

---

## 7 · Phased action plan

Each phase ends with a demoable milestone. Phases 0–1 are mostly refactor (low external risk); the
SaaS surface accretes from Phase 2.

### Phase 0 — Foundations & decisions (1–2 wks)
- Resolve the §6 decisions (at least: stack, hosting model, Claude model/billing, ownership method,
  beachhead vertical).
- Stand up the monorepo skeleton (`engine/`, `api/`, `web/`, `workers/`, `infra/`).
- Choose + spike the workflow engine and the sandbox provider with a hello-world build.
- **Milestone:** a written architecture decision record (ADR) + a sandbox that can `npm run build` an
  Astro archetype and deploy a preview, driven by the Agent SDK.

### Phase 1 — Headless rebuild engine (2–4 wks)
- Introduce the `ProjectStore` interface; make the skills/scripts read/write through it instead of raw
  `clients/<slug>/` paths. Filesystem impl for dev parity; the conventions become typed state.
- Wrap "assemble prototype", "process edits", "site-diagnostic" as **engine entrypoints** callable
  with explicit context — no operator dashboard, no cwd assumptions.
- Port the build agent to the **Claude Agent SDK** with CLAUDE.md as system context and skills as
  tools; verify the parity loop + QA gate still run and pass on a known client.
- **Milestone:** one existing orchid client rebuilt end-to-end by the headless engine in a sandbox,
  preview published, parity checklist green — with zero `studio.py`.

### Phase 2 — Multi-tenant control plane (3–5 wks)
- Postgres data model (§3.5) + object storage; migrate the filename-state conventions to tables.
- Auth + orgs + tenancy isolation; the durable workflow orchestrator replacing the in-memory driver.
- Per-tenant sandboxed workers with scoped credentials; concurrency/rate limits.
- **Milestone:** two isolated test orgs each run a rebuild concurrently; crash-a-worker → workflow
  resumes; no cross-tenant leakage.

### Phase 3 — Customer web app (3–5 wks)
- The funnel (§4): signup → diagnostic → **ownership verification** → concept boards → prototype →
  edits → review → preview. Status-driven, forgiving UX (the operator dashboard's render-invariant
  lesson — never destroy in-flight UI state — carries over).
- In-app questionnaire + deliverables uploads; conversational edits.
- **Milestone:** a non-technical tester takes their own (owned) domain from signup to an approved
  private preview without help.

### Phase 4 — Commercial layer (2–3 wks)
- Stripe plans + usage metering (token + build COGS); quotas/limits; plan gates.
- The commerce-backend flow productized (rehearsal → un-rehearsal swap), if commerce is in launch scope.
- **Milestone:** a paying test customer completes a rebuild within plan limits; usage + invoice correct.

### Phase 5 — Launch/cutover + trust + scale (3–5 wks)
- Productized cutover: prechecks in-app, guided DNS, indexable flip, redirect-at-edge — with the
  email-DNS untouchability guardrail enforced in UI.
- Abuse defense (rate limits, ownership gating, copyright/honesty policy, takedown path),
  observability (per-run tracing, token dashboards), support/incident tooling (the incident
  convention → a support surface).
- **Milestone:** a customer launches a rebuilt site onto their real domain through the product;
  on-call can trace any failed run.

### Phase 6+ — Expand
- More archetypes/verticals (auto-playbook generation already supports this), team features,
  white-label/agency tier, the outreach engine as a growth loop (diagnose prospects → invite to
  self-serve).

---

## 8 · Risks & how we defend

| Risk | Defense |
|---|---|
| **Abuse: rebuilding sites the user doesn't own** (copyright, scraping ToS) | Mandatory ownership verification before scrape-heavy/launch steps; honesty/provenance rules as policy; takedown path; the existing "never scrape other sellers / never bot-scrape marketplaces" boundary becomes platform terms. |
| **Cost blowups** (Claude tokens, build compute) | Per-tenant quotas + global limits (port `CLAUDE_SEM`); meter and cap; cheaper models for sub-steps; the 5-iteration parity cap already bounds loops. |
| **Tenant isolation / data leakage** | Ephemeral per-tenant sandboxes, scoped creds + egress, row-level tenancy in Postgres, no shared mutable filesystem. |
| **Build quality regression at scale** | The parity verification loop + Design QA gate are automated gates — keep them mandatory; track green-rate as a product SLO. |
| **Long-running builds / flakiness** | Durable workflows with resume (formalizing today's resumable artifacts) + transient-vs-terminal failure policy. |
| **DNS/email mistakes at cutover** | Email-DNS untouchability hard rule in UI; redirects at edge only; prechecks must pass; human-confirmed launch. |
| **Fabricated facts reaching a live site** | DRAFT/FOR-REVIEW model + provenance gating already block this; surface it prominently as the approval step. |
| **Vendor lock-in** (workflow/sandbox/host) | Keep the engine portable behind interfaces; the `ProjectStore` + entrypoint boundaries make swaps possible. |

---

## 9 · Cost model (rough, to refine)
- **Variable COGS per rebuild:** Claude tokens (dominant) + sandbox build minutes + storage + (if
  platform-hosted) Pages bandwidth. The diagnostic is cheap; full creative + commerce builds are the
  expensive end.
- **Fixed:** control-plane infra (Postgres, orchestrator, web), observability, support.
- **Implication:** price the rebuild to clear token+compute COGS with margin; consider a low-cost/free
  diagnostic as the funnel top and charge at prototype/launch.

---

## 10 · Immediate next steps (to start "structuring as a website")
1. **Lock the §6 decisions** (especially: beachhead vertical, hosting/Claude ownership, pricing shape,
   stack). I can turn each into a short decision card if useful.
2. **Phase 0 kickoff:** monorepo skeleton + the Agent-SDK-in-a-sandbox spike (proves the engine runs
   headless and can deploy).
3. **Design the customer funnel UI** (§4) as wireframes — this is the "website for customers" the
   request points at; the funnel is the product.
4. **Write the ownership-verification spec** — it's the gate everything else depends on.

> Once these are settled, the next doc is the website information architecture + funnel wireframes,
> then we scaffold `web/` and `api/`.
