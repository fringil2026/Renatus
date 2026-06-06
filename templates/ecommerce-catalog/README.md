# ecommerce-catalog — base archetype

A product-forward small-business catalog in the **"Living Herbarium"** design system.
Astro 5 + Tailwind 4. Phase 1 is fully static; later phases add Supabase (data/auth),
Stripe Checkout (hosted), and Resend (back-in-stock email) per the client build spec.

## Quick start
```bash
npm install
npm run dev      # localhost:4321
npm run build    # static -> dist/   (PUBLIC_INDEXABLE=true for production)
```

## What Phase 1 gives you
- Catalog `/shop/` with genus / difficulty / "in bloom" filters
- Product `/shop/<slug>/` with full Product + BreadcrumbList JSON-LD (offers + availability)
- The Conservatory `/conservatory/` — out-of-stock gallery with per-specimen notify capture
- The SpecimenCard component and the "Specimen of the Week" hero
- Zero shipped photography — licensed originals only; placeholders until then

## Customizing per client
Edit `src/config/site.ts` (identity), `src/data/products.json` (catalog — replaced by live
Supabase reads in Phase 2 via `src/lib/products.ts`), and the `@theme` tokens in
`src/styles/global.css` (mirror `tokens.json`). Draft edge redirects in `public/_redirects`.

See `CLAUDE.md` for the component catalog, hard rules, and the phase roadmap.
