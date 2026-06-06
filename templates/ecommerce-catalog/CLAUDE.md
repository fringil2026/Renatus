# CLAUDE.md — Project Guide
Read automatically by Claude Code on startup; written to be equally readable by humans.

## What this is
MASTER copy of the **ecommerce-catalog** base archetype — a product-forward small-business
catalog in the **"Living Herbarium"** design system. First instantiated for Andy's Orchids
(spec `WS-SPEC-ANDYS-ORCHIDS-001`). Governed by `playbooks/ecommerce-catalog.md`.

NEVER customize this master for a client. Per client: `cp -R templates/ecommerce-catalog
clients/<slug>/03-site`, then customize the copy.

## Required reading — every commerce build (binding, not background)
Before assembling or finishing ANY client from this archetype, read these in order:
1. **`BACKEND.md`** — the Phases 2–4 backend baseline (WHAT gets built).
2. **`INTEGRATIONS.md`** — the integrations registry (what it connects to; env vars; swap notes).
3. **`ECOMMERCE-GUIDELINES.md`** — the **consolidated commerce build standard**: the single place
   the whole picture (hard rules, pipeline order, design doctrine, QA gates) is readable end to
   end. Where it overlaps the two docs above, each of those remains authoritative for its own
   domain; the guidelines are the **consolidated reference**, not a competing source of truth.
   Conflicts resolve: studio Hard Rules → binding client spec → BINDING backend-config →
   the guidelines → archetype defaults.

## Build status — phased per the spec
- **Phase 1 (DONE): static catalog.** Catalog, product, and Conservatory pages render
  from `src/data/products.json`; full Product + Breadcrumb + Store JSON-LD. Fully static,
  no accounts, no adapter.
- **Phase 2+ (NOT built): Supabase / Stripe / Resend.** `src/lib/products.ts` is the seam:
  pages import only from it, so swapping the JSON seed for live Supabase reads is local.
  Adding `@astrojs/cloudflare` + `output: 'server'` turns on `/api/*` and `/admin/*`.

## Commands
- `npm install` — once per fresh copy
- `npm run dev` — local preview at localhost:4321
- `npm run build` — static build to dist/. **Run after every change set.**
  Staging emits `noindex`; production: `PUBLIC_INDEXABLE=true npm run build`.

## Component catalog — the shared vocabulary
This catalog is a PURPOSE vocabulary: scraped source blocks map into it by DESIGNATION (what the
block is FOR), never by appearance. A gap in the vocabulary means create a new purpose-named
component — never inline one-off markup to mimic the old site.

| Name | In plain terms | File |
|---|---|---|
| Specimen card | THE signature unit: photo + herbarium tag (Latin name, origin, care glyphs, difficulty dot, price). OOS → desaturated photo + "In Cultivation" stamp + Notify CTA | `src/components/SpecimenCard.astro` |
| Specimen photo | Image, or a labelled botanical PLACEHOLDER when no licensed photo exists | `src/components/SpecimenPhoto.astro` |
| Care glyphs | Three line icons: light / water / temperature, titles carry the care strings | `src/components/CareGlyphs.astro` |
| Hero | "Specimen of the Week" — one macro plate on the green field, single CTA | `src/components/Hero.astro` |
| Filter bar | Catalog genus chips + difficulty + "in bloom now"; progressive-enhancement JS | `src/components/FilterBar.astro` |
| Base head | `<head>`: meta, OG, fonts, noindex flag, GA4 | `src/components/BaseHead.astro` |
| Schema | Store/Organization JSON-LD (Product/Breadcrumb emitted per-page) | `src/components/SchemaOrg.astro` |
| Header / Footer | Conservatory-green chrome | `src/components/{Header,Footer}.astro` |
| Base layout | Page shell; `slot="head"` lets a page add page-specific JSON-LD | `src/layouts/Base.astro` |

Pages: `/` `src/pages/index.astro` · catalog `/shop/` · product `/shop/[slug]/` (getStaticPaths)
· `/conservatory/` (out-of-stock gallery + notify capture) · custom 404.
Data: `src/data/products.json` (Phase 1 seed). Loader/types/helpers: `src/lib/products.ts`.
JSON-LD builders: `src/lib/schema.ts`. Client facts: `src/config/site.ts`. Tokens: `@theme`
in `src/styles/global.css` (mirror `tokens.json`).

## Hard rules — never violate
- ADMIN COMPLETENESS: an admin build is NOT done until it covers EVERY non-deferred field in
  BACKEND.md §B and EVERY non-deferred block in §C — a partial admin UI is a BUILD FAILURE.
  Apply the field-completeness rule (walk the owner's week). Deferring an item is allowed only
  with a recorded reason; silently omitting one is not.
- Imagery follows the studio rule: a PROTOTYPE may use images scraped from the client's OWN
  site; PRODUCTION ("Finish") requires every image client-supplied or provenance-confirmed,
  else FOR REVIEW + replaced. Never use third-party/stock imagery. `SpecimenPhoto` shows the
  real photo when `product.photos` is set, and a labelled placeholder when it isn't.
- NEVER remove the `INDEXABLE` / `noindex` logic in BaseHead.astro.
- NEVER delete the JSON-LD blocks (Store, Product, Breadcrumb). Update their data instead.
- Prices are ALWAYS server-verified from the DB at checkout — never trust client-supplied
  amounts (Phase 3). The site never renders a card field; Stripe hosts the payment page.
- All colors/fonts via `@theme` tokens — no literal hex in components.
- Reuse the client's EXISTING GA4 property; issue NEW Stripe/Supabase/Resend keys per build.
- Redirects live at the host/CDN edge (`public/_redirects`), never in page JavaScript.

## Style
"The Living Herbarium": paper pages, conservatory-green chrome, pressed-petal coral as the
ONLY accent. Type: Cormorant Garamond (display, italic for Latin binomials) · Public Sans
(body) · IBM Plex Mono (labels/SKU/origin). Microdetails: thin botanical rules, plate
numbers ("Pl. 12"), hover lifts a card 2px. No parallax — neat and precise.

## Concept evolution — "Herbarium v2" (cleaner + photo-forward)
The Living Herbarium evolved toward a quieter, photo-forward expression: significantly more
whitespace, simplified cards (the ruled herbarium tag is a single hairline; paper-grain and
photo-corner mounts retired as noise), lighter chrome, fewer simultaneous visual ideas per screen.
The IDENTITY is unchanged and non-negotiable — **italic Latin display type, conservatory green, and
plate numbering ARE the brand**; the ornament around them was negotiable and got dialled back.
Photo-forward rule: on any surface with a photo, the photo is the largest honest element; real
photos display at their native-resolution ceiling (NEVER upscaled); no-photo products get clean
type-led cards (a big italic binomial), never fake plates. All photo slots are built to accept
large imagery so D-2.7.4 originals scale to full photographic immersion with zero layout rework.
Reference for FEEL only (never copied): the restraint of photography-led catalog sites — few
colours per screen, the photo doing the talking, type staying out of the way.

## Brand-moment design ambition — binding for every client built from THIS archetype
Commerce is a feeling before it is a transaction. Every client built from ecommerce-catalog MUST
deliver a memorable BRAND MOMENT — a beat a visitor would remember tomorrow. This raises the bar
above the studio's global Design Ground Rules and applies to commerce builds ONLY (other archetypes
keep their own character). The toolkit:
- **Arresting, type-led opening.** Oversized display typography used as artwork. This is the HONEST
  default when client photography is below the hero minimum (hero ≥1600px) — let the words carry
  the opening rather than stretching a small photo.
- **Editorial, asymmetric catalog rhythm.** Vary scale and placement; imagery prominence is EARNED
  by resolution — only high-res photos get the big slots; low-res/no-photo items take smaller,
  type-forward cards rather than being blown up.
- **Full-bleed color interlude bands** between sections to pace the page and reset the eye.
- **Staggered reveals and refined hover states** — always gated by `prefers-reduced-motion`.
- **ONE signature micro-interaction per client** — a single deliberate motion/feedback flourish
  that becomes the site's tell. Not a motion circus; exactly one.

**Concept placement (extends the studio ground rules):** each commerce client's named concept must
state WHERE its brand moment LIVES — the opening, the catalog, or the product page — so the moment
is intentional, not incidental.

**Design QA Gate for commerce builds (extends, doesn't replace, the global gate):** the audit must
explicitly confirm the brand moment EXISTS and LANDS — name it, name where it lives, and answer
honestly whether it's memorable. A commerce build with no brand moment fails the gate.
