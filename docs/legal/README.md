# Legal pages — DRAFTS for operator review

These are **placeholder drafts**, not legal advice. They exist so the funnel has the pages it
needs (footer links, CAN-SPAM footer on outreach email) and so real review has a starting point.

**Before public launch you (the operator) must:**
1. Fill every `[BRACKET]` placeholder — legal entity name, physical mailing address, contact email,
   governing-law state, effective date.
2. Have a lawyer review Privacy + Terms (especially data handling, liability, and the
   website-rebuild service terms — this is a service business touching customers' domains).
3. Confirm the **CAN-SPAM physical postal address** used in outreach email footers matches a real
   monitored address.

| File | Purpose | Wired into |
|------|---------|-----------|
| `privacy-policy.md` | What data we collect (diagnostic scrapes, questionnaire answers, payment via Stripe), how it's used, retention, rights | `web/app/legal/privacy` |
| `terms-of-service.md` | Service terms for the rebuild + hosting subscription, ownership/authorization requirement, refunds, liability | `web/app/legal/terms` |
| `can-spam.md` | Required footer + compliance checklist for LP/prospect outreach email | outreach email templates |

The `.md` here is the **canonical review copy**. The Next.js pages under `web/app/legal/` render the
same text with a visible "DRAFT — pending legal review" banner until you remove it.
