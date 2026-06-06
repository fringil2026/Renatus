# CLAUDE.md — Project Guide
Read automatically by Claude Code on startup; written to be equally readable by humans.

## What this is
MASTER copy of the **ecommerce-catalog** base archetype — a product-forward small-business
catalog in the **"Living Herbarium"** design system. First instantiated for Andy's Orchids
(spec `WS-SPEC-ANDYS-ORCHIDS-001`). Governed by `playbooks/ecommerce-catalog.md`.

NEVER customize this master for a client. Per client: `cp -R templates/ecommerce-catalog
clients/<slug>/03-site`, then customize the copy.

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
