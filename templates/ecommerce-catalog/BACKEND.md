# BACKEND.md — commerce backend baseline (Phases 2–4)

BINDING blueprint for the Supabase/Stripe/Resend backend of EVERY client built from the
ecommerce-catalog archetype. Phases 2–4 implement this; a client's binding spec references it.
Item-integrity by construction: one record per thing, every surface reads it. No page builder —
owners edit FACTS and CONTENT, never layout/spacing/color/font.

## Necessity tiers (every item below is tagged)
- **[REQUIRED]** — always built, never toggleable. Safety rails are not a customer choice.
- **[EVIDENCED]** — built automatically when the feature census, binding spec, or playbook shows
  the need; carries its evidence citation.
- **[JUDGMENT]** — recommended ON or OFF per client with a one-line reason; owner-overridable.
- **[DEFERRED]** — off unless explicitly requested (section H).

**Baseline rule:** everything REQUIRED or EVIDENCED is INCLUDED by default; JUDGMENT applies only
to the additionals. A client can end up with LESS than the full baseline, but NEVER less than
their evidence. The per-client decision set is recorded in `02-intake/backend-config.yaml`
(see CLAUDE.md "Propose backend config"); once BINDING, Phase 2+ implements exactly its ON set.

Each item notes the deliverables §2.7 fact that unblocks it, or marks itself `(self-contained)`.

---

## A. Auth & safety rails — everything depends on it
- **[REQUIRED]** Owner login: Supabase Auth, magic-link default, single `owner` role now, schema
  ready for `staff` later. — *D-2.7.2 (Supabase)*
- **[REQUIRED]** RLS on every table: public reads ACTIVE products only; ALL writes require the
  authenticated owner. — *D-2.7.2*
- **[REQUIRED]** Admin audit log: every change records who / what / when / old→new. — *(self-contained)*
- **[REQUIRED]** Secrets per the credentials convention; webhook signature verification;
  idempotency keys on anything Stripe-triggered. — *D-2.7.1 (Stripe)*

## B. Catalog & inventory — daily-use core; effortless on a phone
- **[EVIDENCED]** The catalog + inventory module itself. — *census: product card / category nav (CARRY-OVER); spec data model*
- Complete product record (every field the admin edits):
  - **[EVIDENCED]** Identity: genus, species, common name, SKU (auto-suggested, editable), slug
    (auto, LOCKED after first publish — edge redirects protect old ones). — *spec data model*
  - **[EVIDENCED]** Commerce: price, compare-at price (sale display), private cost field (margin
    math, NEVER rendered), currency, max-quantity-per-order, weight/size for shipping calc,
    pot/plant size as a displayed attribute. — *spec; shipping needs D-2.7.5*
  - **[EVIDENCED]** Inventory: `stock_qty` (inline +/- from the list) PLUS an explicit
    availability status that OVERRIDES quantity — in-stock / out-of-stock / coming-soon /
    discontinued (qty>0 can be held; qty=0 discontinued ≠ qty=0 restocking). Per-product
    low-stock threshold → owner alert. Per-product Conservatory toggle (when out: SHOW (default)
    or HIDE). Optional expected-restock date (renders on the Conservatory card). Auto-OOS on
    webhook decrement. — *census: Conservatory + notify; spec*
  - **[EVIDENCED]** Content: description, care (light/water/temp), difficulty, bloom_now, origin,
    tags, related-products picks, per-photo ALT TEXT, photo ordering (first = primary), per-product
    meta description (auto, overridable). — *spec*
  - **[JUDGMENT]** Merchandising: featured flag + manual sort pinning. *(on — cheap, high control)*
- **[REQUIRED]** Photo upload → Storage with automatic resize variants (hero/card/thumb generated,
  dimensions recorded) — imagery ground rule 4 enforced at UPLOAD, not at build. — *(self-contained)*
- **[EVIDENCED]** Categories (genus auto-derived) + manual tags. — *census: category/genus nav*
- **[JUDGMENT]** Bulk CSV import/export. *(on if the owner has many SKUs; else off)*
- **[REQUIRED]** Draft / active / archived states; one products record, every surface reads it. — *(self-contained)*

## C. Content blocks — owner edits designated blocks, never design (never a page builder)
- **[EVIDENCED]** `site_content` table: `block_key` (the PURPOSE name from the block-purpose map)
  → content → updated_at/by. — *01-baseline/block-purpose-map.md*
- Editable set (each block JUDGMENT unless its feature is evidenced):
  - **[JUDGMENT]** Announcement banner (on/off + scheduled start/end). *(on — owners want this)*
  - **[EVIDENCED]** Specimen-of-the-Week selection. — *Hero exists*
  - **[JUDGMENT]** Business hours + holiday closures (feeds the hours notice AND LocalBusiness
    schema). *(on if a physical/visitable location; else off)*
  - **[JUDGMENT]** About/story text, FAQ entries, shipping policy text, featured-products picks,
    social links, legal-page blocks (privacy / terms / refund & live-plant guarantee). *(on)*
  - **[EVIDENCED]** WORDING of transactional emails (back-in-stock, order acknowledgment) — words
    editable, sending machinery never. — *census: notify capture; D-2.7.3*
- **[REQUIRED]** Components read blocks from the DB with committed static content as FALLBACK;
  admin lists blocks BY PURPOSE NAME with a preview of where each appears. — *(self-contained)*

## D. Orders & fulfillment
- **[EVIDENCED]** `orders` table fed by the Stripe webhook (line items, amounts, shipping address,
  status: new → packed → shipped); order detail view + search. — *census: cart/checkout; D-2.7.1*
- **[EVIDENCED]** Weather-hold flag per order; refunds/disputes DEEP-LINK to Stripe (never rebuild
  what Stripe does better). — *spec (live plants); D-2.7.1*
- **[EVIDENCED]** Owner notification email on each new order. — *D-2.7.3 (Resend)*

## E. Customers & communications
- **[EVIDENCED]** `notify_requests` management: per-product pending counts (demand signal),
  send-on-restock once per subscriber, one-click unsubscribe tokens. — *census: notify capture; D-2.7.3*
- **[EVIDENCED]** Customer records accumulated from orders (guest checkout default). — *census: cart*
- **[JUDGMENT]** Newsletter list as a separate CONSENTED table; data-deletion path documented.
  *(on if the owner will actually send; else off — don't collect what you won't use)*
- **[EVIDENCED]** Email routing: per-form destinations (contact → owner inbox; wholesale/special →
  optionally different; new-order → owner inbox, multiple recipients ok); customer-facing mail
  sends FROM the verified domain (Resend) with reply-to = owner's real inbox; we ROUTE to their
  existing email, NEVER host or alter it (MX/SPF/DKIM/DMARC are never touched — hard rule). — *D-2.3.1, D-2.7.3*
- **[EVIDENCED]** Turnstile (NEW keys per client) + honeypot on public forms. — *census: contact form*
- **[JUDGMENT]** Optional auto-acknowledgment to the customer, owner-toggleable. *(on)*

## F. Store settings
- **[EVIDENCED]** Shipping zones + rates + handling time; heat-pack add-on (line item, price
  editable); free-shipping threshold. — *spec (live-plant policy); D-2.7.5*
- **[JUDGMENT]** Local-pickup toggle + pickup instructions. *(off unless the owner offers pickup)*
- **[EVIDENCED]** Tax via Stripe Tax (never hand-roll). — *D-2.7.1*
- **[JUDGMENT]** Vacation mode: one switch pausing checkout site-wide with an honest banner;
  catalog stays browsable. *(on — every solo grower takes time off)*
- **[JUDGMENT]** Store-wide weather-hold banner toggle. *(on for live-plant sellers)*
- **[EVIDENCED]** Store identity (display name, legal name, contact email, phone, address) edited
  in ONE place, feeding receipts, footer, and Store schema. — *D-2.6.5 (legal name); item-integrity*
- **[REQUIRED]** Stripe test/live mode indicator visible in admin. — *(self-contained)*

## G. Operations
- **[REQUIRED]** Nightly DB backup + documented restore; staging vs production data separation. — *(self-contained)*
- **[REQUIRED]** Error alerting to the BUILDER's email (owner sees friendly failures; builder sees
  stack traces). — *(self-contained)*
- **[JUDGMENT]** Owner mini-dashboard: orders this week, revenue, low-stock list, pending notify
  counts — four numbers, not analytics theater. *(on — high value, low cost)*

## H. Deferred by default — build on client traction
- **[DEFERRED]** Coupon codes (Stripe native) · customer accounts + wishlists · reviews ·
  pre-order deposits · multi-staff roles.

---

## Sequencing
- **A → B → D are Phases 2/3** — the path to a store that SELLS (auth+catalog, then checkout+orders).
- **C and E complete owner autonomy in Phases 2/4** (content blocks; notify + comms).
- **F–G land with whichever phase first needs them** (settings when checkout needs shipping/tax;
  ops backups/alerting as soon as real data exists).

## Field-completeness rule
When building ANY admin form, enumerate every field the OWNER would expect from running their
business for a week. If a thing can **sell out, go on sale, pause, or need an apology banner, it
has a field.** A form that can't express a normal week of the business is incomplete.
