---
name: site-baseline
description: This skill should be used to run or interpret the automated discovery baseline on an existing website (scrape, crawl, extract, audit). Trigger when a new client pipeline starts, when asked to "run the baseline", "scrape <domain>", or when assembling a prototype from baseline outputs.
---

# Site Baseline — three-method discovery scrape

## Purpose
Turn a domain name into the 01-baseline/ deliverables that seed the prototype and
the intake. Three independent capture methods cross-validate URL coverage:
1. **crawl.py** — HTTP crawler (requests+bs4): structure, content, metadata, forms, SEO signals
2. **render_capture.py** — headless Chromium (playwright, optional): JS-rendered pages,
   full-page desktop+mobile screenshots, computed colors/fonts, XHR/fetch endpoints
3. **mirror.sh** — wget archive: raw fallback copy + independent URL census

## Run
Normally studio.py launches `scripts/run_baseline.py <domain> <client_dir>` automatically.
Manual: same command. Each script is independently runnable for retries.

## Outputs (the contract)
00-source/: crawl.json, mirror/, rendered/ (render.json + screenshots), scrape.log
01-baseline/: url-inventory.csv · content-draft.md · tokens-draft.json ·
metadata-audit.md · tech-fingerprint.md · coverage.md · perf-baseline.md ·
feature-census.md

`feature-census.md` (scripts/feature_census.py, runs after extract; also standalone:
`python3 feature_census.py <client_dir>`) detects the site's macro-features (search,
filter/sort, pagination, cart/checkout, accounts, wishlist, newsletter, category nav,
contact, pixels, reviews) and classifies each CARRY-OVER / STUB+FLAG / OBSOLETE. CARRY-OVER
is the prototype's parity floor; STUB+FLAG rows name the deliverables §2.7 fact that unblocks
them. A second tool, `scripts/extract_catalog.py`, pulls a real product catalog (name+photo
per source page) from the mirror for image-bearing builds.

`block-purpose-map.md` is also written into 01-baseline/ — but at BUILD time (Command 1 /
"Finish"), not by the scrapers. It is the Purpose-first reconstruction audit trail: a table
mapping each source block (page + identifier) → its purpose designation → the target component
→ the improvement made, proving every original block was understood rather than transcribed.

## Interpreting for the prototype
- coverage.md lists paths missed by any single method — investigate before trusting the inventory.
- tech-fingerprint.md GA4 IDs and detected services seed brief.yaml integrations and the
  owner questionnaire focus.
- content-draft.md and tokens-draft.json are DRAFTS: scraped, ownership unverified.
  Apply them to the prototype clearly marked DRAFT; the owner's answers confirm or replace.
- url-inventory.csv seeds 02-intake/redirect-map.csv (old column = inventory, new = proposed).
- If a page's word_count is near zero but the rendered method captured text, the site is
  JS-rendered — prefer method-2 data and note it.

## Failure modes
Crawl blocked (403/0 statuses) → retry with the mirror; if both blocked, note it and fall
back to the rendered method. Playwright/wget missing → pipeline continues on method 1 and
coverage.md says so. Never silently substitute guessed content for failed scrapes.
