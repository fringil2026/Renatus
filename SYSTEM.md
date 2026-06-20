# SYSTEM.md — Web Studio internals
How the studio's resilience + quality systems work. Companion to CLAUDE.md (the operating contract)
and CONTEXT.md (background). Two core systems: the scrape ladder (real evidence even from bot-blocked
sites) and the parity verification loop (no prototype ships on belief).

---

## 1 · The scrape ladder (`.claude/skills/site-baseline/scripts/run_baseline.py`)
An escalating cascade, not a fixed method list — each rung runs only when those above captured
insufficient content. Politeness is law on every rung (identified/default UA, generous delays,
bounded retries); two failed unblock attempts ⇒ move DOWN the ladder, never an arms race.

| Rung | Tool | Role | Runs when |
|---|---|---|---|
| 1 | crawler (`crawl.py`, requests) | fast polite first pass | always |
| 2 | rendered browser (`render_capture.py`, Playwright/Chromium) | primary anti-bot weapon — real fingerprint, human-pace nav | always (if installed) |
| 3 | wget mirror (`mirror.sh`) | breadth archive + URL census | only when rungs 1–2 get content |
| 4 | Wayback (`archive_fetch.py`) | last-resort evidence when blocked | only when live rungs are blocked |
| 5 | human | decision card w/ owner-export note | only when all rungs insufficient |

- **Block detection (rung 1):** a REAL block = HTTP 4xx/5xx on the homepage, OR the Cloudflare marker
  `/cdn-cgi/challenge-platform/` WITH little real content. The challenge script ships inside ordinary
  200 pages, so its presence ALONE is not a block (WS-INC-SEATTLE-ORCHIDS-001 — once discarded a
  150-page live crawl for stale archive). Render-rung success counts captured screenshots
  (`*-desktop.png` / `render.json`), not `.html` files.
- **Missing tools never silently skip:** `wget`/Playwright availability is checked; if absent the rung
  is logged loudly (`‼ RUNG n FAILED`) with the install command and counts as a failure.
- **Mirror caps** are bounded but env-overridable for the rehearsal completeness pass:
  `MIRROR_MAX_FILES` / `MIRROR_MAX_SECONDS` (defaults 300 / 300s) — logged, never unbounded.
- **Evidence provenance:** `00-source/evidence-source.txt` records `LIVE` / `ARCHIVE` / `NONE`.
  ARCHIVE content (Wayback, labelled `ARCHIVE-<snapshot-date>`) is STALE — usable for tokens, copy
  drafts, the census; NEVER current price/stock truth. Census + tokens-draft label their source.
- **Reporting:** `01-baseline/coverage.md` records every rung attempted, its result, and which rungs
  the final baseline rests on.
- **Platform catalog enumeration.** Some platforms hide the catalog from category-link following.
  Volusion (WS-INC-SEATTLE-ORCHIDS-002) exposes all products only in `/sitemap.xml` as
  `/<Name>-p/<sku>.htm`; the generic crawler caps on `-s/` category pages and gets zero products. When
  evidence fingerprints Volusion, the ladder runs `scrape_volusion.py` (sitemap → product URLs →
  polite static parse: `og:title`, `og:image`, "Our Price $X" as DRAFT) → `01-baseline/catalog-draft.json`.
  This is URL-discovery + platform-parse, never an unblocking trick (no proxy/CAPTCHA/token evasion).
- **Platform image patterns.** Miva (WS-INC-ORCHIDS-BY-HAUSERMANN-001) lazy-loads the photo via
  `<img id="js-main-image" data-image="graphics/00000001/<GUID>.jpeg">` — static `src` is a blank.gif,
  so a generic `<img src>` extractor gets nothing. `extract_miva_images.py` reads each product's own
  `source_page`, pulls `data-image`, downloads the real photo, pairs it to that product
  (correspondence-safe). Diagnose the actual image markup (src vs data-src/data-image vs srcset vs
  background-image vs CDN) before fixing; honest low-res findings become a D-2.7.4 photography ask,
  never invented/upscaled images.

---

## 1a · Marketplace-export intake (owner-authorized — alternative catalog source)
For a shop that lives on a marketplace (Etsy/eBay) with no crawlable site, the catalog evidence comes
from the owner's own export, not the scrape ladder. It feeds the EXACT same downstream flow (census →
redesign plan → boards → build), standing in for §1 as the catalog's origin of truth.

- **WHO it covers:** a seller's OWN shop WITH that seller's authorization — mine OR a client's. Same
  mechanism either way: an Etsy/eBay CSV listings export + the owner's own photos, imported as DRAFT
  records. Client-shop migrations add provenance capture; the import logic is otherwise unchanged.
- **The mechanism.**
  1. The owner runs the export from their OWN back-office (Etsy: Shop Manager → Settings → Options →
     Download Data → "Currently for sale listings"; eBay: Seller Hub → Listings → download active),
     or grants us access to run it. We never reach their marketplace account by scraping. CSV + photos
     folder land in `02-intake/assets/`.
  2. **CSV → product-record mapping** (same record shape the scrape extractor emits →
     `catalog-draft.json`, one record/listing, each carrying `source_listing_id`/`source_sku`):

     | Record field | Etsy column | eBay column |
     |---|---|---|
     | `name` | `TITLE` | `Title` |
     | `sku` | `SKU` | `Custom label (SKU)` |
     | `listing_id` | listing URL/id | `Item number` |
     | `price` (DRAFT) | `PRICE` | `Start price` / `Buy It Now price` |
     | `currency` | `CURRENCY_CODE` | `Currency` |
     | `availability` (DRAFT) | `QUANTITY` | `Available quantity` |
     | `description` (DRAFT) | `DESCRIPTION` | `Description` |
     | `category`/`genus` | tags / section | `Category` |
     | `photo` | `IMAGE1..N` / matched in assets | photo URLs / matched in assets |

  3. **Photo correspondence [HARD]** (same rule as the scrape, GUIDELINES §4): a listing's photo is
     matched from `02-intake/assets/` by SKU / listing-id / filename, NEVER by order/index. Text and
     photo stay together as on the SAME listing. A listing with no usable photo gets a clean type-led
     card, never a borrowed image. Run the same correspondence verifier + human QA sheet.
  4. **Everything imports DRAFT** — prices/availability/descriptions are REAL but unconfirmed
     (labelled DRAFT, never silently trusted, never fabricated where absent). From here it's the
     ordinary pipeline.
- **Provenance recorded (every import):** `status.json` `catalog: { source: "etsy-export" |
  "ebay-export", owner: "self" | "client" }` (mirrored to brief.yaml `catalogue.source`). For client
  shops (`owner: "client"`) authorization is also captured in the deliverables request: §2.7
  D-2.7.E1/E2 (client export + ownership authorization, BLOCKING) and §2.4 D-2.4.9 (product-photo
  rights, BLOCKING-at-launch).
- **BOUNDARY [HARD].** Import is for a seller's OWN shop with that seller's authorization (mine OR a
  client's). NEVER a scraper for other sellers' listings; we never bot-scrape eBay/Etsy. The only
  inputs are an owner-authorized export + the owner's own photos. (Restated in GUIDELINES §3.)

---

## 2 · The parity verification loop (CLAUDE.md "Verification loop — binding")
The feature census is a binding CHECKLIST; no prototype returns until every line is verified or
honestly blocked.
- **The artifact** (`feature_census.py` → `01-baseline/parity-checklist.md`): one row per feature with
  a checkbox, its census classification, and a CONCRETE VERIFICATION METHOD a later session can
  execute mechanically against `dist/` (e.g. "dist/shop/ has a search input that filters cards"). Plus
  standing gate rows every build: build passes · zero banned design patterns · noindex present ·
  mobile ~390px structure · correspondence verifier 0 mismatches · brand moment named+placed. A row
  without an executable verification method is invalid.
- **The loop** (after assemble; also after "Process edits" and at "Finish"; the rehearsal chain runs
  it at assemble AND after Phase 4 with backend rows): execute each row's method against the BUILT
  OUTPUT, never intentions or remembered source. For each unmet row: fix → `npm run build` →
  re-verify that row + any row the fix could disturb. Iterate to `[x]` verified-with-evidence or `[B]`
  BLOCKED (naming the missing deliverable ID). HARD CAP 5 iterations; at the cap STOP, report
  survivors as honest failures + open a decision card. The completed checklist (per-row evidence +
  iteration count) is pasted into the build report and committed. Publish-always runs only after the
  loop exits.

---

## 3 · Dashboard action surface + full build (`studio.py`)
No stage's only path is typing in a terminal. The `NEXT` map holds STATUS DESCRIPTIONS only (never
`claude → "…"` commands); every actionable stage carries a real button, with the `⧉` copy-command
link as the terminal escape hatch.

| Stage | Control |
|---|---|
| queued / created / scraping | transient auto states — descriptive, no action |
| error | Rerun |
| baseline-ready | Assemble prototype + Full build — from scratch (boards in the row) |
| prototype / awaiting-owner | paste box (owner answers) · Configure backend · Full build — from this prototype · Phase-2 Advance once a BINDING config exists |
| answers-received | Finish + Full build — from this prototype |
| final | Run cutover prechecks + Full build — from this prototype |
| cutover-checked | Archive |

**Full build** (Command 10) — one chain, two stage-gated mutually-exclusive variants (`from-scratch`,
`from-prototype`). studio.py owns the surface: stage gate (`full_build_action`), slug-typed confirm +
test-credential precondition (`/api/full-build`, `test_creds_ready` — disabled until `secrets/.env`
carries `# REHEARSAL` creds), the step artifact `02-intake/full-build-progress.json`
(`init_full_build`), the live row step-log, and resume (re-running keeps the artifact; `claude -p`
skips `done` steps via `full_build_runbook`). TEST banners + cutover-refusal unchanged.

### 3a · Edit creation — TWO reliable paths (both land valid auto-numbered PENDING edits)
Both converge on `NNN-PENDING-<short>.md` so "Process edits" always picks them up (old bug: file
saved under raw name → never matched `NNN-PENDING-*` → silently ignored):
- **Upload a `.md`** (`/api/upload`, dest=`edits`) → `create_edit(slug, content, "upload")`: a
  pre-authored structured edit is normalised to `status: PENDING`; anything else is wrapped in the
  template. (dest=`specs` still saves the raw filename — specs need no numbering.)
- **Type into the row textarea** (`/api/add-edit`) → `create_edit(slug, text, "typed")` wraps free
  text into the template's Requested-change section. The textarea carries `data-keep` so typed text
  survives the 4s refresh (snapState/restoreState, WS-INC-STUDIO-001).
`create_edit` auto-numbers via `_next_edit_n` (highest existing NNN + 1, robust to DONE/BLOCKED gaps).
Both give explicit success feedback (`✓ created NNN-PENDING-…`), never a silent no-op.

**Processing — the actuator (`/api/process-edits`).** Creating a PENDING edit does NOT process it
(the old broken link — edits piled up, never built/deployed). A row with PENDING edits shows
**"✎ Process N edits"** (`pending_edits_count()` → payload `pending_edits`) → POST `/api/process-edits`
→ `run_advance(slug, "Process edits for <slug>")` (Command 5): each edit implemented, site builds,
the studio publish net deploys. Edits stay visible until DONE/BLOCKED.

### 3b · Stale-code defenses (kill "dashboard serving old code")
Root cause of missing-buttons / inaccessible-creative / reverting-radio / broken-upload: a parallel or
older studio.py serving stale code. Four defenses:
- **Version stamp** — at launch the server captures short HEAD (`LAUNCH_HEAD`), studio.py last-commit
  time, and a content fingerprint (`LAUNCH_PY_SIG`). Footer renders `commit <hash> · <time>`
  (`version_info()` → `/api/clients` `version`).
- **Stale self-check** — every poll compares on-disk studio.py fingerprint to `LAUNCH_PY_SIG` (NOT a
  bare HEAD compare — HEAD can move on an unrelated file). If different, a non-dismissable banner
  fires; `version.stale` drives it.
- **Single-instance guard** — `single_instance_guard()` refuses a second studio.py on the port (names
  the incumbent PID); `STUDIO_TAKEOVER=1` / `--takeover` kills it and takes the port.
- **One-command restart** — `./restart.sh` kills any instance on the port, relaunches on current code,
  prints HEAD to verify against the footer stamp.
Convention: a studio.py edit isn't done until restarted AND `version.head == HEAD` with
`version.stale == false`.

### 3c · Multi-version builds (the boards-step design choice is MULTI-SELECT)
At the boards step the human may select one OR MORE modes — standard · image-led · creative — each
with a census-derived advisory (`version_advisory()`; image-led's tone from `photo_coverage()`).
Advisory only — the human is the gate (image-led on weak photography allowed; honest type-led
fallback, never upscaled, §5.4).
- **One build + one URL per mode.** `run_version_builds(slug, modes)` drives them SEQUENTIALLY: version
  `i` builds via `version_build_runbook` into `version_site_dirname(i)` (`03-site`, `03-site-v2`, …),
  then `publish_version(slug, i)` deploys to `version_project(slug, i)` (`ws-<slug>`, `ws-<slug>-v2`, …).
  `STUDIO_DEPLOY_DRYRUN=1` synthesises URLs without wrangler.
- **status.json `versions[]`** — one entry/version `{idx, mode, label, project, site_dir, status,
  preview_url, published_at, chosen?}`. Base build (idx 0) also mirrors to legacy
  `preview_url`/`preview_published_at`. The row lists ALL version URLs (`versionLinks()`).
- **Isolation [HARD]** — each version is a complete honest site (full parity floor + every image +
  feature; only EXPRESSION differs); rebuilding one never touches another.
- **Single selection = today's behaviour** (one build, base URL). Multi engages only at 2+.
- **Promote/archive** — `/api/promote-version` records `chosen_version` (never deletes others);
  `/api/archive-version` moves a non-primary version's site dir to `archive/` (preview project intact).
  Endpoints: `/api/build-versions`, `/api/promote-version`, `/api/archive-version`. Doctrine: GUIDELINES §5.10.

### 3d · Build resilience (concurrency cap · transient-vs-real failures · restart-safe resume)
- **Concurrency cap (`CLAUDE_SEM`, `MAX_CLAUDE_JOBS`=2).** Trigger: ~15 clients × 2-version builds +
  overhauls fired at once, exhausting the Claude monthly spend limit → every headless job exited 1. A
  global semaphore paces EVERY `claude -p` spawn (`run_advance` + `_claude_p_build`). Raise via env
  when the budget is large.
- **Transient ≠ real failure.** `is_transient_failure()` matches budget/rate/overload signatures in a
  job's output tail. A job dying on one is marked `paused` (version) / `status.paused`
  (advance/overhaul) — RESUMABLE — not terminal (`build-failed`/`*_failed`). Genuine failures stay
  terminal.
- **Restart-safe resume.** Multi-version orchestration was in-memory; a restart orphaned it
  (seattle-orchids: image-led built-but-never-deployed, creative never started). `run_version_builds()`
  is resumable (queue in status.json; skip published, re-deploy `built`/`publish-failed`, build the
  rest); `version_reaper_loop()` (every ~20s, guarded by `claude_job_running()`) auto-resumes
  orphaned/paused queues. Header button **"↻ Resume N paused/failed builds"** (`/api/resume-all`)
  resets terminal `build-failed` + `paused` to `queued`, re-fires budget-killed overhauls, kicks the
  reaper — all paced by `CLAUDE_SEM`.

### 3e · Marketplace Import page (build from an owner-authorized export, not a scrape)
Route **`GET /import`** (linked from Step 1) for the §1a path: an Etsy/eBay shop with no crawlable
site. Same dashboard app (`IMPORT_PAGE`), upload-driven. Depends on the upload/state-preservation fix
(§3a/§3b): the upload forms are built once, never re-rendered by the 4s poll — only a data-only
`#live` zone refreshes — so a staged file is never wiped.

Flow + endpoints (JSON, studio-authed):
- **New client** — `POST /api/import/new` `{name, platform: etsy|ebay, owner: self|client}` →
  `new_import_client()` scaffolds `clients/<slug>/`, records provenance `catalog: {source:
  "<platform>-export", owner}` (stage `import-pending`), auto-authors the BINDING spec
  `02-intake/specs/marketplace-creative-build.md` (`marketplace_design_spec()` — creative mode +
  "against blocky outlines" guardrail + category-true visual world + full ecommerce backend at final
  build; `status: BINDING` so it unlocks the backend configurator).
- **Listings CSV** — `POST /api/import/upload-csv` `{slug, filename, content}` saves to
  `02-intake/marketplace-export.csv` and runs `marketplace_import.py` (auto-detects Etsy vs eBay from
  headers, maps columns → DRAFT records → `01-baseline/catalog-draft.json`).
- **Photos** — `POST /api/import/upload-photo` `{slug, filename, b64}` → `02-intake/assets/` (a `.zip`
  is unpacked, image members only).
- **Preview** — `GET /api/import/state?slug=` re-runs the importer over CSV + current assets every
  call (correct after refresh/restart, picks up late photos): N products, M with matched photos,
  products-without-photo and unmatched-photos flagged both ways, plus owner=client provenance items.
  Photos pair by SKU / listing-id / filename, never order/index.
- **Build** — `POST /api/import/build` sets `design_mode: creative` and runs `import_build_runbook()`
  (via `run_advance`, so PUBLISH-ALWAYS fires): assemble the ecommerce-catalog archetype from the
  imported catalog with `import_creative_clause()` (full creative craft, visual world from THIS shop's
  products NOT the orchid default, no-blocky-outlines guardrail, parity floor + every imported photo,
  verification loop) → publish → lands at `prototype`. From there it's an ordinary prototype-stage
  ecommerce client: edits via the ledger (Command 5), then the final backend build (Configure backend
  → Full build — from this prototype: Phases 2–4 = Supabase + Stripe + Resend + storefront on
  rehearsal TEST creds). `version_build_runbook` (idx 0) also assembles from the import when no
  `03-site` exists.
- **Provenance + boundary** — for `owner=client` the page surfaces D-2.7.E1/E2 + D-2.4.9; the boundary
  banner is always shown (owner-authorized own-shop export only). The row carries an `⤓ <source> ·
  <owner>` badge.

## 4 · Concept boards (the visual concept decision)
After the scrape, before any prototype, the human picks from real designs spanning a creativity
spectrum. `concept_boards.py` reads `02-intake/concepts/concepts.json` and emits distinct static
board HTML under `02-intake/concepts/site/concepts/<letter>/` (noindex, no JS, "CONCEPT BOARD" banner),
desktop+390px Playwright screenshots, and `boards.json`. Boards deploy to
`ws-<slug>.pages.dev/concepts/a|b|c/` (disposable — replaced at first prototype publish; PNGs persist).

- **Mandatory divergence.** Base boards: A·classic (safe), B·confident (recommendation), C·bold
  (pushes hard). Each `tier` maps to a structurally distinct archetype (`archetype_css`: classic =
  centered/symmetric + CTA; editorial = asymmetric + signature legend + featured-card grid; dramatic =
  oversized type + staggered grid; experimental = numbered-index nav + viewport hero + broken collage).
  `divergence_check()` is BINDING: base boards must differ in layout archetype AND `type_attitude` AND
  `structural_idea`, exactly one recommended — else the generator prints FAIL and exits non-zero.
- **The wow lever — "🔥 Push further".** Fourth control (only after 3 boards exist; generative, no slug
  confirm) → `/api/push-further` → headless job producing Board D (experimental, beyond bold; still
  honors hard rules). D publishes at `/concepts/d/`, screenshots, joins as a `tag: experimental`
  option. Fires once more for Board E; capped at two escalations (a–e) — beyond that, a decision note.
  The concept decision YAML carries `tier`/`board_url`/`thumb` per option; the "Needs your call" card
  renders screenshots as clickable thumbnails (via `/api/concept-thumb`). Full-build-from-scratch
  auto-accepts Board B.

**Creativity model (ONE hierarchy, no overlaps).** Creative is ONE button, ONE entry point:
| Control | When | What it does | Input modes |
|---|---|---|---|
| STANDARD | always (default) | clean, purpose-fit; full Design QA Gate + brand moment. Advance/Full build are standard BY DESIGN — they ignore `design_mode` | — |
| PUSH FURTHER (🔥) | boards card, after A/B/C | generates ONE bolder board (D, then E; cap 2) | — |
| CREATIVE / WOW (🎨) | ONE button on the boards decision card | `design_mode: creative` — bypasses A/B/C, builds from scratch with full creative craft (disciplined graphic richness + smooth interactivity + an original generated graphic system: section scroll narrative, scroll-reveals, hover category tiles, slide-out drawers, condensing sticky header, ONE signature motion moment; code-drawn SVG motifs — decoration-ONLY, never a stand-in for a real product, all art original) | "Claude develops it" · "Guide with text" (paste into `overhaul-brief.md`) — both build from scratch |

Code (ONE clean path, no silent downgrade): the Creative/Wow button (`renderNeeds` → `openOverhaul` →
`#ovmodal`) hits `/api/overhaul` only; sets `design_mode: creative` (+ `overhaul_input`) via
`set_design_mode`, closes any open A/B/C board decision (bypass), enqueues `overhaul_runbook()` which
ALWAYS injects `creative_clause()`. Brief mode creates/awaits `02-intake/overhaul-brief.md` (first
click arms, second builds). Advance + Full build are standard by design and do not read `design_mode`.
Three HARD invariants every tier: parity floor untouched · all Hard rules untouched · expression-only
(layout/type/colour/motion/interactivity/graphics, never facts/features/guardrails); verification loop
still runs.

**Images on the creative path (WS-INC-STUDIO).** Because creative reimagines components from scratch,
dropped images were a real failure mode. Now: `creative_clause` orders "carry over EVERY source image
(re-import the records); expression changes HOW shown, never WHETHER"; `overhaul_runbook` RUNS the
verification loop; the parity checklist gained a standing gate "Every source image present in build".
Image carry-over is a parity-floor obligation on creative, same as features.

**Known open items (tracked so they're not lost):**
- *Gap #3* — no pre-built motion/interaction components in the archetype; the creative build authors
  them from scratch each time. A future archetype motion kit would make creative builds cheaper.
- *Gap #4* — no creative-specific iteration budget; creative uses the same HARD CAP of 5.

## 5 · Troubleshooting workflow (incidents — diagnose THEN fix)
When the human reports something broken, the studio materializes an incident FIRST
(`02-intake/incidents/NNN-OPEN-<short>.md`, studio-level → `.claude/incidents/`, from
`templates/incident-template.md`). Filename-is-state (OPEN/BLOCKED/RESOLVED). Six binding sections:
SYMPTOM (verbatim) → DIAGNOSTIC (reproduce FIRST, evidence) → ROOT CAUSE (one falsifiable sentence) →
FIX PLAN (smallest change; reimplementation allowed if the impl is unsound) → VERIFICATION
(reproduction must pass + the parity-checklist rows the fix could disturb) → RESOLUTION (at close).
Rules: client-site fixes go THROUGH the edit convention (incident links its edit NNN; publish-always
applies); studio-system fixes commit directly with the SYSTEM.md update. One root cause per incident.
Missing fact/credential → `NNN-BLOCKED-…` + decision card. OPEN→RESOLVED only after verification
passes; RESOLVED is immutable. RECURRENCE: a symptom matching a RESOLVED incident reopens as a NEW
incident referencing the old, and the diagnostic must explain why the previous fix didn't hold.
Dashboard: every row + the header carry a "Report a problem" box (`/api/incident`) that writes the
OPEN incident (words as SYMPTOM) and enqueues the headless diagnostic. Open incidents render as a
count badge.

## 6 · Findings & reports (every report becomes a visible artifact)
Every substantive report — assemble/build, feature census, verification-loop checklist, Design QA
audit, incident diagnostic/resolution, correspondence audit, backend phase, scrape coverage — is
written WHEN PRODUCED to `02-intake/reports/<YYYY-MM-DD-HHMM>-<kind>.md` (studio → `.claude/reports/`).
Append-only; corrections are new reports referencing the old. Records that already exist as their own
artifacts (edit Resolutions, incident files, parity-checklist, coverage.md) are LINKED, never
duplicated. Every finding-emitting flow (advance jobs, full-build, incidents, verification loop,
intake pack) ends with the file write. Dashboard: the row Documents panel has a Reports section
(newest first; kind + timestamp + one-line summary; "new" dot since last opened) — `list_reports()` /
`/api/doc` serves `reports/`; studio reports surface in the header.

## 7 · Outreach pipeline (prospecting: diagnose → DRAFT — sending is a later, separate layer)

### 7a · The site-diagnostic engine (`.claude/skills/site-diagnostic/`)
One URL → a trustworthy, two-axis, industry-aware REBUILD VERDICT.
- **`scripts/diagnose.py`** (the measurable half): hardened-Playwright rendered capture (desktop 1440
  + mobile 390 full-page screenshots, rendered HTML), bounded polite mini-crawl (reuses `crawl.py`),
  PageSpeed Insights with 429-retry + local-load fallback, and every objective Axis-1 check —
  responsive verdict (viewport meta AND @media count AND measured 390px overflow must AGREE for a
  "not-responsive" claim), HTTPS posture, dated-tech tells (table layout, Flash, jQuery era,
  pre-HTML5 doctype, dated generator meta, stale ©, fixed widths — layout attributes only, gated on
  non-responsive), a11y basics (alt coverage, lang, labels, WCAG contrast sampling that EXCLUDES
  text-over-images), mixed content (LOADED resources only). Output: `diagnostic.json` where every
  finding carries its evidence string + confidence, plus a 0–100 measurable score.
- **The model half (SKILL.md):** industry classification FIRST → resolve the diagnostic standard
  (existing archetype guidelines → existing playbook → GENERATE a new `playbooks/<industry>.md` from
  `_TEMPLATE.md`, surfaced as a studio report; reused by all future prospects in that industry; the
  standard used is always recorded). Then the judged Axis-1 rubric (five 1–5 dimensions on the
  screenshots, each flagged OPINION with a visible-evidence reason), Axis-2 completeness gaps vs the
  standard (absence claims downgraded on thin crawls), verdict (strong-candidate / candidate /
  borderline / skip / unreachable / not-scorable), top-3 marketable problems.
- **Honesty rules are binding** (they feed emails to real owners): measurable claims verified-true,
  judged claims flagged opinion, never fabricate a deficiency, a challenge-page capture is NOT SCORABLE
  rather than judged. Artifacts: `outreach/prospects/<domain>/` (git-ignored).

### 7b · The Outreach tab (`/outreach`)
Upload-driven batch layer over the engine; stops at DRAFTS — nothing is ever sent from here.
- **Upload** a Grata CSV/XLSX → company/website columns auto-inferred (social-profile URLs excluded),
  mapping SHOWN before running; rows dedup against the masterfile and within the sheet; dead/missing
  URLs skipped gracefully. Each upload lays down `outreach/runs/<id>/run-state.json` (resumable).
- **Runner:** sequential + paced (`OUTREACH_PACING_S`, default 20s), one `claude -p` site-diagnostic
  per pending row under BG_SEM+CLAUDE_SEM, per-row timeout, Stop (finishes current row), Resume
  continues exactly where it stopped; a transient (budget/rate) failure PAUSES the run. Each row job
  writes `outreach/prospects/<domain>/{report.md,result.json}`; the RUNNER is the single writer (row
  contract is `result.json`).
- **Two living output files** (downloadable): `outreach/masterfile.csv` — every company ever processed
  (domain, company, date, industry, standard, verdict, score, top problems, contact_status) — and
  `outreach/drafted-emails.csv` — one row per rebuild candidate (top-3 problems + drafted
  subject/body), the human review surface. Append-only; dedup reads the masterfile.
- Every finished run writes a studio report. Per-prospect reports render in the tab.
- **Email drafts** are personalized from THAT site's diagnosed problems (measurable lead, taste
  softened, no fabricated deficiencies, no spam patterns). SENDING (not built) must add CAN-SPAM
  compliance: unsubscribe + the studio's physical mailing address + accurate From/subject + per-
  recipient suppression honoring the masterfile. That belongs to the future send layer, never drafting.

## Related systems (pointers)
- **Studio-owned publish net** — a headless `claude -p` build cannot authorize the outbound `wrangler
  pages deploy`, so it must NOT be responsible for publishing. studio.py `publish_preview(slug)`
  deploys `03-site/dist` from the operator's authed shell; `run_advance` calls it after any successful
  headless job that left a fresh `dist` (or a `publish_blocked` flag). On deploy failure it keeps the
  prior `preview_url`, sets `preview_stale`, logs loudly. See WS-INC-STUDIO-002.
- **Backend baseline + configurator** — `templates/ecommerce-catalog/BACKEND.md` + `backend-config.yaml`.
- **Rehearsal mode + completeness pass** — CLAUDE.md rehearsal section; BACKEND.md swap checklist.
