# ADR 0001 — Foundational decisions for the SaaS build

**Status:** Accepted (defaults from PRODUCT-PLAN §6; revisit any line as we learn).
**Date:** 2026-06-19
**Context:** Implementation kickoff. PRODUCT-PLAN.md flagged 9 open decisions. To avoid blocking the
engine refactor (which is decision-independent), we lock each to its recommended default here. These
are reversible; an ADR-0002 supersedes any line if we change course.

## Decisions

1. **Repo shape — monorepo.** One repo, new top-level dirs: `engine/` (headless rebuild engine),
   `api/` (control-plane HTTP API), `web/` (customer app), `workers/` (sandboxed build runners),
   `infra/` (IaC/config), `docs/` (ADRs + specs). Keeps the doctrine + skills co-located with the
   product. The existing `studio.py` + `clients/` stay untouched and operational during the migration.

2. **Language split.**
   - `engine/`, `api/`, `workers/` → **Python** (matches the existing skills/scripts; lets the engine
     import the skill scripts directly). API framework: **FastAPI**.
   - `web/` → **Next.js + TypeScript** (the customer app).

3. **State store — Postgres + object storage, behind an interface.** The `ProjectStore` /
   `ArtifactStore` interfaces (this increment) abstract persistence. Dev/today: a filesystem impl over
   `clients/<slug>/`. Prod: Postgres (state) + S3-compatible object storage (artifacts: scrapes,
   assets, screenshots, `dist/`, concept boards). Object storage default: **Cloudflare R2** (same
   vendor as Pages, zero-egress).

4. **Orchestration — durable workflow engine.** Replace the in-memory driver thread + reaper +
   semaphore. Default: **Temporal** (durable, mature, self-hostable) with **Inngest** as the lighter
   alternative if we want managed + less ops. Decide at Phase 2 spike; the engine entrypoints are
   written to be callable from either.

5. **Sandboxing — ephemeral per-tenant build sandboxes.** Default provider: **Fly Machines** (fast
   boot, per-job, scoped). Alternatives kept open: E2B, Cloud Run jobs. Hard requirements: no
   cross-tenant access, scoped egress, scoped credentials, torn down after the job.

6. **Claude integration — platform-owned, metered, via the Claude Agent SDK.** "Claude-integrated"
   should feel built-in: the platform holds the API keys and meters token usage into billing. Default
   to the **latest, most capable model** (currently the Fable 5 / `claude-fable-5` tier) for the build
   agent; cheaper tiers (Haiku/Sonnet) for mechanical sub-steps (extraction, classification). A
   BYO-key power-user tier is a later option. (Confirm model IDs against the `claude-api` reference at
   build time.)

7. **Hosting — customer-owned Cloudflare via OAuth for launched sites; platform-owned for previews.**
   Throwaway previews deploy to a platform Pages account; at launch we deploy into the customer's own
   Cloudflare (cleaner ownership + their billing). Per-project Pages model is preserved either way.

8. **Beachhead vertical — proven commerce (small-shop / nursery ecommerce), with marketplace sellers
   (Etsy/eBay) as the self-serve wedge.** The catalog/correspondence machinery + the import flow are
   battle-tested here. Horizontal expansion later via auto-generated playbooks.

9. **Pricing — free diagnostic (funnel top) → paid rebuild; subscription for hosting + edits.** Final
   numbers TBD once COGS (Claude tokens + sandbox compute) are measured. Metering is built in from
   Phase 2 so pricing can follow data.

10. **Ownership verification — required before any scrape-heavy or launch step.** Support at least one
    of: DNS TXT record, a verification meta tag, or host OAuth. Spec to be written before Phase 3.
    This is the gate everything expensive/destructive sits behind.

## Consequences
- The engine refactor (Phase 1) can proceed now — it depends on none of the vendor choices (4, 5, 7),
  only on the storage *interface* (3).
- Vendor spikes (Temporal/Inngest, Fly/E2B) happen at their phases; the interfaces keep them swappable.
- `studio.py` remains the live operator tool until the new control plane reaches parity; we do not
  break it mid-migration.
