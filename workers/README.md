# workers/ — sandboxed build runners (scaffold)

Ephemeral, per-tenant sandboxes that run the actual Claude-driven build: the **Claude Agent SDK**
drives the `engine/` skills + the CLAUDE.md contract (scrape ladder → extract → assemble Astro →
parity loop → QA gate → `npm run build` → publish). Default provider: **Fly Machines** (ADR-0001 §5).

Hard requirements: no cross-tenant access, scoped egress, scoped credentials (a job gets only the
deploy token for its own Pages project), torn down after the job.

**Status:** scaffold only — not yet implemented. Built in Phase 2 (PRODUCT-PLAN §7); the Agent-SDK
spike is the Phase 0 milestone.
