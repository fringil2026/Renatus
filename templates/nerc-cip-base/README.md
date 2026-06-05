# B2B Compliance Base — NERC CIP Managed Services
Base archetype: **B2B / professional services**, specialization: **NERC CIP managed compliance**.
Stack: Astro 5 + Tailwind 4, static output (deploy to Cloudflare Pages / Netlify / any CDN).

## Quick start
    npm install
    npm run dev          # local preview at localhost:4321
    npm run build        # static output in dist/ (defaults to NOINDEX — staging-safe)
    PUBLIC_INDEXABLE=true npm run build   # production build (launch-runbook step zero)

## Per-client customization (in order)
1. **tokens.json → src/styles/global.css @theme** — colors, fonts, radius. One block restyles everything.
2. **src/config/site.ts** — identity, contact, regions, certifications, form endpoint, Turnstile key, GA4 ID. Every field maps to the Phase 2 access/inventory checklist.
3. **src/data/*.json** — services, FAQs, case studies. These are the content slots; the Phase 1 content inventory maps into them.
4. **Section variants** — e.g. `<Hero variant="split" | "centered" />` in pages. Compose differently per client.
5. **astro.config.mjs `site`** + public/robots.txt sitemap URL → client's production domain.

## Baked-in guarantees (do not remove)
- `noindex` controlled solely by `PUBLIC_INDEXABLE` env var — kills the staging-noindex disaster class.
- ProfessionalService + FAQPage JSON-LD; semantic headings; AEO-friendly robots policy for AI crawlers.
- Contact form: honeypot + optional Turnstile + GA4 `generate_lead` event with stable element IDs.
- Custom 404 with recovery navigation; canonical URLs; OG/social meta on every page.
- BCSI handling notice on the form and in the footer (CIP-011 signal procurement teams look for).

## Cutover hooks
- Redirect map deploys at the host/CDN edge (e.g. Cloudflare `_redirects`), not in this codebase.
- Carry the client's EXISTING GA4 property ID into site.ts — never create a fresh property.
- Issue NEW Turnstile/reCAPTCHA keys per rebuild.
