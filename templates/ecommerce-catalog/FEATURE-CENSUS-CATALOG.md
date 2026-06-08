# FEATURE-CENSUS-CATALOG.md — The Exhaustive Detection Catalog

**Location:** `templates/ecommerce-catalog/FEATURE-CENSUS-CATALOG.md`
**Implemented by:** `.claude/skills/site-baseline/scripts/feature_census.py`
**Governs:** what a commerce feature census MUST actively probe for, with detection signals and
classification defaults, so coverage is exhaustive by construction and absence is *proven*, not
assumed.

---

## CORE PRINCIPLE

A parity floor can only protect features the census recorded. Therefore: **the census documents
the smallest observable features, not just macro-modules.** A sale badge, a rewards link, a
bloom-status tag, a bundle price, a payment method — each is a first-class census row with
evidence. Under-documentation is a census FAILURE, not a stylistic preference.

**Three rules bind every run:**
1. **Probe every class below.** A class with no hit is logged `none found (probed: <signals>)`
   — absence is proven, never silently skipped.
2. **Evidence per row.** Every detected feature records the URL + the exact markup/text that
   proves it. Never infer a feature without page evidence; never miss one the evidence shows.
3. **Classify every row** — `CARRY-OVER` (static-feasible, parity floor) / `STUB+FLAG` (needs
   backend or client fact → names its unblock, usually a deliverables §2.7 ID) / `OBSOLETE`
   (recommend drop, with reason).

**Pages the detector must read** (not just the homepage): homepage, 2–3 category/listing pages,
3–5 product detail pages, cart, account/login, search results, and the footer. Many features
only appear on one surface (rewards in the footer, variant selectors on product pages, payment
methods at checkout).

---

## DETECTION CLASSES

For each class: what to find · detection signals (text / markup / link / script patterns) ·
classification default · common unblock fact.

### 1. PRICING & PROMOTIONS
- **Find:** regular price, compare-at / was–now SALE pricing, %/$ discounts, bundle &
  multi-buy ("2/$25", "3/$15"), quantity breaks, clearance / "as-is", price ranges,
  "special pricing" / "*Special" flags.
- **Signals:** currency symbol + struck-through or dual price; text `SALE`, `was`, `Our Price`
  vs `ON SALE`; regex `\d+\s*/\s*\$\d+` (bundles); `clearance`, `as is`, `special pricing`;
  price-range dashes (`$9.90 - $16.90`).
- **Default:** CARRY-OVER (display logic; compare-at is a product-record field).
- **Unblock:** confirmed real prior prices for compare-at (never fabricate a "was" price).

### 2. LOYALTY & REWARDS
- **Find:** points/rewards programs, referral schemes, gift cards, store credit.
- **Signals:** links/text `rewards`, `points`, `loyalty`, `refer`, `gift card`, `store credit`;
  named programs ("MyOrchidRewards").
- **Default:** STUB+FLAG (needs a loyalty backend + the owner's program rules).
- **Unblock:** does the owner run/keep the program? rules, point values.

### 3. MERCHANDISING & STATUS BADGES
- **Find:** "new", "in bud/bloom/spike now", "back in stock", "limited", "featured", seasonal,
  bestseller, "blooming size".
- **Signals:** text `new`, `in (bud|bloom|spike)`, `blooming size`, `featured`, `bestseller`,
  `limited`, `seasonal`; badge/flag CSS classes on cards.
- **Default:** CARRY-OVER (status is a product-record flag the catalog renders).

### 4. INVENTORY SIGNALS
- **Find:** stock counts (the `(16)` quantity tags), low-stock, pre-order, "ships after <date>",
  made-to-order, waitlist, "avail. to ship after".
- **Signals:** trailing `\(\d+\)` count tags; `avail.*ship.*after`, `pre-?order`, `waitlist`,
  `made to order`, `back-?order`.
- **Default:** CARRY-OVER for display; the live numbers are backend (Phase 2 stock model).

### 5. BROWSING AXES
- **Find:** EVERY distinct way to filter/sort — by category/genus, by attribute (temperature,
  size, fragrance, bloom season), by price, by status; search; category index; all-products list.
- **Signals:** nav tree depth; category-URL patterns; filter controls; sort selects; a
  `category index` / `all products` link; search form. Count the axes — each is its own row.
- **Default:** CARRY-OVER (search + filters are the static catalog's core).

### 6. ACCOUNT & SOCIAL
- **Find:** login/accounts, wishlist, order status/history, reviews/ratings (+ counts), Q&A,
  newsletter signup, social links/feeds.
- **Signals:** `login`, `my account`, `wishlist`, `order status`, `review`/star markup,
  `subscribe`/mailing-list form; social-domain links.
- **Default:** accounts/wishlist/orders → STUB+FLAG (backend); newsletter → STUB+FLAG (email
  platform); reviews → STUB+FLAG (reviews backend) or OBSOLETE if empty/unused.

### 7. CHECKOUT & PAYMENT
- **Find:** cart, guest checkout, payment methods INCLUDING alternatives (crypto/bitcoin,
  BNPL, PayPal), shipping calculators, tax handling.
- **Signals:** cart link/page; `checkout`; payment-brand text/icons; `bitcoin`/`crypto`;
  `PayPal`, `Klarna`, `Afterpay`; shipping-estimate widget; `tax`.
- **Default:** STUB+FLAG (Stripe Checkout + the owner's payment accounts; alt-payments are a
  per-client judgment call).
- **Unblock:** client Stripe account (D-2.7.1); which payment methods to keep.

### 8. CONTENT & TRUST
- **Find:** care guides/educational content, blog/articles, FAQ, about, awards/certifications
  (AOS/AM/FCC badges), shipping/returns policy, guarantees, location/hours.
- **Signals:** `care`, `how to grow`, `blog`, `article`, `FAQ`, `about`, `AM/AOS`, `FCC`,
  `shipping`, `returns`, `guarantee`, `hours`, `location`.
- **Default:** CARRY-OVER (static content) for FAQ / about / shipping / returns / guarantees /
  location-hours / awards.
- **EXCEPTION — care guides / "how to grow" / care sheets are OPT-IN, studio-wide:** documented in the
  census for parity (so the original is understood) but **recommend-OFF with reason and NEVER
  auto-built** — they are high-upkeep editorial content. Build them ONLY on the human's explicit
  request (the archetype keeps the capability: `src/lib/care.ts` + re-created `src/pages/care/`).
  Surface as a JUDGMENT note, not a default CARRY-OVER.

### 9. PRODUCT-LEVEL DETAIL
- **Find:** variant/option selectors (pot size, "choose 4\" or 6\""), multiple images/galleries,
  related/cross-sell, recently viewed, fragrance/size/temperature attributes.
- **Signals:** option `<select>`/radio on product pages; multiple product images / gallery
  script; `related`, `you may also like`, `recently viewed`; attribute tables.
- **Default:** variants → CARRY-OVER (product-record options); recently-viewed → STUB+FLAG or
  OBSOLETE; related → CARRY-OVER (manual picks).

### 10. COMPANION / CROSS-CATALOG
- **Find:** non-core product lines (supplies, companion/non-orchid plants, books), gift options.
- **Signals:** nav/category entries outside the core taxonomy (`supplies`, `companion`,
  `non-orchid`, `books`, `gift`); distinct SKU prefixes.
- **Default:** CARRY-OVER (additional categories) — flag for the owner whether to keep each line.

---

## OUTPUT CONTRACT (`feature-census.md`)

A table, one row per smallest observable feature:

| ID | Class | Feature | Evidence (URL + markup/text) | Classification | Unblock fact |
|----|-------|---------|------------------------------|----------------|--------------|

Plus a header summary: counts per class (including `none found` classes), total feature count,
and the parity-floor subset (CARRY-OVER rows). The census also emits the parity-checklist rows
(see the verification-loop rule) so every recorded feature gets a mechanical verification method.

---

## ACCOUNTABILITY

Every census run reports a DIFF against the prior census for that client — features added,
reclassified, or (if any) dropped — so the catalog's completeness is demonstrable, not asserted.
A re-run that surfaces features an earlier run missed is the catalog working; a known feature
still absent after a run is a bug in the detector, not a property of the site.

*Amendments to this catalog enter via the edit/spec conventions and are logged in SYSTEM.md.*
