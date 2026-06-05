# Client Intake Framework

Hand Claude Code an `intake/` folder shaped like this and it can customize a base
template end-to-end with no conversational back-and-forth. The principle: **humans and
Phase-1 extraction supply data; Claude implements everything structural.**

## The folder

    intake/
      brief.yaml          REQUIRED  — facts + build directives (the control file)
      tokens.json         OPTIONAL  — design tokens (the look)
      content.md          OPTIONAL  — all copy, by section (the words)
      redirect-map.csv    OPTIONAL  — old → new URLs (cutover)
      assets/             OPTIONAL  — logo.svg (+ images)
      reference/          OPTIONAL  — old-site screenshots, brand PDF, Phase-1 audit

Only `brief.yaml` is required. Anything omitted, Claude either derives (tokens from the
logo, copy from the brief notes) or scaffolds with a placeholder and flags it for review —
it never silently invents client facts.

## What each file is

**brief.yaml** — the one file with mandatory human input. Identity, contact, the
production domain, the handful of integration facts only the client knows (GA4 property,
form endpoint, anti-spam key), archetype-specific profile fields, and *build directives*
that tell Claude how to compose (which pages, which section variants, tone, special notes).
Claude reads this first and transcribes it into the template's `src/config/site.ts`.

**tokens.json** — colors and fonts, same shape as the template's `tokens.json`. From the
Phase-1 design extraction (matching an existing brand) or a fresh palette. If absent or set
to `derive`, Claude proposes a palette from the logo and the brief and shows it for sign-off.
Claude applies these to the `@theme` block in `src/styles/global.css`.

**content.md** — every piece of copy under clear section headings (Services, FAQ, Case
studies, About). Claude parses it into the template's `src/data/*.json` content slots. If a
section is missing, Claude drafts from `brief.yaml` `notes` and marks it `DRAFT — review`.

**redirect-map.csv** — two columns, `old_path,new_path`. Claude turns this into edge-config
(e.g. a `_redirects` file), never into in-page JavaScript.

**assets/** — `logo.svg` (vector, not a scraped PNG) plus any photography. Claude wires the
logo into the header/favicon and references images by filename.

**reference/** — context Claude reads but does not reproduce: old-site screenshots, a brand
guidelines PDF, the Phase-1 audit. Shapes decisions; never copied verbatim.

## What Claude generates (do NOT put in intake)

Schema/JSON-LD · meta titles & descriptions · OG images · image alt text · semantic markup ·
the sitemap · the component composition itself. Providing these is wasted effort — they are
derived from the data above.

## Read & apply order

1. `brief.yaml`   → `src/config/site.ts` + decides pages and variants
2. `tokens.json`  → `@theme` in `src/styles/global.css` (mirror back into the repo's tokens.json)
3. `content.md`   → `src/data/services.json`, `faqs.json`, `cases.json`
4. `assets/`      → header logo, favicon, image references
5. `redirect-map` → edge redirect config
6. `reference/`   → context only

After applying, Claude runs `npm run build` to verify, then reports what it drafted or
placeholdered for review.

## How to invoke it

Drop the `intake/` folder into a fresh copy of the base template and tell Claude Code:
*"Customize this template from the files in `intake/`."* That single prompt replaces the
line-by-line description.
