# ECOMMERCE-GUIDELINES.md — The Complete Commerce Build Standard

**Scope:** binding for every client built from the `ecommerce-catalog` archetype.
**Location:** `templates/ecommerce-catalog/ECOMMERCE-GUIDELINES.md`
**Relationship to other documents:** this file is the consolidated, exhaustive standard. Where it
overlaps with `BACKEND.md` (what gets built), `INTEGRATIONS.md` (what it connects to),
`BUILD-PLAYBOOK.md` (build order), or the studio `CLAUDE.md` (studio-wide law), those documents
remain authoritative for their domain; this file is the single place where the whole picture is
readable end to end. Conflicts resolve in this order: studio Hard Rules → binding client spec →
binding backend-config → this file → archetype defaults.

**Stack assumed:** Astro 5 + Tailwind 4 (static-first, Cloudflare adapter for server routes) ·
Supabase (Postgres, Auth, Storage, RLS) · Stripe (hosted Checkout, webhooks, Tax) · Resend
(transactional email) · Cloudflare Pages (hosting, previews, edge redirects) · Turnstile (form
protection).

---

## 0. HOW TO USE THIS FILE

- A fresh Claude session building a commerce client reads, in order: studio `CLAUDE.md` → the
  client's binding spec(s) in `02-intake/specs/` → this file → `BACKEND.md` → `INTEGRATIONS.md`
  → the client's `backend-config.yaml`.
- Every rule below is testable. If a rule cannot be verified by looking at a file, a build
  output, or a deployed URL, it does not belong here.
- Rules marked **[HARD]** are never overridable by a spec, an edit, or a chat instruction.
  Rules marked **[DEFAULT]** are overridable only by a binding spec or a BINDING backend-config,
  with the override recorded.

---

## 1. HARD RULES — NON-NEGOTIABLE, EVERY BUILD

1. **[HARD] Never fabricate a client fact.** Prices, legal names, policies, hours, emails,
   shipping rules, claims about the business — blanks stay blank and are flagged `FOR REVIEW`.
   Scraped facts are real but unconfirmed: they enter labeled `DRAFT` until the owner confirms.
2. **[HARD] Never edit `templates/` for a client.** Copy the archetype into
   `clients/<slug>/03-site/` and customize the copy. Improvements that should be shared get
   implemented in the archetype first, then ported.
3. **[HARD] Previews are permanently `noindex`.** Only `PUBLIC_INDEXABLE=true` at launch, set by
   a human, removes it. No preview, rehearsal, or staging build is ever crawlable.
4. **[HARD] Never touch the client's email DNS.** No MX, SPF, DKIM, or DMARC records are ever
   modified by the studio. We ROUTE mail to the client's existing inbox; we never host or alter
   their email. Sending domains are verified additively (new TXT records only, with sign-off).
5. **[HARD] Redirects live at the edge** (`public/_redirects` → Cloudflare Pages), never in
   page JavaScript. Every legacy URL with traffic or backlinks gets a 301 to its new home.
6. **[HARD] Prices are server-verified at checkout.** The browser never supplies an amount the
   server trusts. Stripe Checkout sessions are created server-side from the database record.
7. **[HARD] New Turnstile/CAPTCHA keys per client rebuild.** Never reuse another client's keys;
   never carry the old site's keys forward.
8. **[HARD] Reuse the client's existing GA4 property** (if any); never create a parallel
   analytics property that splits their history.
9. **[HARD] Rehearsal credentials never reach production.** Any credential tagged `REHEARSAL`
   blocks cutover until swapped per the checklist (§14).
10. **[HARD] No page builders, ever.** Owners edit facts and words inside purpose-named blocks;
    layout, spacing, color, and typography are never owner-editable.
11. **[HARD] Item integrity by construction.** One product record; every surface (card, page,
    schema, cart, admin, email) reads that record. The same applies to store identity: one
    source feeds receipts, footer, contact page, and `Store` schema.
12. **[HARD] All colors and fonts flow through `@theme` tokens.** No literal hex values in
    components. `tokens.json` mirrors the `@theme` block.
13. **[HARD] Publish-always.** Any completed change to `03-site` ends with `npm run build`
    (mandatory verification), an automatic preview deploy, and `preview_url` +
    `preview_published_at` refreshed in `status.json`. A failing deploy still commits the work,
    logs loudly, and flags `preview_stale` — never a silently stale URL.
14. **[HARD] State lives in artifacts, not memory.** Specs, edits, deliverables,
    backend-configs, and decisions are signed/state-named files. Filename is state
    (`NNN-PENDING-…` → `NNN-DONE-…`/`NNN-BLOCKED-…`). DONE/BLOCKED/RESOLVED files are immutable.

---

## 2. PIPELINE ORDER — THE CANONICAL SEQUENCE

Each step cites its governing rule. Skipping a step is a build failure unless the client's
binding spec explicitly waives it (and the waiver is recorded).

1. **Scrape (baseline)** — all methods: crawler (`crawl.py`), rendered browser
   (`render_capture.py`, catches JS-driven features), wget mirror (`mirror.sh`, capped —
   raise the cap deliberately via env var for full-catalog modes, never unbounded), plus
   robots/sitemap parsing and JS-file harvesting for feature signals.
2. **Feature census** (`feature_census.py`) — every macro-feature classified:
   - `CARRY-OVER` — static-feasible; MUST appear in the prototype (the parity floor).
   - `STUB+FLAG` — needs backend or client input; ships as a visible honest stub with its
     unblock fact recorded in deliverables §2.7.
   - `OBSOLETE` — recommended drop, with reason.
   The parity floor is absolute: new features come ON TOP of parity, never instead of it.
3. **Intake pack** (auto on baseline-ready) — `redesign-plan.md` (2–3 named concept proposals,
   feature plan, block-purpose preview, scope) + `deliverables-request.md` (filtered,
   specialized, §2.1/§2.2 always BLOCKING) + a concept-choice decision card.
4. **Block-purpose map** — every source block designated by PURPOSE (announcement banner,
   taxonomy index, product card, inventory state…) and mapped to a purpose-named component.
   Never port or restyle source markup. Undecidable blocks go to the human, never copied.
5. **Assemble prototype** (Command 1) — archetype copied, tokens applied, content mapped as
   DRAFT, redirect map drafted from `url-inventory.csv`, build verified, preview published.
6. **Edits via the ledger** — every change is an edit file; one commit per edit; Resolution
   stamped with commit hash; conversational requests are materialized as edit files first.
7. **Backend configuration** — "Propose backend config" reads the tiers + evidence; the human
   confirms on the dashboard (slug-typed); BINDING config = the exact Phase 2+ build order.
8. **Phases 2–4** — per `BACKEND.md` and the BINDING config, on rehearsal or production
   credentials per the client's mode. Each phase verifies before the next.
9. **Owner answers → Finish** — DRAFT content replaced/confirmed, provenance cleared,
   FOR REVIEW flags resolved.
10. **Cutover prechecks → launch** — launch checks, redirect verification, DNS zone diff,
    rehearsal-credential refusal, `PUBLIC_INDEXABLE=true` as the final human-confirmed step.

---

## 3. EVIDENCE & SCRAPING RULES

- **Three methods minimum** (crawler + rendered + mirror); a baseline resting on fewer is
  recorded as partial in `coverage.md` with the gap named. The rendered pass is the only
  method that catches JavaScript-driven features — it is not optional for commerce.
- **Coverage is provable, not assumed.** Re-census against the union of all evidence; diff
  against earlier censuses; report what each method uniquely revealed.
- **Mirror caps:** default 300 files / 5 minutes (anti-runaway). Full-catalog modes raise via
  `MIRROR_MAX_FILES` / `MIRROR_MAX_SECONDS` — bounded, logged, and announced in the run log.
- **Polite crawling:** identified user-agent, ~0.5s wait, bounded retries/timeouts. The studio
  scrapes a client's own site for the client's own rebuild — never third-party sites for assets.
- **Image resolution:** every scraped image resolves to its LARGEST available variant; pixel
  dimensions are recorded; thumbnail-pattern URLs are traced to originals.
- **Stray-process hygiene:** every scrape entrypoint kills leftover wget on start, signal, and
  exception, scoped to that client's mirror directory.

---

## 4. CATALOG INTEGRITY & PRODUCT CORRESPONDENCE

The most expensive class of defect in a catalog rebuild is a right-name/wrong-photo product.
These rules exist because a self-consistent automated check once reported "0 mismatches" on a
catalog where every photo was wrong.

1. **Same-source-page assembly [HARD].** Every field of a product — name, price, description,
   AND photo — comes from that product's OWN source page. Never pool images across pages and
   re-attach by filename, order, or index.
2. **Cover-image pairing.** The product's true photo is the page's product-cover element
   (e.g. the `js-product-cover` `<img>`), not "the first large image on the page" — product
   pages commonly render featured/related images before the real one. A `nophoto` cover means
   the product genuinely has no photo: ship a clean type-led card, never a borrowed image.
3. **Independent verification.** The verifier must NOT share the extractor's selection logic;
   it re-derives truth from the source page's cover element + metadata independently, so a
   systematic extraction bug cannot self-confirm. Any mismatch is a BUILD FAILURE.
4. **Human correspondence sign-off, once per client.** A QA sheet (unlinked, noindex) renders
   every pairing — our name, our photo large, source filename, the page's own title/meta and
   true cover — for human eyeballing. Automated checks verify internal consistency; only a
   human verifies reality. The sign-off is a recorded decision.
5. **Provenance recorded.** Every product carries `source_page`; every image record carries
   `source_page`, `dimensions`, and `largest_variant`.
6. **Scraped commercial facts are DRAFT.** Prices, availability, and descriptions extracted
   from the old site import labeled DRAFT — real, but unconfirmed until the owner signs off.

---

## 5. DESIGN DOCTRINE — COMMERCE BUILDS

### 5.1 Concept-first [HARD]
Every client has ONE named art-direction concept (one sentence) chosen from 2–3 proposals
before any component is built. Concepts derive from the client's world (a nursery → herbarium;
a compliance firm → control room), never from web-design fashion. Every visual decision must
trace to the concept. The chosen concept and the rejected alternatives are recorded in the
redesign plan.

### 5.2 Brand-moment ambition (commerce-only, binding)
Commerce is a feeling before it is a transaction. Every commerce client delivers a memorable
BRAND MOMENT — a beat a visitor would remember tomorrow:
- **Arresting, type-led opening** — oversized display typography as artwork; the honest default
  whenever client photography is below the hero minimum.
- **Editorial, asymmetric catalog rhythm** — imagery prominence EARNED by resolution; high-res
  photos get big slots; low-res/no-photo items get smaller, type-forward cards.
- **Full-bleed color interlude bands** between sections to pace the page.
- **Staggered reveals and refined hover states** — always gated by `prefers-reduced-motion`.
- **ONE signature micro-interaction per client** — exactly one; never a motion circus.
The concept must state WHERE the brand moment lives (opening / catalog / product page), and the
Design QA Gate audits that it exists and lands.

### 5.3 Clean expression [DEFAULT]
Generous whitespace; restrained chrome; few simultaneous visual ideas per screen. Identity is
carried by the display typography, the palette, and one or two signature details; decorative
texture (grain, mounts, ruled ornament) is negotiable and removed where it adds noise.

### 5.4 Photo-forward where honest [HARD]
- Photos are the largest honest element on any surface that has one — displayed at their
  native-resolution ceiling, never upscaled or stretched.
- Slot minimums: hero ≥1600px wide, card ≥600px. An image below minimum is REJECTED from that
  slot and a photography ask (with exact specs: large originals ≥2000px, product shots plus
  habitat/environment shots) is added to the deliverables request.
- All photo slots are built to gracefully accept large imagery, so new photography upgrades the
  site with zero layout rework.
- ONE cropping/color treatment per site.

### 5.5 Place-based organization (when origin data exists) [DEFAULT]
Where products carry origin data, derive region collections (`/origin/<region>/`): a full-bleed
band with the region name in oversized display type + a 1–2 sentence habitat blurb (general
knowledge, labeled DRAFT) + that region's products. Homepage rhythm alternates region band →
blurb → product strip → "browse the region." Product pages carry an origin trail in mono labels
and cross-link to their region. Principles may be adapted from best-in-class references;
markup, theme, imagery, and trade dress are NEVER copied.

### 5.6 Distinctiveness bar [HARD]
Banned by default: generic template sameness (white background + gray cards + blue accent),
default system fonts, stock-gradient heroes, three-icon feature rows, parallax circuses.
Each site ships one memorable signature visual element.

### 5.7 Design QA Gate [HARD]
A build is not done until a recorded self-audit passes: names the concept + signature element;
zero banned patterns; every image meets its slot minimum, unstretched, correspondence-correct;
brand moment named, placed, and landing; checked at desktop AND ~390px mobile; honest answer to
"would a visitor remember this tomorrow?" The audit verbatim goes in the build report or the
edit's Resolution.

---

## 6. CONTENT & LANGUAGE RULES

1. **Explicit functional language.** Every nav label, button, and heading states what it does
   ("Browse orchids by genus", "Get notified when it's back"). Banned: "Discover", "Explore",
   "Learn more", and marketing filler ("premium", "world-class", "curated", "elevate").
2. **Concrete attributes on cards** — size, origin, care level, price — as worded text, not
   icon soup.
3. **Honest stubs over fakes.** A feature awaiting its backend ships as a visibly labeled
   preview ("sign-in is coming with the full store"), never a form that silently goes nowhere.
4. **Scraped copy is DRAFT** until the owner confirms ownership (license risk).
5. **Plain language in owner-facing documents** (roadmap, deliverables): benefits in the
   client's terms, no phase numbers or stack names in benefit lines; deliverable IDs appear
   only in the unblock lines.

---

## 7. FRONTEND ENGINEERING RULES

- **Static-first.** Phase 1 fully prerenders. Server routes (`/api/*`, `/admin/*`) arrive with
  Phase 2 via the Cloudflare adapter; catalog/product pages stay prerendered.
- **Data seam.** Pages read products ONLY from `src/lib/products.ts`; Phase 2 swaps that module
  to live Supabase reads and nothing else changes.
- **Structured data:** `Store` (site-wide), `Product` with offers (price, currency,
  availability mapped in-stock→`InStock`, out→`OutOfStock`), `BreadcrumbList`, FAQ schema where
  FAQ content exists, `LocalBusiness` hours when the hours block is enabled. JSON-LD blocks are
  never deleted — their data is updated.
- **Slugs lock after first publish**; changed slugs leave a 301 behind.
- **Progressive enhancement:** filters/search hide and show server-rendered nodes; the catalog
  works with JavaScript off.
- **Accessibility floor:** semantic headings, labeled forms, alt text on every real image,
  visible focus states, color contrast ≥ WCAG AA, reduced-motion honored everywhere.
- **Performance floor:** lazy-loaded below-fold images, generated responsive variants, no
  blocking third-party scripts on the catalog path; record a performance baseline
  before/after when the old site is measurable.
- **404 page** in-concept, linking back to the catalog.
- **Mobile check at ~390px is part of every gate.**

---

## 8. BACKEND BASELINE — FIELD-LEVEL (summary of BACKEND.md; that file governs)

### A. Auth & safety rails [REQUIRED]
Supabase Auth owner login (magic-link default; schema ready for a later "staff" role) · RLS on
every table (public reads active products only; all writes authenticated owner) · admin audit
log (who/what/when/old→new on every change) · secrets per the credentials convention · webhook
signature verification · idempotency keys on anything Stripe-triggered.

### B. Catalog & inventory (the owner's daily tool; effortless on a phone)
**The complete product record:**
- *Identity:* genus/category, species/variant, common name, SKU (auto-suggested, editable),
  slug (auto, locked after first publish).
- *Commerce:* price, compare-at price (sale display), private cost (never rendered), currency,
  max-quantity-per-order, weight/size for shipping, displayed size attribute.
- *Inventory:* `stock_qty` as a DIRECTLY EDITABLE number (typed entry; steppers are a
  convenience, never the only path) PLUS an availability status that can OVERRIDE quantity —
  `in-stock / out-of-stock / coming-soon / discontinued`; per-product low-stock threshold →
  owner alert email; Conservatory/out-of-stock-gallery show/hide toggle; optional
  expected-restock date; automatic out-of-stock on webhook decrement.
- *Content:* description, care/spec fields, difficulty/grade, seasonal flags, origin, tags,
  related-product picks, per-photo ALT TEXT, photo ordering (first = primary), per-product meta
  description (auto-generated, overridable).
- *Merchandising:* featured flag, manual sort pinning.
- *Lifecycle:* draft / active / archived. "Remove" = archive (record kept, URL redirected) —
  never a hard delete from the admin.
- *Photos:* upload → Storage with automatic resize variants (hero/card/thumb) and recorded
  dimensions — imagery rule enforced at upload, not at build.
- *Bulk:* CSV import/export.

### C. Content blocks (owner autonomy without design access)
`site_content` table keyed by PURPOSE NAME (from the block-purpose map). Editable set:
announcement banner (on/off + scheduled start/end), featured-specimen picker, business hours +
holiday closures (feeds the notice AND LocalBusiness schema), about/story, FAQ entries,
shipping policy, featured-product picks, social links, legal pages (privacy / terms / refund &
live-goods guarantee), and the WORDING of transactional emails. Components read blocks from the
DB with committed static fallbacks. The admin lists blocks by purpose name with a note of where
each appears.

### D. Orders & fulfillment
Orders table fed by the Stripe webhook (line items, amounts, shipping address; status
new → packed → shipped) · order detail + search · per-order weather/ship-hold flag ·
refunds/disputes deep-link to Stripe (never rebuilt) · owner notification email per order.

### E. Customers & communications
`notify_requests` with per-product pending counts (a demand signal), send-once-per-subscriber
restock email, one-click unsubscribe tokens · customer records accumulated from orders (guest
checkout default) · consented newsletter list as a separate table · documented data-deletion
path · email routing: per-form destinations, customer-facing mail FROM the verified domain with
reply-to the owner's real inbox, route-never-host (§1.4), Turnstile + honeypot on public forms,
optional owner-toggleable auto-acknowledgment.

### F. Store settings
Shipping zones/rates/handling time · special add-ons as editable line items (e.g. heat pack) ·
free-shipping threshold · local-pickup toggle + instructions · Stripe Tax (never hand-rolled) ·
VACATION MODE (one switch pauses checkout with an honest banner; catalog stays browsable) ·
store-wide hold banner toggle · single-source store identity · visible Stripe test/live
indicator in the admin.

### G. Operations [REQUIRED]
Nightly DB backup + documented restore · staging/production data separation · error alerting to
the BUILDER's email (owner sees friendly failures) · owner mini-dashboard: orders this week,
revenue, low-stock list, pending notify counts — four numbers, not analytics theater.

### H. Deferred by default
Coupon codes (Stripe native) · customer accounts + wishlists · reviews · pre-order deposits ·
multi-staff roles. Built on client traction or explicit request only.

### Field-completeness rule [HARD]
When building any admin form, enumerate every field the OWNER would expect from running their
business for a week — if a thing can sell out, go on sale, pause, or need an apology banner, it
has a field. An admin below sections B+C coverage is a build failure, not a partial success.

---

## 9. NECESSITY TIERS & THE BACKEND-CONFIG

- **REQUIRED** — always built, never toggleable: auth, RLS, audit log, webhook verification,
  upload-time image processing, lifecycle states, backups, error alerting, test/live indicator.
- **EVIDENCED** — built automatically when the feature census, binding spec, or playbook proves
  the need; each carries its evidence citation.
- **JUDGMENT** — recommended ON or OFF per client with a one-line reason; owner-overridable
  (vacation mode, newsletter, hold banners, local pickup, content-block selection).
- **DEFERRED** — off unless explicitly requested (section H).

**Baseline rule:** everything necessary or evidenced is INCLUDED by default; judgment applies
only to additionals. A client can end up with less than the full baseline, never less than
their evidence.

**The config artifact:** `02-intake/backend-config.yaml`, signed
(`config-id: WS-BCFG-<CLIENT>-NNN`, version, status `DRAFT` → `BINDING` on slug-typed dashboard
confirm). A BINDING config is a build order: Phase 2+ implements exactly its ON set; changes
require a new version, never silent edits. Phase 2 cannot start without a BINDING config AND
its BLOCKING deliverables met (or rehearsal mode).

---

## 10. ADMIN APP RULES

1. **Phone-first.** The owner's primary device is assumed to be a phone in a greenhouse,
   stockroom, or van. Every daily task (stock change, price change, banner edit, order status)
   completes comfortably at ~390px.
2. **Direct entry everywhere.** Numbers are typed, not only stepped; dates are picked; statuses
   are dropdowns. Steppers, toggles, and quick actions are conveniences layered on top.
3. **List-view inline actions:** stock edit, availability flip, featured toggle, archive — all
   without opening the product detail page.
4. **Archive, never delete.** Deleting a record from the UI is not possible; archive preserves
   history and leaves a redirect.
5. **Every change audited** (who/what/when/old→new) and visible in a simple history view.
6. **TEST MODE banner** rendered in the admin header (and on checkout) whenever rehearsal or
   Stripe-test credentials are active. The Stripe mode indicator is always visible.
7. **Friendly failures.** Owner-visible errors are plain-language with a next step; stack
   traces go to the builder's error alerting, never to the owner's screen.
8. **No design controls.** The admin edits facts, words, selections, and order — never layout,
   spacing, color, or type (§1.10).
9. **Completeness audit before "done":** walk BACKEND.md sections B+C field by field;
   anything missing is either implemented or listed as deferred-with-reason in the report.

---

## 11. INTEGRATIONS REGISTRY — CORE (every commerce client)

For each: purpose · tier · env vars · rehearsal credential · production credential
(deliverable) · swap notes · failure behavior. Full operational detail lives in
`INTEGRATIONS.md`; this is the canonical summary.

### 11.1 Supabase — database, auth, storage [REQUIRED]
- *Purpose:* products, orders, notify_requests, site_content, customers, audit log; owner
  magic-link auth; photo storage with resize variants; RLS as the security boundary.
- *Env:* `SUPABASE_URL`, `SUPABASE_ANON_KEY` (public reads), `SUPABASE_SERVICE_ROLE_KEY`
  (server only — never shipped to the browser, never in client bundles).
- *Rehearsal:* the studio's `ws-rehearsal` project (free tier). *Production:* the client's own
  project, or one provisioned under the client's email with their consent — D-2.7.2.
- *Failure:* site falls back to the last committed static catalog for reads; admin shows a
  friendly outage notice; builder alerted.

### 11.2 Stripe — payments, tax, refunds [EVIDENCED → effectively required for any store]
- *Purpose:* hosted Checkout (the site never renders a card field), signed webhooks feeding the
  orders table and stock decrements, Stripe Tax, refunds/disputes handled in Stripe's own
  dashboard.
- *Env:* `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`.
- *Rehearsal:* TEST-mode keys (`sk_test_…`) on a free account; card `4242 4242 4242 4242`.
  *Production:* the CLIENT's own Stripe account — payouts go to them, never through the studio
  — D-2.7.1. Webhook endpoint re-registered at swap; idempotency keys on all mutations.
- *Failure:* checkout disabled with an honest banner; catalog stays browsable; orders already
  in Stripe are never lost (webhook retries + idempotency).

### 11.3 Resend — transactional email [EVIDENCED when any email feature is on]
- *Purpose:* back-in-stock notifications, order acknowledgments, owner alerts, contact-form
  routing. Sends FROM the verified client domain; reply-to is the owner's real inbox.
- *Env:* `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_OWNER_INBOX` (+ optional per-form overrides).
- *Rehearsal:* Resend's test/onboarding domain (delivers to the builder's own inbox only).
  *Production:* domain verification on the client's domain — additive DNS TXT only, with
  sign-off; MX untouched [HARD] — D-2.7.3.
- *Failure:* sends queue/log rather than silently drop; the notify promise ("we'll email you")
  is never shown unless sending works.

### 11.4 Cloudflare Pages — hosting, previews, redirects [REQUIRED]
- *Purpose:* `ws-<slug>.pages.dev` permanent previews; production hosting at cutover; edge
  `_redirects`; the Cloudflare adapter runs `/api/*` and `/admin/*` server routes.
- *Env/CLI:* wrangler login (machine-level); project `ws-<slug>`.
- *Rehearsal = production infrastructure* (only the data/keys differ); previews always noindex.
- *Failure:* deploy failure flags `preview_stale` (§1.13); the prior deploy keeps serving.

### 11.5 Turnstile — form protection [EVIDENCED when public forms exist]
- *Purpose:* contact, notify, newsletter forms; paired with a honeypot field.
- *Env:* `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` — NEW keys per client [HARD].
- *Rehearsal:* Cloudflare's documented test keys. *Production:* fresh keys in the client's (or
  studio's, by agreement) Cloudflare account.

---

## 12. INTEGRATIONS — OPTIONAL CATALOG (tier + judgment note)

| Integration | Tier | When it earns its place |
|---|---|---|
| Shipping-label API (EasyPost / Shippo) | JUDGMENT | Owner ships weekly volume; prints labels from the order view instead of retyping addresses. |
| Client's existing GA4 | EVIDENCED if detected | Reuse their property [HARD §1.8]; wire behind consent where required. |
| Privacy-light analytics (e.g. self-hosted/lightweight) | JUDGMENT | When the client has no GA4 and wants simple numbers without a consent banner burden. |
| Meta Pixel (re-add) | EVIDENCED if detected on old site | Only behind a cookie-consent decision — D-2.4.4, D-2.6.1. |
| Instagram feed link-out / embed | JUDGMENT | Link-out is Tier 1-cheap; live embeds only if the account is active (a dead feed is worse than none). |
| Newsletter (Resend audiences) | JUDGMENT | Only when the owner will actually send; never collect consent that goes unused. |
| Reviews platform | DEFERRED | On traction; native lightweight reviews before third-party widgets. |
| Search service (hosted index) | DEFERRED | Client-side search suffices into the hundreds of products; revisit past ~1–2k. |
| Uptime monitoring | JUDGMENT (studio-level) | One monitor per production site, alerting the builder. |
| Object-storage backups (B2/S3 via restic) | REQUIRED at production | Nightly DB + media snapshots; documented restore. |
| Google Business Profile linkage | EVIDENCED for local businesses | Hours block feeds the same truth shown on the profile. |

Any integration not in this table enters through a spec or an edit, gets a tier assigned, and
is added to `INTEGRATIONS.md` so the registry stays complete.

---

## 13. CREDENTIALS & SECRETS CONVENTION

- All client secrets live in `clients/<slug>/02-intake/secrets/.env` — gitignored, never
  echoed into chat or logs, never committed, never rendered in any report ("stored, not
  echoed" is the standard phrasing).
- Every credential line carries a tag comment: `# REHEARSAL` or `# PRODUCTION`.
- Server-only keys (Supabase service role, Stripe secret, Resend, Turnstile secret) exist only
  in server runtime env — never in the client bundle. A build-time check greps `dist/` for
  secret prefixes (`sk_live`, `sk_test`, `service_role`) and fails the build on a hit.
- The canonical env-var table (every variable → which service → rehearsal source → production
  source → swap step) lives in `INTEGRATIONS.md` and is the single authority at swap time.

---

## 14. REHEARSAL MODE

- `mode: rehearsal` in `backend-config.yaml` lets Phases 2–4 build on STUDIO TEST RESOURCES
  (rehearsal Supabase, Stripe TEST keys, Resend test domain) instead of client deliverables.
  Client facts remain unfaked; dummy data is loudly labeled.
- **Guarantees [HARD]:** visible TEST MODE banners on admin + checkout; rehearsal credentials
  tagged in `secrets/.env`; cutover REFUSES to run while any REHEARSAL-tagged credential is in
  use; previews stay noindex.
- **Full-rehearsal builds** scrape to complete coverage and import the ENTIRE real catalog
  (cover-paired, DRAFT-labeled facts) so the demo is a faithful replica on test rails.
- **The un-rehearsal swap checklist** (executed as a ritual, each item checked):
  1. `SUPABASE_URL` / keys → client's project; schema migrated; data re-seeded or promoted.
  2. `STRIPE_*` → client's LIVE keys; webhook endpoint re-registered; one live test
     transaction + refund verified.
  3. `RESEND_*` → client's verified domain; one real notify email verified end-to-end.
  4. `TURNSTILE_*` → fresh production keys.
  5. Remove every `# REHEARSAL` tag; re-run the cutover precheck (it must now pass the
     credential scan); only then is launch eligible.

---

## 15. EMAIL & DNS RULES (restated because they are the most dangerous)

1. The studio NEVER modifies MX, SPF, DKIM, or DMARC [HARD]. Breaking a client's email is the
   one mistake a small business cannot forgive.
2. Sending-domain verification adds new TXT/CNAME records only, listed for sign-off first.
3. All form mail ROUTES to the owner's existing inbox; the studio never hosts mailboxes.
4. Per-form destinations are owner-configurable facts (D-2.3.1); order notifications may have
   multiple recipients.
5. Every subscriber email (notify, newsletter) has a working one-click unsubscribe; restock
   notifications send at most once per subscriber per restock.
6. Email WORDING is owner-editable content; sending machinery is not.

---

## 16. SEO, REDIRECTS & STRUCTURED DATA

- The redirect map is drafted from `url-inventory.csv` at assemble time and finalized before
  cutover; deep product URLs are the highest-value redirects and get 1:1 mappings as soon as
  the legacy-ID↔slug map exists (interim catch-alls so nothing 404s in between).
- Canonical URLs on every page; one canonical host (apex or www, decided at cutover).
- Per-product meta descriptions auto-generate from the record, overridable in the admin.
- Sitemap generated at build; submitted via the client's existing Search Console (D-2.4.2)
  at launch — never a new property that orphans their history.
- Previews and rehearsal builds never enter any sitemap and are always noindex (§1.3).
- Structured-data validation (Product offers parse, availability correct) is a standing QA
  gate, not a one-time check.

---

## 17. ACCESSIBILITY, PERFORMANCE, PRIVACY & LEGAL

- **Accessibility:** WCAG AA contrast; keyboard-navigable filters, modals, and admin; alt text
  required on every real product image (an admin field, not an afterthought); reduced-motion
  honored in every animation; form errors announced in text.
- **Performance:** image variants served by slot; lazy-loading below the fold; no third-party
  script may block first paint of the catalog; webhook and API routes respond < 2s or queue.
- **Privacy:** guest checkout default; customer data minimal and purpose-bound; a documented
  one-command data-deletion path; analytics/pixels only per the consent decision recorded in
  deliverables (D-2.6.1); privacy policy text is an owner-editable block but its FIRST version
  is reviewed by a human, never auto-published.
- **Legal pages:** privacy, terms, refund/guarantee policy exist before checkout goes live;
  live-goods sellers get an explicit live-arrival guarantee block.
- **Commerce honesty:** compare-at pricing only with a real prior price; availability shown is
  availability meant; "notify me" only where the email actually sends (§11.3).

---

## 18. QA GATES — THE MASTER CHECKLIST (every gate must pass before "done")

1. `npm run build` passes — a failing build is never published or reported done.
2. JSON-LD validates: Store + Product (offers complete) + Breadcrumb (+ FAQ/LocalBusiness
   where enabled).
3. Feature-parity floor: every census CARRY-OVER reachable within one click of home; every
   STUB+FLAG visibly stubbed or wired.
4. Product correspondence: independent verifier 0 mismatches AND human QA-sheet sign-off
   recorded (once per client).
5. Design QA Gate + brand-moment audit recorded verbatim.
6. Imagery: every slot at/above minimum or honestly rearranged; no upscaling; alt text present.
7. Mobile ~390px walkthrough (site AND admin).
8. Secrets scan of `dist/` clean; noindex present on every preview page.
9. Redirect spot-check: top legacy URLs 301 correctly.
10. Publish-always satisfied: live preview URL + refreshed `status.json` in the report.
11. (Phase 2+) RLS probe: anonymous write attempts fail; (Phase 3) full test purchase →
    webhook → stock decrement → order visible in admin; (Phase 4) notify loop end-to-end
    including unsubscribe.

---

## 19. OWNER HANDOFF & DOCUMENTATION

- `production-roadmap.md` — the client-facing plain-language promise list; living document;
  entries move to "Now live" as they ship, never silently vanish.
- An **owner's guide** ships with Phase 2: one page per daily task (add a plant, change stock,
  post an announcement, mark an order shipped, turn on vacation mode), written for a phone,
  screenshots optional but steps mandatory.
- The four-number dashboard is the owner's home screen; everything else is one tap deep.
- Handoff is complete when the owner performs the owner's-Tuesday tasks unassisted in
  rehearsal/test mode.

## 20. DELIVERABLES MAPPING (the unblock facts)

§2.1 access/control and §2.2 email infrastructure are ALWAYS BLOCKING. Commerce-specific:
D-2.7.1 client Stripe account (checkout, tax, payouts) · D-2.7.2 Supabase project / data area
(admin, accounts-later, content blocks) · D-2.7.3 Resend domain verification (every email
feature) · D-2.7.4 photography — large originals ≥2000px, product + habitat/environment shots
(full photographic design expression) · D-2.7.5 shipping policy facts (checkout shipping,
policy page) · D-2.7.6/D-2.6.5 legal name (receipts) · D-2.3.1 per-form inbox destinations ·
D-2.4.4 + D-2.6.1 pixel + consent decision. Every prototype stub names its unblock D-number.

## 21. CHANGE-CONTROL CONVENTIONS (recap)

Specs: signed, versioned, BINDING; highest version wins; never override Hard Rules. Edits:
numbered ledger files, filename-is-state, one commit per edit, immutable once DONE/BLOCKED.
Backend-configs: signed, DRAFT→BINDING, new version per change. Decisions: `NNN-OPEN-*.yaml` →
dashboard cards → immutable RESOLVED. Conversational requests are materialized as edit files
BEFORE implementation. Every judgment capability ships with a dashboard control in the same
commit (decision-surfaces rule).

## 22. GLOSSARY

**Archetype** — the reusable master site in `templates/`; never edited for a client.
**Parity floor** — the census-proven feature set the rebuild must meet before improving.
**Brand moment** — the one memorable beat every commerce build must deliver.
**Purpose-first** — rebuilding what a block is FOR, never porting its markup.
**Correspondence** — the guarantee that a product's name, facts, and photo share one source.
**Rehearsal mode** — full backend builds on studio test resources, swap-listed to production.
**Owner's Tuesday** — the field-completeness test: can the owner run a normal week unassisted?
**Publish-always** — no change is done until it's live at the preview URL.

*End of guidelines. Amendments enter via the edit/spec conventions and bump this file's
heading-level change-log; silent edits to a binding standard are themselves a rule violation.*
