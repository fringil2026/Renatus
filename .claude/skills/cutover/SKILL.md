---
name: cutover
description: This skill should be used for launch preparation and verification of a rebuilt website — pre-cutover checks, redirect validation, DNS zone comparison, and post-launch monitoring. Trigger on "cutover", "launch", "go live", "prechecks", or zone-file review requests.
---

# Cutover — launch checks with deterministic scripts

## Scripts (scripts/)
- `launch_check.py <url> [--production]` — fetches the live site and verifies:
  meta-robots noindex (must EXIST on staging, must NOT on production), robots.txt not
  blocking, canonical present, title/meta present, OG tags, JSON-LD present, custom 404.
- `redirect_check.py <map.csv> <base_url>` — requests every old path; verifies exactly
  one 301 hop landing on the mapped new URL; flags chains, 404s, and blanket-to-home.
- `zone_diff.py <before.txt> <after.txt>` — diffs DNS zone exports; ERRORS on any
  missing/changed MX, SPF, DKIM, DMARC, or subdomain record.

## Procedure: "Run cutover prechecks for <slug>"
1. `launch_check.py` against staging (expect noindex PRESENT) → 04-cutover/precheck-staging.md
2. `redirect_check.py` with 02-intake/redirect-map.csv against the staging/preview host
3. If the human supplies zone exports, `zone_diff.py` before vs planned-after
4. All pass → stage=cutover-checked. Any fail → report, do not advance.

## Launch day (human executes; Claude verifies)
Step zero: human flips PUBLIC_INDEXABLE=true and redeploys → immediately run
`launch_check.py <prod-url> --production` (expect noindex ABSENT). Then redirect_check
against production, form end-to-end test, email send/receive test, submit sitemap.
Days 1–28: feed CDN 404 logs and Search Console exports back in; unexpected 404s
get appended to the redirect map and redeployed.

## Hard boundaries
Never modify DNS, never advise deleting records, never touch MX/SPF/DKIM/DMARC —
zone work is verify-and-diff only. These rules hold even mid-task.
