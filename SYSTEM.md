# SYSTEM.md — Web Studio internals

How the studio's resilience + quality systems work. Companion to CLAUDE.md (the operating contract)
and CONTEXT.md (background). Two systems live here: the **scrape ladder** (getting real evidence even
from bot-blocked sites) and the **parity verification loop** (no prototype ships on belief).

---

## 1 · The scrape ladder (`.claude/skills/site-baseline/scripts/run_baseline.py`)
An ESCALATING CASCADE, not a fixed method list. Each fallback rung runs only when the rungs above it
captured insufficient content. **Politeness is law on every rung** — identified/default-browser UA,
generous delays, bounded retries; two failed unblock attempts means move DOWN the ladder, never an
arms race against active blocking.

| Rung | Tool | Role | Runs when |
|---|---|---|---|
| 1 | crawler (`crawl.py`, requests) | fast, polite first pass | always |
| 2 | rendered browser (`render_capture.py`, Playwright/Chromium) | the **primary anti-bot weapon** — real fingerprint, human-pace nav | always (if installed) |
| 3 | wget mirror (`mirror.sh`) | **breadth** archive + URL census | only when rungs 1–2 are getting content |
| 4 | Wayback archive (`archive_fetch.py`) | last-resort evidence when blocked | only when live rungs are blocked |
| 5 | human | decision card w/ a ready-to-send owner-export note | only when all rungs are insufficient |

**Block detection (rung 1):** a REAL block = HTTP 4xx/5xx on the homepage, OR the Cloudflare
challenge marker `/cdn-cgi/challenge-platform/` WITH little real content (a true interstitial). The
challenge script ships inside ordinary 200 pages, so its presence ALONE is NOT a block
(WS-INC-SEATTLE-ORCHIDS-001 — it once discarded a 150-page live crawl for stale archive). Render-rung
success counts captured screenshots (`*-desktop.png` / `render.json`), not `.html` files.

**Missing tools never silently skip.** `wget` and Playwright availability are checked; if absent the
rung is logged LOUDLY (`‼ RUNG n FAILED`) and counts as a rung failure with the install command.

**Mirror caps are bounded but env-overridable** for the rehearsal completeness pass:
`MIRROR_MAX_FILES` / `MIRROR_MAX_SECONDS` (defaults 300 / 300s) — deliberate + logged, never unbounded.

**Evidence provenance.** `00-source/evidence-source.txt` records `LIVE` / `ARCHIVE` / `NONE`.
ARCHIVE content (Wayback, labelled `ARCHIVE-<snapshot-date>`) is STALE — usable for design tokens,
copy drafts, and the feature census, **never as current price/stock truth**. The feature census folds
archive HTML into its evidence and labels its source; tokens-draft does the same.

**Reporting.** `01-baseline/coverage.md` records every rung attempted, its result, and which rungs the
final baseline rests on.

**Platform catalog enumeration.** Some platforms hide the catalog from category-link following.
Volusion (WS-INC-SEATTLE-ORCHIDS-002) exposes all products only in `/sitemap.xml` as
`/<Name>-p/<alphanumeric-sku>.htm` — the generic crawler caps out on category `-s/` pages and captures
zero products. When the evidence fingerprints Volusion, the ladder runs `scrape_volusion.py`
(sitemap → product URLs → polite static-HTML parse: `og:title`, `og:image`, "Our Price $X" as DRAFT)
→ `01-baseline/catalog-draft.json`. This is URL-DISCOVERY + platform-parse, never an unblocking trick
(no proxy/CAPTCHA/token evasion — that boundary stays). Build a platform extractor to the diagnosed
cause, not a guessed one.

**Platform image patterns.** Photos are also platform-specific. Miva (WS-INC-ORCHIDS-BY-HAUSERMANN-001)
lazy-loads the product photo via `<img id="js-main-image" data-image="graphics/00000001/<GUID>.jpeg">`
— the static `src` is a blank.gif placeholder, so a generic `<img src>` extractor captures nothing.
`extract_miva_images.py` reads each product's own `source_page`, pulls `data-image`, downloads the real
photo, and pairs it to that product (same page ⇒ correspondence-safe). Diagnose the actual image markup
(src vs data-src/data-image vs srcset vs background-image vs CDN) before fixing; honest low-res findings
become a D-2.7.4 photography ask, never invented/upscaled images.

---

## 2 · The parity verification loop (CLAUDE.md "Verification loop — binding")
The feature census is a binding CHECKLIST; no prototype returns until every line is verified or
honestly blocked.

**The artifact** (`feature_census.py` → `01-baseline/parity-checklist.md`): one row per feature with
a checkbox, its census classification, and a CONCRETE VERIFICATION METHOD a later session can execute
mechanically against `dist/` (e.g. "dist/shop/ has a search input that filters cards"). Plus standing
gate rows on every build: build passes · zero banned design patterns · noindex present · mobile
~390px structure · correspondence verifier 0 mismatches · brand moment named+placed. **A row without
an executable verification method is itself invalid.**

**The loop** (after assemble; also after "Process edits" and at "Finish"; the rehearsal chain runs it
at assemble AND after Phase 4 with backend rows): execute each row's method against the BUILT OUTPUT —
never intentions or remembered source. For each unmet row: fix → `npm run build` → re-verify that row
+ any row the fix could disturb. Iterate to `[x]` verified-with-evidence or `[B]` BLOCKED (naming the
missing deliverable ID — never a euphemism for "didn't get to it"). **HARD CAP 5 iterations**; at the
cap, STOP, report survivors as honest failures + open a decision card. The completed checklist (per-row
evidence one-liners + iteration count) is pasted into the build report and committed with the build.
**Publish-always runs only after the loop exits.**

---

## 3 · Dashboard action surface + full build (`studio.py`)
Enforcement of the decision-surfaces rule: **no stage's only path is typing in a terminal.** The
`NEXT` map holds STATUS DESCRIPTIONS only (never `claude → "…"` commands); every actionable stage
carries a real button, and the `⧉` copy-command link is the terminal escape hatch.

| Stage | Control |
|---|---|
| queued / created / scraping | transient auto states — descriptive status, no action (machine wait) |
| error | **Rerun** button |
| baseline-ready | **Assemble prototype** + **Full build — from scratch** (concept boards in the row) |
| prototype / awaiting-owner | **paste box** (owner answers) · **Configure backend** · **Full build — from this prototype** · Phase-2 Advance once a BINDING config exists |
| answers-received | **Finish** + **Full build — from this prototype** |
| final | **Run cutover prechecks** + **Full build — from this prototype** |
| cutover-checked | **Archive** |

**Full build** (CLAUDE.md Command 10) — one chain, two stage-gated variants (`from-scratch`,
`from-prototype`), mutually exclusive. `studio.py` owns the control surface: stage gate
(`full_build_action`), slug-typed confirm + test-credential precondition (`/api/full-build`,
`test_creds_ready` — disabled with a tooltip until `secrets/.env` carries `# REHEARSAL` creds), the
step artifact `02-intake/full-build-progress.json` (`init_full_build`), the live row step-log, and
**resume** (re-running keeps the artifact; `claude -p` skips `done` steps via the runbook in
`full_build_runbook`). TEST banners + cutover-refusal are unchanged.

## 4 · Concept boards (the visual concept decision)
After the scrape, before any prototype, the human picks from real designs spanning a **creativity
spectrum**, not documents. `.claude/skills/site-baseline/scripts/concept_boards.py` reads
`02-intake/concepts/concepts.json` and emits distinct static board HTML under
`02-intake/concepts/site/concepts/<letter>/` (noindex, no JS, "CONCEPT BOARD — not the final build"
banner), desktop+390px Playwright screenshots, and `boards.json`. Boards deploy to
`ws-<slug>.pages.dev/concepts/a|b|c/` (disposable — replaced at the first prototype publish; PNGs
persist).

**Mandatory divergence (the spectrum).** The three base boards are A·**classic** (safe,
conversion-proven), B·**confident** (the recommendation), C·**bold** (pushes hard). Each `tier` maps
to a STRUCTURALLY distinct archetype (`archetype_css`: classic = centered/symmetric + CTA; editorial
= asymmetric + signature legend + featured-card grid; dramatic = oversized type + staggered grid;
experimental = numbered-index nav + viewport hero + broken collage). `divergence_check()` is BINDING:
the base boards must differ in layout archetype AND `type_attitude` AND `structural_idea`, with exactly
one recommended — else the generator prints FAIL and exits non-zero (regenerate). Three palettes on one
layout is a generation failure.

**The wow lever — "🔥 Push further".** A fourth control on the decision card (only after the 3 boards
exist; generative, no slug confirm) enqueues `/api/push-further` → a headless job producing **Board D**:
experimental, BEYOND bold (break conventions; still honor the hard rules). D publishes at `/concepts/d/`,
screenshots, and joins the card as a fourth `tag: experimental` option. Fires once more for **Board E**;
**capped at two escalations** (a–e) — beyond that the studio refuses and points to a decision note. The
concept decision YAML carries `tier`/`board_url`/`thumb` per option; the "Needs your call" card renders
the screenshots as clickable thumbnails (served via `/api/concept-thumb`), recommendation + experimental
badges marked. Choosing any letter resolves it as before; full-build-from-scratch auto-accepts Board B —
wow stays human-in-the-loop.

**The creativity model (ONE hierarchy, no overlaps).** Three tiers; creative is **ONE button, ONE
entry point**:
| Control | When it appears | What it does | Input modes |
|---|---|---|---|
| **STANDARD** | always (default) | clean, purpose-fit; full Design QA Gate + brand moment. Built via **Advance / Full build — standard BY DESIGN, they ignore `design_mode`** | — |
| **PUSH FURTHER** (🔥) | on the boards card, after A/B/C exist | generates ONE bolder board (D, then E; cap 2) — a board generator, standard effort | — |
| **CREATIVE / WOW build** (🎨) | **ONE button on the boards decision card** (the boards step) | `design_mode: creative` — **bypasses the A/B/C boards** and builds **from scratch** with full creative craft = **disciplined graphic richness + smooth interactivity** (section scroll narrative, scroll-reveals, hover category tiles, slide-out drawers, condensing sticky header, ONE signature motion moment) | **"Claude develops it"** (Claude reaches on its own) · **"Guide with text"** (paste a direction into `overhaul-brief.md`) — both build from scratch |

Code (ONE clean path, no silent downgrade): the **Creative / Wow build** button (`renderNeeds` →
`openOverhaul` → `#ovmodal`) hits **`/api/overhaul`** only; it sets `design_mode: creative`
(+ `overhaul_input`) via `set_design_mode`, closes any open A/B/C board decision (bypass), and enqueues
`overhaul_runbook()` which ALWAYS injects `creative_clause()`. Brief mode creates/awaits
`02-intake/overhaul-brief.md` (first click arms it, second click builds). **Advance and Full build are
standard by design** and do not read `design_mode`. **Three HARD invariants across every tier:** parity
floor untouched · all Hard rules untouched · expression-only (layout/type/colour/motion/interactivity/
graphics, never facts/features/guardrails); the verification loop / parity checklist still runs.

**Images on the creative path (fixed — WS-INC-STUDIO).** Because creative reimagines components FROM
SCRATCH, dropped images were a real failure mode (no carry-over instruction + the loop wasn't invoked
+ no image row). Now: `creative_clause` explicitly orders "carry over EVERY source image (re-import the
records); expression changes HOW shown, never WHETHER"; `overhaul_runbook` RUNS the verification loop
(FAIL+iterate, never ship incomplete); and the parity checklist gained a standing gate **"Every source
image present in build"**. Image carry-over is a parity-floor obligation on creative, same as features.

**Known open items (not yet implemented — tracked here so they're not lost):**
- *Gap #3* — no pre-built motion/interaction components in the archetype (`src/` has no drawer /
  scroll-reveal / condensing-header scaffolding); the creative build authors them from scratch each
  time per `creative_clause`. A future archetype motion kit would make creative builds cheaper + consistent.
- *Gap #4* — no creative-specific iteration budget; creative uses the same verification-loop HARD CAP
  of 5 as standard.

## 5 · Troubleshooting workflow (incidents — diagnose THEN fix)
When the human reports something broken, the studio does NOT start editing — it materializes an
**incident** first (`02-intake/incidents/NNN-OPEN-<short>.md`, studio-level → `.claude/incidents/`,
from `templates/incident-template.md`). Filename-is-state (OPEN/BLOCKED/RESOLVED), mirroring edits +
decisions. Six binding sections: SYMPTOM (verbatim) → DIAGNOSTIC (reproduce FIRST, evidence) → ROOT
CAUSE (one falsifiable sentence) → FIX PLAN (smallest change; reimplementation allowed if the impl is
unsound) → VERIFICATION (reproduction must pass + the parity-checklist rows the fix could disturb) →
RESOLUTION (filled at close).

Rules: client-site fixes go THROUGH the edit convention (incident links its edit NNN; publish-always
applies); studio-system fixes commit directly with the SYSTEM.md update. One root cause per incident
(a second problem → a second incident, no scope creep). Missing fact/credential → `NNN-BLOCKED-…` +
decision card. OPEN→RESOLVED only after verification passes; RESOLVED is immutable. RECURRENCE: a
symptom matching a RESOLVED incident reopens as a NEW incident referencing the old, and the diagnostic
must explain why the previous fix didn't hold before any new fix lands.

**Dashboard:** every client row + the studio header carry a "Report a problem" box (`/api/incident`);
submitting writes the OPEN incident with the words as SYMPTOM and enqueues the headless diagnostic
(`claude -p "Diagnose incident …"`). Open incidents render as a count badge with the decisions card
treatment. The chat tier recognizes problem reports and routes them through this convention.

## 6 · Findings & reports (every report becomes a visible artifact)
A finding that exists only in scrollback doesn't exist. Every substantive report — assemble/build,
feature census, verification-loop checklist, Design QA audit, incident diagnostic/resolution,
correspondence audit, backend phase, scrape coverage — is written WHEN PRODUCED to
`02-intake/reports/<YYYY-MM-DD-HHMM>-<kind>.md` (studio → `.claude/reports/`). Append-only; corrections
are new reports referencing the old. Records that already exist as their own artifacts (edit
Resolutions, incident files, parity-checklist, coverage.md) are LINKED, never duplicated. Every
finding-emitting flow (advance jobs, full-build, incidents, verification loop, intake pack) ends with
the file write. **Dashboard:** the row Documents panel has a Reports section (newest first; kind +
timestamp + one-line summary; click to render; "new" dot since last opened) — `studio.py`
`list_reports()` / `/api/doc` serves `reports/`; studio reports surface in the header.

## Related systems (pointers)
- **Findings & reports** — §6 above; CLAUDE.md "Findings & reports".
- **Troubleshooting / incidents** — §5 above; CLAUDE.md "Troubleshooting workflow"; `incident-template.md`.
- **Decision surfaces / inbox** — judgment moments become dashboard cards (CLAUDE.md "Decision surfaces").
- **Action surface + full build** — §3 above; CLAUDE.md Command 10 (`studio.py`).
- **Concept boards** — §4 above; CLAUDE.md Command 9 (`concept_boards.py`).
- **Rehearsal mode + completeness pass** — build on studio test resources; rehearsal's first step is a
  completeness pass (entire catalog) (CLAUDE.md rehearsal section; BACKEND.md swap checklist).
- **Backend baseline + configurator** — `templates/ecommerce-catalog/BACKEND.md` + `backend-config.yaml`.
- **Publish-always** — every `03-site` change ends build + Publish preview + status refresh.
