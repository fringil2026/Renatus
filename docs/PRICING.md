# PRICING — placeholder copy (operator sets real numbers before launch)

The model (locked, ADR-0002 #4 / `engine/billing.py`): **free diagnostic → one-time rebuild fee →
recurring hosting + edits subscription.** The rebuild (`assemble`) is the first paid action; the
diagnostic is never gated.

> All `$X` / `[BRACKET]` values are placeholders. Set the real numbers in **Stripe** (Product +
> Price IDs) and paste them into the copy below + the paywall UI before public launch.
> Nothing here is a promise until you replace it.

## Placeholder numbers (fill these in)
| Line item | Placeholder | Stripe object | Notes |
|-----------|-------------|---------------|-------|
| Free diagnostic | **$0** | — | never charged; the hook |
| One-time rebuild fee | **$[REBUILD_FEE]** | one-time Price | charged when the rebuild starts |
| Hosting + edits subscription | **$[MONTHLY]/mo** (or $[ANNUAL]/yr) | recurring Price | starts after rebuild; hosting, edits, monitoring |
| (optional) Rush / extra revisions | **$[ADDON]** | one-time Price | if offered |

## Copy strings (drop-in)

### Landing (already live — reference)
> "Free diagnostic · we only rebuild sites their owners ask us to."

### Paywall card (funnel Step 2 — `web/app/projects/[slug]`)
**Headline:** Rebuild [domain]
**Subhead:** One-time rebuild of **$[REBUILD_FEE]**, then hosting + unlimited small edits from
**$[MONTHLY]/mo**. Cancel anytime.
**Bullets:**
- Complete rebuild to a modern, faster, mobile-first site
- You approve a private preview before anything goes live
- Hosting, security, and ongoing edits included in the subscription
**CTA:** `Pay & start the rebuild`
**Fine print:** Secure payment via Stripe. The subscription starts once your new site is approved
and live. See [Terms](/legal/terms).

### Stripe product/price descriptions
- **Product:** "[PRODUCT_NAME] — Website Rebuild"
  - **Price (one-time):** "One-time website rebuild fee"
  - **Price (recurring):** "Website hosting + edits — monthly"

### Paywall gate message (the `402` from `require_paid_plan`)
> "The diagnostic is free. Starting the rebuild requires payment — you'll approve a private preview
> before your new site ever goes live."

### Subscription / cancellation (account area)
> "You're on the [PLAN_NAME] plan — $[MONTHLY]/mo, includes hosting and edits. Cancel anytime; your
> site stays live through the end of the current billing period."

## Wiring checklist
- [ ] Create Stripe Products + Price IDs (test mode first); record IDs in the API env.
- [ ] Replace `$[…]` placeholders here and in the paywall UI with the Stripe numbers.
- [ ] Real Checkout session + `POST /v1/billing/webhook` (flips plan to `active`); set
      `WS_ENFORCE_BILLING=1` (TASKS.md item 4.5).
- [ ] Confirm the free diagnostic stays ungated end-to-end.
