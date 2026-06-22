---
name: site-diagnostic
description: This skill should be used to diagnose whether an existing website is a rebuild candidate — one URL in, a two-axis industry-aware verdict out (visual maintenance/modernity + industry completeness). Trigger on "Diagnose site <url>", "Run outreach diagnostic for <company> — <url>", or any request to assess a prospect's website for the outreach pipeline.
---

# Site Diagnostic — the outreach verdict engine

## Purpose
One URL → a trustworthy, evidence-backed REBUILD VERDICT. This feeds outreach emails to
real business owners, so the honesty rules below are binding: a single false "your site
isn't mobile-friendly" to a responsive site burns the lead and the studio's name.

Artifacts live under `outreach/prospects/<domain>/` (studio-level, git-ignored — NOT a
client; never write under `clients/`).

## Procedure

### 1. Capture (script — the measurable half)
```
python3 .claude/skills/site-diagnostic/scripts/diagnose.py <url> outreach/prospects/<domain>/
```
(`<domain>` = host without `www.`, e.g. `outreach/prospects/arngren.net/`.) Writes
`capture/home-desktop.png`, `capture/home-mobile-390.png`, `capture/home.html`,
`diagnostic.json` (every measurement with its evidence string), `MEASURABLES.md`.
- Exit 2 = unreachable by every method → verdict is **UNREACHABLE** (dead site / hard
  block); record it honestly and stop — never diagnose a site you could not see.
- `challenge_suspected: true` in the JSON means the screenshots may show a bot
  interstitial, not the site. LOOK at the screenshots before judging anything; if they
  show a challenge page, the judged axis is **NOT SCORABLE** (say so) and only
  network-level measurables (https, PSI if it returned) may be claimed.
- For batch/outreach runs, `--skip-psi` is allowed when PSI keeps timing out; the
  performance component then falls back to measured load time (lower confidence —
  phrase performance claims accordingly).

### 2. Industry classification (1A — do this before judging)
From the crawled content (`diagnostic.json` → `completeness.page_titles`,
`nav_link_sample`, `jsonld_types`, commerce signals) classify the business's industry in
plain words (e.g. "specialty plant nursery — ecommerce catalog", "residential HVAC
contractor — local service"). Then resolve the DIAGNOSTIC STANDARD, first match wins:
1. **Existing archetype** — if it's a commerce catalog, the standard is
   `templates/ecommerce-catalog/ECOMMERCE-GUIDELINES.md` + `playbooks/ecommerce-catalog.md`.
   A NERC-CIP/compliance org → `templates/nerc-cip-base/` + `playbooks/nerc-cip-compliance.md`.
2. **Existing playbook** — any file in `playbooks/` matching the industry.
3. **NEW industry** — generate `playbooks/<industry-slug>.md` from `playbooks/_TEMPLATE.md`:
   research what is table-stakes for that sector (required sections, trust signals,
   conversion elements, schema, legal must-haves) and fill every template section. The
   playbook is REUSED by every future prospect in that industry. Surface it for review:
   write a studio report `.claude/reports/<YYYY-MM-DD-HHMM>-new-industry-playbook-<slug>.md`
   summarizing what was generated and why (non-blocking — the run continues).
Record in the report WHICH standard was used (file path + whether it was pre-existing or
generated this run).

### 3. Axis 1 — visual maintenance / modernity (PRIMARY)
**Measurable (from diagnostic.json — objective, high confidence):** responsive verdict,
PSI/Core-Web-Vitals, HTTPS posture, dated-tech tells (table layout, Flash, jQuery era,
pre-HTML5 doctype, fixed widths, stale copyright), a11y basics (alt coverage, contrast
sample, lang, labels), mixed content. Quote the script's evidence strings verbatim —
never restate a measurable more strongly than its evidence + confidence supports.
**Judged (OPINION — score the two screenshots on this fixed 1–5 rubric):**

| dimension | 1 | 3 | 5 |
|---|---|---|---|
| Layout modernity | mid-2000s table/portal look | dated template but ordered | current-decade layout craft |
| Typographic quality | default system serif/sans soup | readable but characterless | deliberate pairing + hierarchy |
| Designed vs templated | obviously untouched template | template, lightly customized | clearly designed for this business |
| Visual cohesion | clashing colors/spacing chaos | inconsistent but navigable | one coherent visual system |
| 2026 trust impression | "is this site abandoned?" | passable, dated | instills confidence instantly |

One sentence of reason per score, each citing something VISIBLE in the screenshot
("hero is a stretched 400px JPEG", "12 colors in the nav alone"). Every judged score is
flagged **OPINION** in the report. Judge the MOBILE screenshot too — a desktop-fine site
that's broken at 390px is a finding (measurable if the overflow signal corroborates).

### 4. Axis 2 — industry completeness
Walk the resolved standard's required sections / trust signals / conversion elements
against `completeness.*` signals AND what the screenshots show. Each gap is a concrete,
nameable deficiency with the evidence that it's absent ("no contact form on any of the
9 crawled pages; the only phone number is in a JPEG"). Absence claims require the crawl
to have actually covered the site: if `pages_ok` < 4, downgrade absence claims to
"not found on the pages we could sample" — never assert a hard absence from a thin crawl.
Mark each gap CRITICAL (table-stakes for the industry) or NICE-TO-HAVE.

### 5. Verdict
Weighted: Axis 1 measurable (highest), Axis 1 judged, Axis 2.
- **STRONG REBUILD CANDIDATE** — not-responsive OR ≥3 dated-tech tells OR measurable
  score < 45, PLUS ≥1 critical industry gap or judged avg ≤ 2.
- **REBUILD CANDIDATE** — measurable score 45–65 with real gaps, or judged avg ≤ 2.5 on
  a measurably-mediocre site.
- **BORDERLINE** — modern-ish but incomplete, or dated but complete; one-liner says which.
- **SKIP — modern & complete** — responsive, decent perf, no critical gaps, judged ≥ 3.5.
- **UNREACHABLE / NOT SCORABLE** — per step 1.
Plus a one-line summary ("dated, non-responsive, missing core ecommerce components —
strong rebuild candidate").

### 6. Top 3 marketable problems
The outreach-ready hooks a rebuild would fix. MEASURABLE problems lead (provable:
"doesn't adapt to phones — no viewport meta, content renders at 1024px on a 390px
screen"); judged/taste problems are phrased softly ("the design could feel more
current") and NEVER as fact. Each must trace to evidence in this diagnostic.

### 7. Report (findings-on-dashboard convention)
Write `outreach/prospects/<domain>/report.md`:
```
# Site diagnostic — <domain> (<verdict>)
<one-liner>
## Industry & standard      (classification + standard file + pre-existing/generated)
## Rebuild verdict          (verdict + score + reasoning)
## Axis 1 — visual maintenance/modernity
   measurable scorecard (score/100 + component table from diagnostic.json)
   judged scorecard (1–5 table, each row flagged OPINION with its one-sentence reason)
## Axis 2 — industry completeness (gaps: CRITICAL / NICE-TO-HAVE, each with evidence)
## Top 3 marketable problems
## Evidence (screenshots, diagnostic.json path, pages sampled, capture caveats)
```
For a STANDALONE diagnostic (not a batch run), also write a studio report
`.claude/reports/<YYYY-MM-DD-HHMM>-site-diagnostic-<domain>.md` (summary + link to the
prospect folder) so it shows on the dashboard. Batch runs write ONE run-level summary
report instead (the Outreach runner owns that).

## Outreach mode (batch rows — triggered as "Run outreach diagnostic for <company> — <url> (outreach run <id>)")
Everything above, plus write `outreach/prospects/<domain>/result.json` — the machine
contract the Outreach runner consumes (the runner owns the masterfile and the
drafted-emails spreadsheet; do NOT write those files yourself):
```json
{
  "domain": "...", "company": "...", "url": "...",
  "industry": "...", "standard": "playbooks/....md", "standard_generated": false,
  "verdict": "strong-candidate | candidate | borderline | skip | unreachable | not-scorable",
  "one_liner": "...", "measurable_score": 0-100, "judged_avg": 1.0-5.0,
  "top_problems": ["...", "...", "..."],
  "candidate": true,
  "email": {"subject": "...", "body": "..."}   // null unless candidate
}
```
`candidate` = verdict is strong-candidate or candidate. Keep `report.md` as above.

### Email draft rules (drafting only — nothing is ever sent from this skill)
- Personalized from THIS site's diagnosed problems; lead with the provable/measurable
  ones, soften taste ones ("could feel more current"). NEVER state a false or
  unverified deficiency; never mention a problem that isn't in the report.
- Tone: a competent local studio that actually looked at their site. Concise (~120–170
  words), concrete, zero spam patterns (no ALL CAPS, no fake urgency, no "Dear Sir").
  Name the business. Imply the fix and our service; end with a low-pressure ask.
- No invented claims about their business, traffic, or revenue. No compliance footer
  here — unsubscribe + physical address get added at the SEND step (see SYSTEM.md).

## Honesty rules (binding)
1. Measurable claims must be TRUE and verified by the script's evidence; when signals
   disagree (responsive = "partial"), say what was observed, not a conclusion.
2. Judged claims are opinion, flagged as such, softened in outreach copy.
3. Never fabricate a deficiency; never assert absence from a thin crawl (step 4).
4. A challenge-page capture is NOT the site — mark NOT SCORABLE rather than judging it.
5. Confidence travels with the claim, from diagnostic.json all the way into the email.
