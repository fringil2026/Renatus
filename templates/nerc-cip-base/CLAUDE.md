# CLAUDE.md — Project Guide
Read automatically by Claude Code on startup. Written to be equally readable by humans —
this file is the map of the project and the shared vocabulary for talking about it.

## What this is
This folder is the MASTER copy of a base template.
Archetype: B2B professional services — NERC-CIP managed compliance.

NEVER customize this master for a client. Per client: duplicate the folder
(`cp -R nerc-cip-base clients/<client-name>`) and do all work in the copy.

## Commands
- `npm install` — once per fresh copy, downloads dependencies
- `npm run dev` — local preview at localhost:4321 (live-reloads on save)
- `npm run build` — static build to dist/. **Run after every change set to verify.**
  Default build emits `noindex` (staging-safe). Production: `PUBLIC_INDEXABLE=true npm run build`.

## Intake workflow — per-client customization
If an `intake/` folder is present, customize from it with no further instruction needed,
in this order:

1. `intake/brief.yaml` → transcribe into `src/config/site.ts`; compose the pages and
   section variants named under `build:` directives; use `build.tone` and `build.notes`
   to steer any copy that must be drafted.
2. `intake/tokens.json` → apply to the `@theme` block in `src/styles/global.css` and
   mirror into the repo's `tokens.json`. If absent or values say "derive": propose a
   palette from the logo + brief and present it for sign-off before applying.
3. `intake/content.md` → parse headed sections into `src/data/services.json`,
   `faqs.json`, `cases.json`, and the About page copy. Missing sections: draft from
   `brief.yaml` notes and mark clearly as `DRAFT — review`.
4. `intake/assets/` → wire `logo.svg` into the Header and favicon; place images and
   write descriptive alt text for each.
5. `intake/redirect-map.csv` → emit edge redirect config (`public/_redirects`).
   Redirects NEVER live in page JavaScript.
6. `intake/reference/` → read for context (voice, what to preserve). Never copy verbatim.

Finish by running `npm run build`, fixing any failure, then report two lists:
APPLIED (what was set from intake) and FOR REVIEW (everything drafted or placeholdered).

**Never fabricate a client fact.** A blank field in brief.yaml becomes a visible
placeholder and a FOR REVIEW entry — not a guess.

## Component catalog — the shared vocabulary
When the user names a block below, this is what they mean and where it lives.

| Name | In plain terms | File | Variants / options |
|---|---|---|---|
| Header | Sticky top bar: logo, nav links, amber CTA button | `src/components/Header.astro` | — |
| Hero | The big top banner of a page | `src/components/Hero.astro` | `variant="split"` (headline + standards panel) or `"centered"` |
| Compliance band | Thin trust strip: regional entities + certification chips | `src/components/ComplianceBand.astro` | reads regions/certs from site.ts |
| Services grid | The service offering cards | `src/components/ServicesGrid.astro` | `detailed` prop adds bullet lists (used on /services/) |
| Case studies | Three engagement cards, each with a headline metric | `src/components/CaseStudies.astro` | content from `data/cases.json` |
| FAQ | Expandable question/answer list; also emits FAQPage schema | `src/components/FAQ.astro` | content from `data/faqs.json` |
| CTA | Closing call-to-action band before the footer | `src/components/CTA.astro` | `title` prop overrides the headline |
| Contact form | The wired lead form: honeypot, optional Turnstile, GA4 lead event | `src/components/ContactForm.astro` | endpoint/keys from site.ts |
| Footer | Three columns: identity, practice links, contact + BCSI notice | `src/components/Footer.astro` | — |
| Base head | Everything in `<head>`: meta, OG, fonts, noindex flag, GA4 | `src/components/BaseHead.astro` | do not restructure |
| Schema | ProfessionalService JSON-LD for the business | `src/components/SchemaOrg.astro` | data from site.ts |
| Base layout | The page shell wrapping header/content/footer | `src/layouts/Base.astro` | — |

Pages (file-based routes): `/` `src/pages/index.astro` · `/services/`
`src/pages/services/index.astro` · `/about/` `src/pages/about.astro` · `/contact/`
`src/pages/contact.astro` · custom 404 `src/pages/404.astro`.

Content slots: `src/data/services.json`, `faqs.json`, `cases.json`.
Design tokens: `@theme` in `src/styles/global.css` (mirrored in `tokens.json`).
Client facts: `src/config/site.ts`.

## Hard rules — never violate
- NEVER remove or hardcode the `INDEXABLE` / `noindex` logic in BaseHead.astro.
- NEVER delete JSON-LD blocks (SchemaOrg, FAQ). Update their data instead.
- NEVER rename `id="contact-form"` or form field `name`s — conversion tracking is wired to them.
- All colors/fonts via `@theme` tokens. No literal hex values inside components.
- Reuse the client's EXISTING GA4 property ID; issue NEW Turnstile keys per rebuild.
- Redirects live at the host/CDN edge, never in this codebase's JavaScript.

## Style
Aesthetic: "control-room precision" — ink/panel darks, paper sections, amber as the ONLY
accent. Type: Barlow Condensed (display, uppercase) · Public Sans (body) · IBM Plex Mono
(codes/labels). Tailwind utilities referencing theme tokens (`bg-ink`, `text-amber`,
`font-display`).
