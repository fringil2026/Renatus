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

## 1a · Marketplace-export intake (owner-authorized — an ALTERNATIVE catalog source)
For a shop that lives on a **marketplace** (Etsy / eBay) rather than its own crawlable site, the
catalog evidence comes from the **owner's own export**, not the scrape ladder. This is a parallel
source that feeds the EXACT same downstream flow (census → redesign plan → boards → build); it
stands in for §1 as the catalog's origin of truth.

**WHO it covers (the authorized model).** A seller's **OWN** shop, WITH that seller's authorization
— **mine OR a client's**. The mechanism is identical either way: an Etsy/eBay CSV listings export +
the owner's own product photos, imported as **DRAFT** product records. Client-shop migrations add
PROVENANCE capture (below); the import logic does not otherwise change.

**The mechanism.**
1. The owner runs the export from their OWN marketplace back-office (Etsy: Shop Manager → Settings →
   Options → Download Data → "Currently for sale listings"; eBay: Seller Hub → Listings → download
   active listings) — **or grants us access to run it.** We do **not** reach their marketplace
   account by scraping. The CSV + a photos folder land in `02-intake/assets/`.
2. **CSV → product-record mapping** (same record shape the scrape extractor emits → `catalog-draft.json`,
   one record per listing, each carrying `source_listing_id`/`source_sku` as its provenance key):

   | Record field | Etsy export column | eBay export column |
   |---|---|---|
   | `name` | `TITLE` | `Title` |
   | `sku` | `SKU` | `Custom label (SKU)` |
   | `listing_id` | `(listing URL / id)` | `Item number` |
   | `price` (DRAFT) | `PRICE` | `Start price` / `Buy It Now price` |
   | `currency` | `CURRENCY_CODE` | `Currency` |
   | `availability` (DRAFT) | `QUANTITY` | `Available quantity` |
   | `description` (DRAFT) | `DESCRIPTION` | `Description` |
   | `category`/`genus` | `(tags / section)` | `Category` |
   | `photo` | filenames in `IMAGE1..N` / matched in assets | photo URLs / matched in assets |

3. **Photo correspondence [HARD] — same rule as the scrape (GUIDELINES §4).** A listing's photo is
   matched from `02-intake/assets/` by its **SKU / listing-id / filename**, NEVER by array order or
   index. Text and photo stay together as they appeared on the SAME listing; pooling photos and
   re-attaching by order silently produces a right-name/wrong-photo catalog. A listing with no usable
   photo gets a clean type-led card, never a borrowed image. Run the same correspondence verifier +
   human QA sheet over the imported set.
4. **Everything imports DRAFT.** Prices, availability, descriptions are REAL but unconfirmed
   (owner facts pending sign-off) — labelled DRAFT, never silently trusted, never fabricated where
   absent. From here it is the ordinary pipeline: feature census → redesign plan → concept boards →
   build, run from the imported catalog.

**Provenance recorded (explicit, every import).** `status.json` carries
`catalog: { source: "etsy-export" | "ebay-export", owner: "self" | "client" }` (mirrored to
`brief.yaml` `catalogue.source`). For **client shops** (`owner: "client"`) the authorization is also
captured in the deliverables request: **§2.7 D-2.7.E1/E2** (client-provided export + ownership
authorization, BLOCKING) and **§2.4 D-2.4.9** (product-photo rights / source confirmation,
BLOCKING-at-launch). So a client-shop migration provably records that the CLIENT authorized and
supplied the export and owns/authorized the photos.

**BOUNDARY [HARD].** Import is for a **seller's OWN shop with that seller's authorization — mine OR a
client's**. It is **NEVER** a scraper for other sellers' listings, and we **never bot-scrape
eBay/Etsy** (against their terms). The only inputs are an **owner-authorized export** + the owner's
own photos; the client runs the export from their own Shop Manager / Seller Hub or grants access —
we do not access their marketplace account. (Restated in ECOMMERCE-GUIDELINES §3.)

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

### 3a · Edit creation — TWO reliable paths (both land valid, auto-numbered PENDING edits)
The dashboard creates client edits two ways, both converging on the `NNN-PENDING-<short>.md`
convention so **"Process edits" always picks them up** (the old upload bug: the file was saved under
its raw name → never matched `NNN-PENDING-*` → silently ignored):
- **Upload a `.md`** (`/api/upload`, dest=`edits`) → routed through `create_edit(slug, content,
  "upload")`: a pre-authored structured edit is normalised to `status: PENDING`; anything else is
  wrapped into the edit template. (dest=`specs` still saves the raw filename — specs need no numbering.)
- **Type into the row textarea** (`/api/add-edit`) → `create_edit(slug, text, "typed")` wraps the
  free text into the edit template's Requested-change section. The textarea carries `data-keep`, so
  typed text **survives the 4 s auto-refresh** (snapState/restoreState, per WS-INC-STUDIO-001).
`create_edit` auto-numbers via `_next_edit_n` (**highest existing NNN + 1**, robust to DONE/BLOCKED
gaps). Both paths give explicit success feedback (`✓ created NNN-PENDING-…`) — never a silent no-op.

**Processing them — the actuator (`/api/process-edits`).** Creating a PENDING edit does NOT process
it; that was the broken link (edits piled up PENDING, never built/deployed). A row with PENDING edits
shows a **"✎ Process N edits"** button (`pending_edits_count()` → payload `pending_edits`) that POSTs
`/api/process-edits` → `run_advance(slug, "Process edits for <slug>")` (CLAUDE.md Command 5): each
PENDING edit is implemented, the site builds, and the studio-owned publish net deploys — so the
preview URL refreshes. Edits stay visible (and the button stays) until they're DONE/BLOCKED.

### 3b · Stale-code defenses (kill the "dashboard is serving old code" class of bug)
The recurring root cause behind missing-buttons / inaccessible-creative-mode / reverting-radio /
broken-upload symptoms was a parallel or older `studio.py` serving stale code. Four defenses:
- **Visible version stamp** — at launch the server captures the short HEAD (`LAUNCH_HEAD`), the
  studio.py last-commit time, and a content fingerprint of the loaded studio.py (`LAUNCH_PY_SIG`).
  The footer/header renders `commit <hash> · <time>` (`version_info()` → `/api/clients` `version`).
- **Stale self-check** — every poll compares the on-disk studio.py fingerprint to `LAUNCH_PY_SIG`
  (NOT a bare HEAD compare — HEAD can move on an unrelated file without studio.py changing, which
  would false-alarm). If they differ, a **non-dismissable banner** fires: "running STALE code …
  restart." `version.stale` drives it.
- **Single-instance guard** — `single_instance_guard()` refuses to start a second studio.py on the
  port (names the incumbent PID); `STUDIO_TAKEOVER=1` / `--takeover` kills the incumbent and takes
  the port. No more two-servers-fighting.
- **One-command restart** — `./restart.sh` kills any instance on the port and relaunches on current
  code, then prints HEAD to verify against the footer stamp.
Convention (CLAUDE.md "studio.py change protocol"): a studio.py edit isn't done until the server is
restarted AND `version.head == HEAD` with `version.stale == false`.

### 3c · Multi-version builds (the boards-step design choice is MULTI-SELECT)
At the boards step the human may select **one OR MORE** design modes — **standard · image-led ·
creative** — each shown with a census-derived advisory (`version_advisory()`; image-led's tone comes
from `photo_coverage()`). Advisory only — the human is the gate (image-led on weak photography is
allowed; honest type-led fallback, never upscaled, §5.4).
- **One build + one URL per selected mode.** `run_version_builds(slug, modes)` drives them
  SEQUENTIALLY (one Claude task per client): version `i` builds via `version_build_runbook` into
  `version_site_dirname(i)` (`03-site`, then `03-site-v2`, `03-site-v3`…), then `publish_version(slug,
  i)` deploys it to `version_project(slug, i)` (`ws-<slug>`, then `ws-<slug>-v2`, …). `publish_version`
  generalises the studio-owned publish net across projects; `STUDIO_DEPLOY_DRYRUN=1` synthesises URLs
  without wrangler (plumbing tests).
- **status.json `versions[]`** — one entry per version `{idx, mode, label, project, site_dir, status,
  preview_url, published_at, chosen?}`. The base build (idx 0) also mirrors to the legacy
  `preview_url`/`preview_published_at` so single-version display + the run_advance publish net are
  unchanged. The row lists ALL version URLs (`versionLinks()`), each with copy + timestamp.
- **Isolation [HARD]** — each version is a complete, honest site (full parity floor + every image +
  every feature; only EXPRESSION differs); rebuilding one never touches another.
- **Single selection = today's behaviour** (one build, base URL). Multi only engages at 2+.
- **Promote / archive** — `/api/promote-version` records `chosen_version` (never deletes others);
  `/api/archive-version` moves a non-primary version's site dir to `archive/` (preview project left
  intact). Endpoints: `/api/build-versions`, `/api/promote-version`, `/api/archive-version`. Doctrine:
  ECOMMERCE-GUIDELINES §5.10.

### 3d · Build resilience (concurrency cap · transient-vs-real failures · restart-safe resume)
A mass build-failure taught three lessons; each has a lasting guard:
- **Concurrency cap (`CLAUDE_SEM`, `MAX_CLAUDE_JOBS`=2).** The trigger was a self-inflicted burst —
  ~15 clients × 2-version builds + overhauls fired at once, exhausting the Claude **monthly spend
  limit**, after which every headless job exited 1. A global semaphore now paces EVERY `claude -p`
  spawn (`run_advance` + `_claude_p_build`), so the studio can never blow the budget / overload the
  API in one wave. Raise via env when the budget is large.
- **Transient ≠ real failure.** `is_transient_failure()` matches budget/rate/overload signatures in a
  job's output tail. A job that dies on one is marked **`paused`** (version) or `status.paused` (advance/
  overhaul) — RESUMABLE — not `build-failed`/`*_failed` (terminal). Genuine non-transient failures stay
  terminal so they don't loop.
- **Restart-safe resume.** Multi-version orchestration is in-memory (a driver thread); a studio restart
  orphaned it (the seattle-orchids bug: image-led built-but-never-deployed, creative never started).
  `run_version_builds()` is now **resumable** (queue in `status.json`; skip published, re-deploy `built`/
  `publish-failed`, build the rest) and a **`version_reaper_loop()`** (every ~20 s, guarded by
  `claude_job_running()` so it never races a live build) auto-resumes orphaned/paused queues. The
  **"↻ Resume N paused/failed builds"** header button (`/api/resume-all`) resets terminal `build-failed`
  + `paused` versions to `queued`, re-fires budget-killed creative overhauls, and kicks the reaper —
  all paced by `CLAUDE_SEM`.

### 3e · Marketplace Import page (build from an owner-authorized export, not a scrape)
A dedicated dashboard route — **`GET /import`** (linked from Step 1 on the main dashboard) — for the
**marketplace-export intake path** (§1a): a shop on Etsy/eBay with no crawlable site of its own.
Rendered in the same dashboard app (its own `IMPORT_PAGE`, same styling), entirely upload-driven.
Depends on the resolved upload / state-preservation fix (§3a/§3b): the upload **forms are built once
and never re-rendered by the 4 s poll** — only a data-only `#live` zone (read from disk) refreshes — so
a staged file is never wiped, the same architectural guarantee as the main list's `interacting()` guard.

Flow + endpoints (all JSON, studio-authed):
- **New client from export** — `POST /api/import/new` `{name, platform: etsy|ebay, owner: self|client}`
  → `new_import_client()` scaffolds the standard `clients/<slug>/`, records provenance in
  `status.json` `catalog: {source: "<platform>-export", owner}` (stage `import-pending`), and
  auto-authors the BINDING design spec `02-intake/specs/marketplace-creative-build.md`
  (`marketplace_design_spec()` — creative mode + the "against blocky outlines" guardrail +
  category-true visual world + the full ecommerce backend at the final build; `spec-id`/`status:
  BINDING` so it unlocks the backend configurator).
- **Listings CSV** — `POST /api/import/upload-csv` `{slug, filename, content}` saves the export to
  `02-intake/marketplace-export.csv` and runs the importer
  (`.claude/skills/site-baseline/scripts/marketplace_import.py`): auto-detects Etsy vs eBay from the
  headers, maps columns → DRAFT product records (name, description, price, qty, tags/category, SKU,
  listing-id, variants) → `01-baseline/catalog-draft.json`.
- **Photos** — `POST /api/import/upload-photo` `{slug, filename, b64}` saves into `02-intake/assets/`
  (a `.zip` is unpacked, image members only); base64 so binaries ride the same JSON channel.
- **Preview** — `GET /api/import/state?slug=` re-runs the importer over CSV + current assets every call
  (so it is correct after refresh/restart and picks up photos uploaded after the CSV): N products,
  M with matched photos, products-without-photo and unmatched-photos flagged both directions, plus the
  owner=client provenance items. Photos pair by **SKU / listing-id / filename, never order/index**
  (the §1a / catalog-correspondence rule), one photo per product.
- **Build (creative prototype → edits → final backend)** — `POST /api/import/build` sets
  `design_mode: creative` and runs `import_build_runbook()` (via `run_advance`, so PUBLISH-ALWAYS
  fires): assemble the ecommerce-catalog archetype from the imported catalog (§1a) with the
  `import_creative_clause()` — full creative craft, the visual world derived from THIS shop's own
  products (NOT the orchid/greenhouse default), the **no-blocky-outlines** guardrail, parity floor +
  every imported photo, verification loop — then publish. That produces `03-site` + a preview and
  lands the client at `prototype`. From there it is an ordinary prototype-stage ecommerce client:
  **(2) edits** via the ledger (Command 5 / "Process edits"), then **(3) the final backend build** —
  Configure backend (BINDING config) → **Full build — from this prototype** (`full_build_action`
  from-prototype): Phases 2–4 = Supabase + Stripe + Resend + storefront integrations, on rehearsal
  TEST creds first (cutover refused while any `# REHEARSAL` credential is in use). The boards/
  multi-version gate stays available on the dashboard if a non-creative direction is wanted;
  `version_build_runbook` (idx 0) also assembles from the import when no `03-site` exists yet.
- **Provenance + boundary** — for `owner=client` the page surfaces D-2.7.E1/E2 + D-2.4.9 (recorded in
  the deliverables request when the pipeline runs); the boundary banner is always shown:
  owner-authorized own-shop export only, never a scraper for other sellers, never bot-scraping
  eBay/Etsy. The client row carries an `⤓ <source> · <owner>` badge. (Doctrine: §1a.)

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
| **CREATIVE / WOW build** (🎨) | **ONE button on the boards decision card** (the boards step) | `design_mode: creative` — **bypasses the A/B/C boards** and builds **from scratch** with full creative craft = **disciplined graphic richness + smooth interactivity + an original generated graphic system** (section scroll narrative, scroll-reveals, hover category tiles, slide-out drawers, condensing sticky header, ONE signature motion moment; code-drawn SVG botanical/tropical motifs for atmosphere — decoration-ONLY honesty boundary: never a stand-in for a real product, all art original) | **"Claude develops it"** (Claude reaches on its own) · **"Guide with text"** (paste a direction into `overhaul-brief.md`) — both build from scratch |

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

## 7 · Outreach pipeline (prospecting: diagnose → DRAFT — sending is a later, separate layer)

### 7a · The site-diagnostic engine (`.claude/skills/site-diagnostic/`)
One URL → a trustworthy, two-axis, industry-aware REBUILD VERDICT. Split of labor:
- **`scripts/diagnose.py`** (the measurable half): hardened-Playwright rendered capture (desktop
  1440 + mobile 390 full-page screenshots, rendered HTML), bounded polite mini-crawl (reuses
  `crawl.py`), PageSpeed Insights with 429-retry + local-load fallback, and every objective Axis-1
  check — responsive verdict (viewport meta AND @media count AND measured 390px overflow; a
  "not-responsive" claim requires the signals to AGREE), HTTPS posture, dated-tech tells (table
  layout, Flash, jQuery era, pre-HTML5 doctype, dated generator meta, stale ©, fixed widths —
  layout attributes only, gated on non-responsive), a11y basics (alt coverage, lang, labels, WCAG
  contrast sampling that EXCLUDES text-over-images as unscorable), mixed content (LOADED resources
  only, not links). Output: `diagnostic.json` where every finding carries its evidence string +
  confidence, plus a 0–100 measurable score with per-component evidence.
- **The model half (SKILL.md)**: industry classification FIRST → resolve the diagnostic standard
  (existing archetype guidelines → existing playbook → GENERATE a new `playbooks/<industry>.md`
  from `_TEMPLATE.md`, surfaced as a studio report for review — reused by all future prospects in
  that industry; the standard used is always recorded). Then the judged Axis-1 rubric (five 1–5
  dimensions on the screenshots, every score flagged OPINION with a visible-evidence reason),
  Axis-2 completeness gaps vs the standard (absence claims downgraded on thin crawls), verdict
  (strong-candidate / candidate / borderline / skip / unreachable / not-scorable), top-3
  marketable problems (measurable lead; taste phrased softly).
**Honesty rules are binding** (they feed emails to real owners): measurable claims verified-true,
judged claims flagged opinion, never fabricate a deficiency, a challenge-page capture is
NOT SCORABLE rather than judged. Artifacts: `outreach/prospects/<domain>/` (git-ignored).

### 7b · The Outreach tab (`/outreach` on the dashboard)
Upload-driven batch layer over the engine; **stops at DRAFTS — nothing is ever sent from here.**
- **Upload** a Grata CSV/XLSX → company/website columns auto-inferred from headers (social-profile
  URL columns excluded), the mapping is SHOWN before anything runs; rows dedup against the
  masterfile (the source of truth for "who we've touched") and within the sheet; dead/missing URLs
  are skipped gracefully. Each upload lays down `outreach/runs/<id>/run-state.json` — the resumable
  artifact (filename-state thinking: state lives in the artifact, not memory).
- **Runner**: sequential + paced (`OUTREACH_PACING_S`, default 20s between rows), one
  `claude -p` site-diagnostic per pending row under BG_SEM+CLAUDE_SEM (same budget pacing as
  builds), per-row timeout, Stop button (finishes the current row), Resume continues exactly where
  it stopped; a transient (budget/rate) failure PAUSES the run rather than failing rows. Each row
  job writes `outreach/prospects/<domain>/{report.md,result.json}`; the RUNNER is the single
  writer of the two output files (the row contract is `result.json`).
- **Two living output files** (downloadable from the tab): `outreach/masterfile.csv` — every
  company ever processed (domain, company, date, industry, standard, verdict, score, top
  problems, contact_status diagnosed/drafted — later: emailed) — and `outreach/drafted-emails.csv`
  — one row per rebuild candidate (top-3 problems + drafted subject/body), the human review
  surface. Append-only; dedup reads the masterfile.
- Every finished run writes a studio report (findings convention). Per-prospect reports render in
  the tab.
- **Email drafts** are personalized from THAT site's diagnosed problems (measurable lead, taste
  softened, no fabricated deficiencies, no spam patterns). **SENDING (not built) must add CAN-SPAM
  compliance: unsubscribe mechanism + the studio's physical mailing address + accurate
  From/subject — plus per-recipient suppression honoring the masterfile.** That belongs to the
  future send layer, never to drafting.

## Related systems (pointers)
- **Marketplace-export intake** — §1a above: owner-authorized Etsy/eBay export as an alternative
  catalog source (mine OR a client's own shop); never a scraper for other sellers (boundary in §1a +
  GUIDELINES §3). Provenance: `status.json` `catalog.{source,owner}`; client-shop deliverables
  D-2.7.E1/E2 + D-2.4.9.
- **Findings & reports** — §6 above; CLAUDE.md "Findings & reports".
- **Troubleshooting / incidents** — §5 above; CLAUDE.md "Troubleshooting workflow"; `incident-template.md`.
- **Decision surfaces / inbox** — judgment moments become dashboard cards (CLAUDE.md "Decision surfaces").
- **Action surface + full build** — §3 above; CLAUDE.md Command 10 (`studio.py`).
- **Concept boards** — §4 above; CLAUDE.md Command 9 (`concept_boards.py`).
- **Rehearsal mode + completeness pass** — build on studio test resources; rehearsal's first step is a
  completeness pass (entire catalog) (CLAUDE.md rehearsal section; BACKEND.md swap checklist).
- **Backend baseline + configurator** — `templates/ecommerce-catalog/BACKEND.md` + `backend-config.yaml`.
- **Publish-always** — every `03-site` change ends build + Publish preview + status refresh.
- **Studio-owned publish net** — a headless `claude -p` build (Creative/Overhaul, full-build, advance)
  cannot authorize the outbound `wrangler pages deploy`, so it must NOT be the thing responsible for
  publishing. `studio.py` `publish_preview(slug)` deploys `03-site/dist` from the operator's authed
  shell; `run_advance` calls it after any successful headless job that left a fresh `dist` (or a
  `publish_blocked` flag). On deploy failure it keeps the prior `preview_url`, sets `preview_stale`,
  and logs loudly (never a silent stale url). See incident WS-INC-STUDIO-002.
