# web/ — customer web app (funnel specification)

The self-serve product surface. **Next.js + TypeScript** (ADR-0001 §2), talking to the control-plane
API (`api/`). This file is the implementable spec, grounded in the product decisions (ADR-0002):
**nursery/small-shop commerce · self-serve build + human-reviewed launch · platform-managed+metered ·
free diagnostic → rebuild fee → hosting subscription.**

> Status: spec only. The UI isn't built here (Next.js needs a real dev environment to run/verify).
> Every funnel step below maps to a real control-plane endpoint; the ones the web app needs that
> **aren't built yet** are consolidated in §6 — that's the remaining API work.

All requests carry the tenant bearer token (`Authorization: Bearer <token>`); the `TenantRouter`
resolves it to the tenant and isolates data. `<slug>` is the project (one rebuild).

---

## 1 · The funnel (customer)

Each step: what the customer sees → the API call(s) → the gate. ✓ = endpoint exists; ⛏ = §6 gap.

### Step 0 — Sign up / workspace
```
┌──────────────────────────────────────────────┐
│  Rebuild your plant shop's website            │
│  [ Enter your website ]  → Start free check   │
└──────────────────────────────────────────────┘
```
- Account + tenant provisioning is external (the auth vendor issues the bearer token — ADR-0002 §3).
- ⛏ `POST /v1/tenants` (create tenant + issue token) is not built; tenants are seeded out-of-band today.

### Step 1 — Free diagnostic (the hook)  ✓ no paywall, no ownership
```
enter domain → "Analyzing yoursite.com…" (live) → verdict card
   Visual score 62/100 · Industry completeness: missing online ordering, …
   [ See the full report ]   [ Rebuild my site → ]
```
- `POST /v1/projects {slug, domain}` ✓ → create the project (stage `queued`).
- `POST /v1/projects/{slug}/actions/diagnose` ✓ → returns `202 + run`; poll `GET …/runs/{id}` ✓.
- Render `GET …/reports` ✓ (the diagnostic report). **Free**: `diagnose` is never gated.

### Step 2 — Paywall (decision #4)
```
┌── Rebuild yoursite.com ───────────────┐
│  One-time rebuild + hosting from $X/mo │
│  [ Pay & start the rebuild ]           │
└────────────────────────────────────────┘
```
- `POST /v1/projects/{slug}/billing/checkout` ✓ (dev stub; ⛏ production = Stripe Checkout + webhook).
- After payment the plan flips to `active`; `assemble` stops returning `402`.

### Step 3 — Verify ownership (gate before any scrape-heavy/build work)
```
Prove you own yoursite.com:  ( ) DNS TXT  ( ) meta tag  ( ) /.well-known file
   → shows the exact record/tag/file to add → [ Verify ]
```
- `POST /v1/projects/{slug}/ownership/challenge {method}` ✓ → instructions + expected value.
- `POST /v1/projects/{slug}/ownership/verify` ✓ → `200` verified / `422` not yet.

### Step 4 — Baseline + concept boards
```
"Studying your current site…"  → 3 concept boards (Classic · Confident · Bold)
   [thumbnail] [thumbnail] [thumbnail]   ( 🔥 push further )   [ Choose ]
```
- ⛏ `POST …/actions/baseline` (run the scrape ladder → `baseline-ready`) — **not built**; today nothing
  produces `baseline-ready` via the API (`assemble` assumes it).
- ⛏ `POST …/actions/intake-pack` (or folded into baseline) → generates concept boards + opens the
  concept decision.
- `GET …/decisions` ✓ lists the open concept decision; ⛏ `POST …/decisions/{n}/resolve {choice}` to
  record the pick — **not built** (only GET exists). ⛏ board screenshots need a static asset route.

### Step 5 — Prototype preview  ✓
```
"Building your prototype…"  → live preview at ws-<slug>.pages.dev  → [ Request changes ] [ Looks good → ]
```
- `POST /v1/projects/{slug}/actions/assemble` ✓ (gated: ownership ✓, paid plan ✓, stage ✓) → `202 + run`;
  poll the run; show `project.preview_url`.

### Step 6 — Edits (conversational)  ✓
```
"Make the hero bigger, add a shipping FAQ"  → [ Apply ]  → preview refreshes
```
- `POST /v1/projects/{slug}/edits {name, request}` ✓ (author the edit), then
  `POST …/actions/process-edits` ✓ → `202 + run`. List with `GET …/edits` ✓.

### Step 7 — Owner answers + deliverables (→ final build)
```
Questionnaire (22 Qs) · upload logo / product photos / hours → [ Finish my site ]
```
- ⛏ endpoints to submit owner answers + manage the deliverables list + upload assets — **not built**
  (the studio reads `owner-answers.txt` / `assets/` from disk; the SaaS needs upload/intake endpoints).
- `POST /v1/projects/{slug}/actions/finish` ✓ (stage `answers-received` → `final`).

### Step 8 — Request launch → reviewed → go live (decision #2)
```
[ Request launch ]  → "In review by our team"  → (approved) → prechecks → "Ready to go live"
```
- `POST /v1/projects/{slug}/launch/request` ✓ → pending. Reviewer approves (see §2).
- `POST /v1/projects/{slug}/actions/cutover` ✓ (gated: approved launch ✓, stage `final` ✓) → prechecks.
- The DNS/indexable flip stays a **guided human step** (studio Hard rule) — the UI shows the runbook,
  never touches MX/SPF/DKIM/DMARC.

---

## 2 · Ops review console (decision #2 — the human-reviewed launch)
A separate, reviewer-authenticated surface (uses the `reviewer_token`, not a customer token):
```
Pending launches:
  acme-orchids   prototype preview ↗   submitted 2h ago   [ Approve ] [ Reject … ]
```
- `POST …/launch/approve` / `…/launch/reject {note}` ✓ (require the reviewer bearer).
- ⛏ a **cross-tenant** pending-launch queue (`GET /v1/admin/launches?status=pending`) — **not built**;
  the per-tenant `TenantRouter` has no cross-tenant view yet. Ops needs one (or a separate admin app).

---

## 3 · Account: billing + usage
- `GET /v1/projects/{slug}/billing` ✓ (plan) · `GET …/usage` ✓ (cost + tokens rollup, for the
  metered model). ⛏ tenant-level billing/usage aggregation (vs per-project) once plan moves to tenant.

---

## 4 · Stage → screen mapping
The engine stage machine drives what the customer sees (poll `GET /v1/projects/{slug}` → `stage`):

| stage | customer screen |
|---|---|
| `queued` / `scraping` | "Analyzing / studying your site…" |
| `baseline-ready` | concept boards → choose |
| `prototype` / `awaiting-owner` | live preview · request edits · questionnaire |
| `answers-received` | "Finalizing your site…" |
| `final` | request launch |
| `cutover-checked` | guided go-live runbook |

---

## 5 · Build notes
- **Next.js (App Router) + TS.** Server components fetch the API with the tenant token (httpOnly
  cookie/session); never expose the reviewer token to customer sessions.
- **Status-driven + forgiving:** carry over the operator dashboard's render-invariant lesson — never
  destroy in-flight UI state on poll (a staged upload, typed text). Poll runs/stage; don't full-rebuild.
- **Auth:** vendor-issued token → exchanged for the tenant bearer; the API stays provider-agnostic.

---

## 6 · API gaps the web app needs (the remaining backend work)
Consolidated, actionable — these are control-plane additions, all decision-light + testable like the rest:
1. `POST /v1/tenants` — self-serve tenant signup + token issuance (Step 0).
2. `POST …/actions/baseline` — run the scrape ladder (`queued` → `baseline-ready`) (Step 4).
3. `POST …/actions/intake-pack` — generate concept boards + open the concept decision (Step 4).
4. `POST …/decisions/{n}/resolve {choice}` — record the concept pick (Step 4; GET already exists).
5. Asset/intake endpoints — upload owner answers, deliverables, logo/photos (Step 7).
6. Static asset route — serve concept-board screenshots + preview thumbnails (Step 4/5).
7. `GET /v1/admin/launches` — cross-tenant reviewer queue (Step 2 / §2).
8. Stripe integration — real `billing/checkout` + webhook (Step 2).

Items 2–4 + 7 are pure engine/API work (no external vendor) and the natural next backend increment.
