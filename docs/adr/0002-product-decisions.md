# ADR 0002 — Product decisions (beachhead, launch model, hosting, pricing)

**Status:** Accepted (2026-06-20). Supersedes the "leaning" notes in ADR-0001 §6 (#6–#9) and
PRODUCT-PLAN §6 for these four. Confirmed by the human.

## Decisions

1. **Beachhead vertical — small-shop commerce / nurseries.** Launch into the proven vertical
   (~26 existing clients, the ecommerce-catalog archetype, playbooks, and the catalog/correspondence
   machinery are battle-tested). The marketplace-seller (Etsy/eBay) import flow stays available but
   is not the launch wedge.

2. **Launch model — self-serve build, human-reviewed launch.** Customers drive
   diagnostic → concept → prototype → edits self-serve, but **a human reviewer approves before the
   site goes live**. Implication: a launch-review gate + an ops review surface; the automated cutover
   prechecks may run only once a launch is approved. (The DNS/indexable flip itself stays a human
   step regardless — studio Hard rule.)

3. **Hosting + Claude — platform-managed, metered.** The platform holds the Cloudflare + Claude
   credentials and meters usage into the price. Implication: usage metering (token/cost per run →
   per-project/per-tenant aggregates) is now a required capability; we carry COGS + abuse risk
   (ownership verification already gates that).

4. **Pricing — free diagnostic → one-time rebuild fee → hosting+edits subscription.** The diagnostic
   is the top-of-funnel hook; charge at the rebuild step, then a recurring hosting/edits plan.
   Implication: the paywall sits between diagnose and assemble; metering feeds plan limits/billing.

## Consequences (build order shifts)
- **Now buildable & testable (this/next increments):** the launch-review gate + cutover action
  (decision 2); usage metering (decisions 3 & 4); multi-tenancy (everything per-customer).
- **Web app (`web/`) funnel** is now specifiable: nursery-commerce onboarding → diagnostic (free) →
  paywall → ownership verify → concept boards → prototype → edits → **request launch → reviewer
  approves** → cutover prechecks → human go-live.
- **Still infra/credential-bound:** Postgres/R2/sandbox standup; the live Agent-SDK confirmation.
