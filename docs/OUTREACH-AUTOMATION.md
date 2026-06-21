# OUTREACH-AUTOMATION — automated targeted client outreach (directions to implement)

**Goal:** automate the front of the web-studio sales funnel — *source* cold target businesses, find
the owner + a valid email, *qualify* by whether their website genuinely needs a rebuild, draft a
personalized pitch, and stage it to Reply.io — with a human approval gate before anything sends. This
is the growth loop that feeds the rebuild product (PRODUCT-PLAN §4: "diagnose prospects → invite to
self-serve").

> **Non-redundancy is the prime directive of this plan.** web-studio already has most of the parts.
> The new code is *only* the automated-sourcing front-end + the funnel glue. Everything expensive
> (the website diagnostic, contact/email enrichment + validation, Reply.io upload, dedup) is
> **reused, not rebuilt.** See §1.

---

## 1 · Reuse map — what already exists (DO NOT duplicate)

| Capability | Existing asset | Verdict |
|---|---|---|
| Website rebuild verdict (the qualifier) | `.claude/skills/site-diagnostic/` (`diagnose.py`) + `studio.py` outreach runner (`create_outreach_run`, `outreach_runner`, `outreach_row_command`, `_finish_outreach_row`, `write_outreach_report`) | **REUSE as-is** |
| "Who we've touched" (dedup) | `outreach/masterfile.csv` (`domain,company,url,date_processed,industry,standard,verdict,score,top_problems,contact_status,run_id`) | **REUSE + extend** |
| Pitch drafts (measurable-lead, taste-soft, no fabrication) | the Outreach tab → `outreach/drafted-emails.csv` (SYSTEM.md §7b) | **REUSE** |
| Contact sourcing + email find/validate + Reply.io | wavelength **`company-processor`** skill + MCP: `apollo_enrich_person`/`apollo_bulk_enrich_people`/`apollo_enrich_org`, `validate_email` (Clearout), `zb_validate_email` (ZeroBounce), `bulk_validate`/`bulk_status`/`bulk_results`, `check_credits`, `reply_list_sequences`/`reply_push_contacts`/`reply_search_contact` | **REUSE — never rebuild** |
| Lead scoring / force-rank shortlist | wavelength **`grata-search-enrichment`** | **ADAPT** (swap the fit function: rebuild-candidacy, not PE thesis) |
| Resumable run state + pacing | `outreach/runs/<id>/run-state.json`; `OUTREACH_PACING_S`, `BG_SEM`, `CLAUDE_SEM` | **REUSE** |
| Shared memory / learnings | MCP `query_context`/`update_context`, `get_skill_learnings`/`save_skill_learning` | **REUSE** |

**Net-new code (small):** (a) an **Apollo sourcing adapter** that replaces the manual Grata upload as
the queue's origin; (b) the **funnel orchestrator** that chains the reused stages with dedup +
cheap-before-expensive gating; (c) a **contact↔company↔draft join** (one new `contacts.csv` layer);
(d) ICP **segment configs**. Nothing else.

We do **not** author a new skill (the three above cover it) and do **not** re-implement diagnostics,
enrichment, validation, or Reply.io. The orchestrator is a thin extension of the existing
`studio.py` outreach runner + the MCP tools.

---

## 2 · Token / credit efficiency (explicit — this is a hard requirement)

Every expensive operation (Playwright render, PageSpeed, Claude draft, Apollo credit, email-validation
credit) runs on the **smallest possible qualified set**, late in a narrowing funnel:

1. **Dedup first.** Drop anything already in `masterfile.csv` *before* any paid/LLM/render op.
2. **Cheap → expensive ordering.** Firmographic + a cheap site signal filter the list *before* the
   full `site-diagnostic` runs; contact enrichment + the Claude pitch draft run *only* on
   diagnostic-qualified rebuild candidates. The expensive tail is a fraction of the sourced top.
3. **Reuse cached diagnostics.** `outreach/prospects/<domain>/` already caches a run — never
   re-diagnose a domain we've scored.
4. **Cheap model for triage, capable model only for the draft.** Industry/fit classification →
   Haiku; the final personalized email → the standard model. One capable-model call per *qualified*
   lead, not per sourced lead.
5. **Batch the credit calls.** `apollo_bulk_enrich_people` (10/call); `bulk_validate` for >20 emails;
   `check_credits` before any batch.
6. **Key PageSpeed Insights.** Memory: the unkeyed PSI API 429s — set the key before batch runs or
   we waste retries (and the diagnostic falls back to local-load, losing signal).
7. **Cap + resume.** Per-run volume cap; resumable `run-state.json` so a stop never re-spends.
8. **Never re-draft / re-validate.** `contact_status` gates each stage; a `drafted`/validated row is
   skipped on re-runs.

Target funnel shape (illustrative): 1000 sourced → ~700 after dedup → ~400 after cheap pre-qual →
~400 diagnosed → ~120 rebuild candidates → ~120 contacts enriched + validated → ~100 drafted → human
review → staged. The two costliest stages (diagnose, draft) touch ≤40% and ≤12% of the sourced top.

---

## 3 · The automated funnel (each stage → the reused tool + the gate)

```
A. ICP segment  →  B. SOURCE (Apollo)  →  C. dedup vs masterfile  →  D. cheap pre-qual
   →  E. QUALIFY: site-diagnostic (rebuild verdict)  →  F. contact+email enrich/validate (Apollo+MCP)
   →  G. draft pitch (from the diagnostic's top-3 problems)  →  H. HUMAN REVIEW (gate)
   →  I. stage to Reply.io sequence  →  J. record (masterfile + contacts + learnings)
```

- **A — Segment / ICP** *(new, tiny)*: `outreach/segments/<name>.yaml` — vertical (nurseries /
  small-shop commerce per ADR-0002), geo, size band, owner titles, optional platform signal
  (Wix/Squarespace/Volusion/old). Reusable + versioned.
- **B — Source** *(new — the core automation)*: `apollo_search_people` by the ICP (owner/founder/CEO
  titles + industry + geo + size) → companies + people, written into the **existing** run-state queue
  shape. The manual **Grata upload path stays** (`infer_outreach_mapping`/`parse_outreach_sheet`/
  `create_outreach_run`) — both feed the same queue. This replaces "a human must hand me a list."
- **C — Dedup** *(glue)*: skip domains/contacts already in `masterfile.csv`/`contacts.csv`
  (suppression). The masterfile is the source of truth for "touched."
- **D — Cheap pre-qual** *(glue, Haiku)*: firmographic sanity + a cheap homepage signal (one light
  fetch / platform fingerprint) to drop obvious non-candidates before the full render-based diagnostic.
- **E — Qualify = `site-diagnostic`** *(REUSE)*: the existing runner produces the two-axis rebuild
  verdict + score + top-3 measurable problems. **Only `strong-candidate`/`candidate` (low score)
  proceed.** This is the "targeted" core: we only pitch businesses whose sites genuinely need a
  rebuild — and it's the existing engine, unchanged.
- **F — Contact + email** *(REUSE company-processor + MCP)*: for qualified domains only, find/confirm
  the owner-operator + email via `apollo_enrich_person`/`apollo_bulk_enrich_people`, validate via
  `validate_email` + `zb_validate_email` (or `bulk_validate`). Owner-operators only (the skill's role
  filter). Either call the `company-processor` skill on the qualified set, or a thin adapter that
  makes the same MCP calls — **no new validation/enrichment logic.**
- **G — Draft** *(REUSE)*: personalize from the diagnostic's top-3 *measurable* problems (measurable
  lead, taste softened, no fabricated deficiencies, no spam patterns) → `drafted-emails.csv`.
- **H — Human review** *(REUSE, the gate)*: the Outreach tab review surface. **Nothing sends
  automatically.**
- **I — Stage to Reply.io** *(REUSE)*: `reply_list_sequences` → pick; `reply_push_contacts` (batches
  of ~50). Sending happens in Reply.io with CAN-SPAM (see §7).
- **J — Record** *(glue)*: update `masterfile.csv` + `contacts.csv` + `contact_status`; `save_skill_learning`.

---

## 4 · Data model (unify the two existing layers; one new file)

- **Company layer** — `outreach/masterfile.csv` (existing). Extend `contact_status` to a funnel state:
  `sourced → deduped → pre-qualified → diagnosed → candidate → contacted-enriched → drafted → staged
  → emailed`; add `source` (apollo|grata) + `segment`.
- **Contact layer** — `outreach/contacts.csv` (**new**, = company-processor's master CSV shape, joined
  by `domain`): `domain, company, first_name, last_name, title, email, linkedin, clearout_rating,
  zerobounce_rating, apollo_id, status`.
- **Draft layer** — `outreach/drafted-emails.csv` (existing).
- **Segments** — `outreach/segments/<name>.yaml` (new). **Runs** — `outreach/runs/<id>/` (existing).
- **Join key:** `domain` (company-name fallback). All of `outreach/` is git-ignored (real-business data).

---

## 5 · Targeting / fit (the "targeted" definition)

`fit = in-target-vertical AND website-is-a-rebuild-candidate (diagnostic) AND reachable
owner-operator with a valid email AND not previously touched.`

Force-rank qualified leads by **diagnostic score (worse site → higher priority) × vertical match ×
contactability**. This reuses `grata-search-enrichment`'s force-rank pattern with the fit function
swapped from investment-thesis to rebuild-candidacy — so we spend outreach on the businesses most
likely to convert (bad site + reachable owner + our vertical).

---

## 6 · Guardrails (reuse SYSTEM.md §7 doctrine — binding)

- **Honesty (binding):** measurable claims verified-true, judged claims flagged opinion, **never
  fabricate a deficiency**, a challenge-page capture is NOT-SCORABLE not judged. (Already enforced by
  the diagnostic.)
- **Sourcing boundary:** licensed data only — Apollo + owner-authorized exports. **Never bot-scrape**
  Apollo/LinkedIn/marketplaces or the prospects' sites beyond the polite diagnostic crawl.
- **Send is a separate, human-gated layer:** nothing emails from this pipeline. Sending (Reply.io)
  must carry **CAN-SPAM**: unsubscribe mechanism + the studio's physical mailing address + accurate
  From/subject + **per-recipient suppression honoring the masterfile**. (SYSTEM.md §7b.)
- **Dedup/suppression** against the masterfile before contact, always.
- **Credit/rate caps:** `check_credits` before batches; per-run volume cap; existing semaphores/pacing.

---

## 7 · Implementation phases (what I'll build — reuse-first, glue-only)

1. **Segment config + Apollo sourcing adapter** — `outreach/segments/*.yaml` + a script that runs
   `apollo_search_people` for a segment and writes rows into the existing run-state queue. (New, small.)
2. **Dedup + cheap pre-qual** — filter the queue against `masterfile.csv`; a Haiku triage pass. (Glue.)
3. **Qualify** — route survivors through the **existing** `site-diagnostic` outreach runner (no new
   diagnostic code); keep only rebuild candidates.
4. **Contact + email** — on candidates, reuse `company-processor`/MCP for enrich + validate; write
   `contacts.csv`. (Adapter, no new enrichment logic.)
5. **Draft + review + stage** — reuse `drafted-emails.csv` drafting + the review surface; stage via
   `reply_push_contacts`.
6. **Orchestrator + dashboard + schedule** — chain 1–5 into one paced, resumable headless run
   (extend `studio.py` outreach functions); surface on the Outreach tab; optional cron via the
   `schedule` skill — **review gate before any send stays.**

Each phase ends with the funnel metrics (§2) recorded so cost stays visible. Reuse is verified per
phase against §1 before writing any new code.

---

## 8 · Open decisions (resolve before Phase 1)
1. **Primary source:** Apollo search (fully automated) vs Grata exports vs both. *Lean: both; Apollo is the automation.*
2. **Launch segment:** which ICP first. *Lean: nurseries / small-shop commerce (ADR-0002), a chosen metro.*
3. **Send layer:** stage-to-Reply.io with manual approve now; build an automated CAN-SPAM send layer later. *Lean: manual approve now.*
4. **Schedule:** sourcing batch cadence + per-run cap (cost ceiling).
5. **Apollo/validation credit budget** per run.
