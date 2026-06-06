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

**Block detection (rung 1):** HTTP 5xx/403 on the homepage OR the Cloudflare challenge marker
`/cdn-cgi/challenge-platform/` in any response → BLOCKED → escalate.

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
After the scrape, before any prototype, the human picks from THREE real designs, not documents.
`.claude/skills/site-baseline/scripts/concept_boards.py` reads `02-intake/concepts/concepts.json`
(per-board palette/fonts/signature/layout/products; `images:[]` ⇒ type-led, honest when photography
is weak) and emits: distinct static board HTML under `02-intake/concepts/site/concepts/<letter>/`
(noindex, no JS, "CONCEPT BOARD — not the final build" banner), desktop+390px Playwright screenshots
(`<letter>-<id>.png`), and the `boards.json` manifest. The boards deploy to the preview project at
`ws-<slug>.pages.dev/concepts/a|b|c/` (disposable — replaced at the first prototype publish; the PNGs
persist). The concept decision YAML carries `board_url` + `thumb` per option, so the dashboard
"Needs your call" card renders the screenshots as clickable thumbnails (served via
`/api/concept-thumb`) with the recommendation marked; picking one resolves it as before and drives
Assemble. A full-build-from-scratch generates + records the boards but auto-accepts the recommended
concept without waiting.

## Related systems (pointers)
- **Decision surfaces / inbox** — judgment moments become dashboard cards (CLAUDE.md "Decision surfaces").
- **Action surface + full build** — §3 above; CLAUDE.md Command 10 (`studio.py`).
- **Concept boards** — §4 above; CLAUDE.md Command 9 (`concept_boards.py`).
- **Rehearsal mode + completeness pass** — build on studio test resources; rehearsal's first step is a
  completeness pass (entire catalog) (CLAUDE.md rehearsal section; BACKEND.md swap checklist).
- **Backend baseline + configurator** — `templates/ecommerce-catalog/BACKEND.md` + `backend-config.yaml`.
- **Publish-always** — every `03-site` change ends build + Publish preview + status refresh.
