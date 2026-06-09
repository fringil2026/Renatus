# CLAUDE.md — Web Studio Orchestrator
This folder is a multi-client website-rebuild studio. The human provides exactly two
inputs per client (a domain, then the owner's questionnaire answers). Everything else
is automated by the scripts in .claude/skills/ and by you.

**Deeper background** (architecture, design decisions, glossary, external deliverables):
read CONTEXT.md when needed — new sessions, unfamiliar references, or structural changes.

## Client folder contract (never deviate)
clients/<slug>/
  00-source/    raw scrapes — read-only evidence, never edit
  01-baseline/  extracted facts & drafts produced by the site-baseline skill
  02-intake/    human-provided truth: brief.yaml, owner-answers.txt, assets/, redirect-map.csv
  03-site/      the Astro project for this client (copied from templates/, then customized)
  04-cutover/   runbook, snapshots, check reports
  status.json   {stage, log[]} — update stage after every pipeline step

Stages: queued → scraping → baseline-ready → prototype → awaiting-owner
        → answers-received → final → cutover-checked → (archived)
Multiple clients run concurrently; clients/ holds only ACTIVE work. Finished projects
live in archive/<slug>-<timestamp>/ — read-only history, one folder per completed build.

## Command 1 — "Assemble prototype for <slug>"
Trigger: status.stage == baseline-ready (dashboard tells the human when).
0. Record the chosen design concept — the option the human picked on the "Choose the design concept"
   decision (opened by the intake pack). Build to THAT concept; if no decision is resolved yet, stop
   and surface it (don't guess the concept).
1. Read 01-baseline/ in full (inventory, drafts, audits, coverage, feature-census) and the intake
   pack (`02-intake/redesign-plan.md`).
   PARITY FLOOR: the prototype MUST carry every feature the census marks CARRY-OVER; STUB+FLAG
   features get a visible honest stub. New/better features come ON TOP of parity, never INSTEAD
   of it — dropping a CARRY-OVER feature is a build failure unless the census marked it OBSOLETE.
2. Copy the matching archetype from templates/ into 03-site/ (`cp -R`, never build in templates/).
3. Apply 01-baseline/tokens-draft.json to the @theme block; mirror to 03-site/tokens.json.
4. Map content-draft.md into the data slots; everything is marked DRAFT (it is scraped, unverified).
5. Seed 02-intake/brief.yaml with every fact the baseline established (domain, detected
   GA4/CMS from tech-fingerprint.md) — leave unknown fields blank, never guessed.
6. Seed 02-intake/redirect-map.csv from url-inventory.csv (old URL column filled, new column proposed).
7. `npm install && npm run build` in 03-site/ to verify; fix failures.
8. Set stage=prototype, then awaiting-owner. Report: what was applied, what is DRAFT, what is blank.
9. UPDATE `02-intake/deliverables-request.md` (CREATED earlier by "Prepare intake pack") with
   build-time discoveries — e.g. integrations confirmed in code, image-resolution gaps found,
   forms wired. Same filtering/specializing rules; never silently drop rows. (Generation moved to
   the intake pack so the human gets the deliverables list the moment scraping finishes, not only
   at build.)
10. Generate `01-baseline/block-purpose-map.md` — the audit trail for Purpose-first
    reconstruction (above). A table: source block (page + brief identifier) → purpose
    designation → target component (existing or new) → improvement made. It proves every block
    of the original was UNDERSTOOD, not transcribed. (Refreshed at "Finish" too.)
11. Generate `02-intake/production-roadmap.md` — a CLIENT-FACING, plain-language description of
    everything the complete product includes that the prototype doesn't yet do. Rules:
    - SOURCES, merged: the binding spec's phased features (checkout, owner admin, back-in-stock
      email…); the feature census STUB+FLAG list (EVERY stub in the prototype MUST appear here,
      honestly labelled — "the notify-me button you see is a preview; it goes live in the complete
      build"); and the playbook's Tier 2/3 features marked clearly as "optional later additions,"
      not promises.
    - Each entry: feature name → one sentence on what it does FOR THE CLIENT'S BUSINESS (no
      jargon, no phase numbers, no stack names like Supabase) → one line on what unblocks it,
      cross-referenced to the deliverables request ("available once we have your Stripe account —
      item D-2.7.1").
    - Two sections: "Included in your complete site" and "Optional additions we'd recommend down
      the road." Tone: confident, concrete, honest — sets client expectations, so nothing
      speculative is stated as certain.
    - Living, like the deliverables file: as facts arrive and features go live, entries move to a
      short "Now live" list at the top; rows never silently vanish.

## Command 2 — "Finish <slug>"
Trigger: 02-intake/owner-answers.txt exists (stage answers-received).
Use the apply-intake skill. Summary: parse the answers (statuses: answered / UNSURE / DELEGATED /
SKIPPED), reconcile into brief.yaml, resolve UNSURE items marked permission_to_investigate=YES via
technical lookups, replace DRAFT content with verified facts, finalize redirect-map and emit edge
config, rebuild, set stage=final. Produce 04-cutover/launch-runbook.md and a FOR-REVIEW list.

## Command 3 — "Run cutover prechecks for <slug>"
Use the cutover skill and its scripts (launch_check.py, redirect_check.py, zone_diff.py).
Write reports into 04-cutover/. Set stage=cutover-checked only if all checks pass.

## Command 4 — "Archive <slug>"
The human normally archives via the dashboard button; if asked: verify stage is final or
cutover-checked (warn otherwise), then move clients/<slug>/ to archive/<slug>-<YYYYmmdd-HHMMSS>/.
Never delete client folders; archive is the only removal path.

## Command 5 — "Process edits for <slug>"
Every revision request to a built site lives as a file:
`clients/<slug>/02-intake/edits/NNN-PENDING-<short-name>.md`, authored from
`templates/edit-template.md`. The filename IS the state — `PENDING` / `DONE` / `BLOCKED`.
`ls 02-intake/edits/` is the ledger: PENDING is the to-do list, DONE is closed history,
BLOCKED names the fact it waits on. State lives in the artifact, not in memory.

On "Process edits for <slug>", handle every PENDING file in ascending numeric order:
1. Implement the change in 03-site/.
2. Verify with `npm run build` (in 03-site/); a failing build is not done.
3. Fill `## Resolution` — what changed, files touched, commit hash, date.
4. Set frontmatter `status: DONE` and rename the file `NNN-PENDING-…` → `NNN-DONE-…`.
5. Commit, ONE commit per edit, message `edit NNN: <scope>`.
If an edit needs a missing client fact or conflicts with a Hard rule: do NOT implement it
— write the blocking reason (the exact missing fact or rule) into `## Resolution`, set
`status: BLOCKED`, rename to `NNN-BLOCKED-…`, commit, and CONTINUE to the next edit.
DONE and BLOCKED files are immutable — never edited, never reprocessed. If an edit-id is
duplicated, the highest NNN wins.

When the human describes a change conversationally ("make the hero bigger, add a shipping
FAQ"), do NOT just do it: first author the edit file from the template (next NNN, PENDING),
SHOW it to the human, then process it. The record must always exist before the change does.

## Command 6 — "Publish preview for <slug>" (and the PUBLISH-ALWAYS rule)
Deploy the current `03-site` build as a PRIVATE preview for owner review.
1. Build with noindex ON — previews NEVER get `PUBLIC_INDEXABLE` (so `npm run build`, never the
   production flag). Previews are PERMANENTLY noindex; the staging noindex meta must be in output.
2. Deploy `03-site/dist/` to Cloudflare Pages via wrangler as project `ws-<slug>`:
   `wrangler pages deploy 03-site/dist --project-name ws-<slug>`.
3. Report the public `*.pages.dev` URL, and write `preview_url` + `preview_published_at` into
   `status.json`.
First run only: wrangler isn't set up. Do NOT fail — walk the human through the one-time setup
(`npm i -g wrangler` then `wrangler login`, which opens a browser), then continue.
This is a preview, not a launch: no DNS, no custom domain, no MX/email changes.
**Concept boards are disposable:** deploying `03-site/dist` replaces any concept boards that were
published to `ws-<slug>.pages.dev/concepts/a|b|c/` at the intake step (Command 9) — so the
`/concepts/` routes naturally vanish at the first prototype publish. NEVER carry `/concepts/` into
`03-site/public/`. The screenshots in `02-intake/concepts/` are the permanent record and stay.

### PUBLISH-ALWAYS (universal — replaces any per-trigger auto-publish)
ANY completed change to a client's `03-site` — prototype assembly, edit processing, a spec phase,
or a one-off fix from chat — is NOT "done" until it is live at the preview URL. Every such change
ends with, in order:
1. `npm run build` (verification stays MANDATORY — a failing build is never published or reported done);
2. an automatic Publish preview (the steps above — no need to be asked);
3. `preview_url` + `preview_published_at` refreshed in `status.json`.
**Reporting:** report the preview URL as where to see the WORK (the client site). Do NOT offer
`npm run dev` (the client-site dev server) as the review path — it stays available for your own
debugging only. This applies ONLY to client-site review. The **studio dashboard at
`localhost:8788` is NOT a client site** — it is the control panel for creating clients and running
the pipeline, and remains the local entry point (where the human starts a client and gets the
preview link) until the cloud migration. Keep referencing it for that purpose.
**On deploy failure:** the work STILL commits; log the failure loudly to `status.json` `log[]` and
leave the prior `preview_url` with a `preview_stale: true` flag so the dashboard staleness hint
fires — NEVER silently leave a stale URL unflagged. Then surface the failure in the report.

## Command 7 — "Process deliverables for <slug>"
`02-intake/deliverables-request.md` is a LIVING document. As answers and assets arrive,
update each row's **status** IN PLACE (NEEDED → REQUESTED → RECEIVED → VERIFIED) — rows are
never deleted, only re-statused. On "Process deliverables for <slug>": reconcile the new
information into the rows, then report (a) what is still **BLOCKING** (nothing launches until
these are RECEIVED/VERIFIED — §2.1 and §2.2 always count), and (b) which build phase each
newly-unblocked item releases. When a received asset confirms provenance, that also clears the
matching image/copy FOR REVIEW flag at "Finish".

## Command 8 — "Propose backend config for <slug>"
For a commerce client (ecommerce-catalog archetype) at/after prototype: read
`templates/ecommerce-catalog/BACKEND.md` (the necessity tiers) plus the client's
`01-baseline/feature-census.md`, binding spec, the matching playbook, and
`02-intake/deliverables-request.md`. Emit `02-intake/backend-config.yaml` listing EVERY
module/feature from BACKEND.md with: its **tier**, **on/off**, and a **one-line reason**
(the evidence citation for EVIDENCED; the judgment rationale for JUDGMENT). Apply the baseline
rule: REQUIRED and EVIDENCED are ON by default; JUDGMENT items get a recommended on/off with the
reason; DEFERRED are off unless requested. The file carries a signature block —
`config-id: WS-BCFG-<CLIENT>-NNN`, `version`, `status: DRAFT` until the human confirms, then
`BINDING`. A BINDING backend-config is a BUILD ORDER: Phase 2+ implements EXACTLY its ON set;
changes require a NEW version, never silent edits. (The dashboard can enqueue this headlessly and
flip DRAFT→BINDING on slug-typed confirm — see studio.py "Configure backend".)

## Rehearsal mode (prove Phases 2–4 before a real client depends on them)
A client may carry `mode: rehearsal` in `02-intake/backend-config.yaml`. In rehearsal mode the
Phase 2–4 DELIVERABLES gating is satisfied by STUDIO TEST RESOURCES instead of client facts:
a studio-owned Supabase project, Stripe **TEST-MODE** keys, and Resend's onboarding/test domain.
Client FACTS are never faked — dummy catalogue/content is loudly labelled, never invented client truth.

Hard guarantees:
- **(a)** Every rehearsal surface shows a visible **TEST MODE** banner — admin header AND checkout.
- **(b)** Rehearsal credentials live in `clients/<slug>/02-intake/secrets/.env` (git-ignored) and
  each is tagged `# REHEARSAL`. Never commit secrets.
- **(c)** "Finish" / cutover REFUSES to run while ANY `REHEARSAL`-tagged credential is in use.
  Un-rehearsal is the explicit, human step: swap to the client's real accounts per the swap
  checklist in `templates/ecommerce-catalog/BACKEND.md` (changes: 4 env vars + Stripe webhook
  endpoint + Resend domain; unchanged: schema, code, content).
- Dashboard: Advance/Phase buttons HONOR rehearsal — enabled with a visible **REHEARSAL** badge
  instead of blocked-on-deliverables. The config still has to be BINDING (the build order stands).

**Step 1 of the rehearsal chain is a COMPLETENESS PASS (before any building) — "full" means complete
coverage + the ENTIRE real catalog:**
1. **Complete baseline.** Run any scrape method that hasn't run (incl. the rendered-browser pass).
   For rehearsal only, the mirror runs with a raised but STILL-BOUNDED cap (e.g.
   `MIRROR_MAX_FILES=5000 MIRROR_MAX_SECONDS=2700` — deliberate + logged, never unbounded) so every
   product page is captured. Enumerate ALL product URLs from robots/sitemaps + the site's own
   category/genus indexes; fetch any product pages the mirror missed.
2. **Full feature census** over the complete evidence union — the rehearsal parity floor is EVERY
   feature found (all CARRY-OVERs built, all STUB+FLAGs as honest stubs).
3. **Entire catalog, exactly.** Extract ALL products (no limit) with the cover-image pairing — real
   names, real photos at their largest honest variants, photo-less products as clean type-led cards.
   Scraped prices/descriptions import as DRAFT-labelled REAL data (client facts pending owner
   confirmation — labelled, never silently trusted, never fabricated where absent). Run the
   correspondence verifier over the full set + generate the human QA sheet; the sign-off is a PENDING
   DECISION (inbox), not a chain-blocker.
4. **Phase 2 seeds Supabase with this COMPLETE catalog** — the rehearsal admin manages the real
   inventory and the demo store browses everything the original sold.
Report: products extracted vs the original site's catalog count (with evidence), photo-coverage
stats, and any pages the scrape provably missed.

## Command 9 — "Prepare intake pack for <slug>"
Trigger: auto-enqueued the moment a client reaches `baseline-ready` (also runnable by hand). Produces
two documents in `02-intake/`, grounded ENTIRELY in baseline evidence — everything DRAFT-labelled,
no fabricated client facts:
1. `redesign-plan.md` — the pre-build plan:
   - **2–3 NAMED art-direction concept proposals** (for a commerce archetype, each per the
     brand-moment rules): one sentence + palette + type pairing + signature element + WHERE the
     brand moment lives — each traceable to the client's actual world (from the scrape).
   - **Feature plan** from the census: CARRY-OVER (parity floor) · STUB+FLAG (+ unblock facts) ·
     OBSOLETE (+ reasons).
   - **Block-purpose preview**: the major source blocks → their purpose designations (seeds the
     full purpose map at build).
   - **Scope summary**: archetype, playbook routed, binding specs found, phases anticipated.
2. `deliverables-request.md` — generated HERE (moved out of Command 1) by the same filtering/
   specializing rules; §2.1/2.2 always BLOCKING; auditable "Omitted" list.
3. **CONCEPT BOARDS — three visual mockups across a CREATIVITY SPECTRUM, not documents.** Build a
   single static HTML homepage IMPRESSION per concept (hero + nav + 3–4 product cards + one section
   band), type-led where photography is weak (brand-moment rules), using the client's REAL scraped
   images at their largest honest variants + evidence-derived brand colours. The three boards span a
   DELIBERATE spectrum and MUST differ STRUCTURALLY, not just in palette:
   - **A · CLASSIC** — the safe, conversion-proven expression a cautious owner says yes to instantly.
   - **B · CONFIDENT** — the studio's RECOMMENDATION: distinctive, editorial, clearly designed.
   - **C · BOLD** — pushes the concept hard: unconventional grid, dramatic type scale, a structural idea.
   **Divergence test (binding):** the three boards must differ in at least **layout archetype AND
   typographic attitude AND one structural idea each**. Three palettes on one layout is a GENERATION
   FAILURE — regenerate. (The generator enforces this and exits non-zero on failure.) All three still
   obey the ground rules: honest imagery, accessibility, explicit language, parity-compatible,
   reduced-motion honored. Each board is labelled "CONCEPT BOARD — not the final build" + its tier,
   carries `<meta robots noindex>`, no JS. Pipeline: write `02-intake/concepts/concepts.json`
   (per board — letter/id/name/**tier** (classic|confident|bold|experimental)/recommended/**type_attitude**/
   **structural_idea**/palette/fonts/signature/layout/nav/hero/band/products[]; exactly ONE base board
   recommended = the confident one; `images:[]` ⇒ type-led), then run
   `python3 .claude/skills/site-baseline/scripts/concept_boards.py clients/<slug>` (emits board HTML
   under `02-intake/concepts/site/`, desktop+390px screenshots `02-intake/concepts/<letter>-<id>.png`,
   `boards.json` with `divergence_pass`). DEPLOY to the preview project so boards live at
   `ws-<slug>.pages.dev/concepts/a|b|c/` (`wrangler pages deploy 02-intake/concepts/site
   --project-name ws-<slug>`; create the project first if needed), then write the deployed base into
   `boards.json` `deploy_url`.
Then OPEN the **VISUAL** concept decision (the inbox): **"Choose the design concept for <slug>"** —
each option carries `tier` (`tag:`), `board_url` (live board) + `thumb` (screenshot filename) so the
dashboard renders the screenshots as clickable thumbnails, recommendation marked. The chosen option
(whatever letter) is what Command 1 step 0 records and builds; an **experimental** choice also gets a
one-line risk note in the redesign plan ("chosen direction is unconventional; validate with the owner
early"). (Boards are disposable — Command 1/6: `/concepts/` routes drop at the next publish; the PNGs
persist as the permanent record of what was offered and chosen.)
   **THE WOW LEVER — "🔥 Push further" (optional, human-in-the-loop, appears only AFTER the 3 boards
   exist).** A fourth control on the decision card enqueues a headless job (no slug confirm — it's
   generative, not destructive) producing **Board D**: a deliberately experimental concept BEYOND
   Board C — permission to break conservative commerce conventions (asymmetry, oversized type as the
   entire hero, an unconventional navigation metaphor, one theatrical interactive moment) while still
   respecting the HARD rules (no upscaled imagery, reduced-motion honored, parity reachable, no banned
   patterns). D publishes at `/concepts/d/`, screenshots, and joins the card as a fourth option
   labelled "experimental". The button can fire once more for **Board E**; **cap at two escalations** —
   beyond E the fix is a conversation, not regeneration (open a decision note instead). Full-build
   from-scratch is unaffected: it auto-accepts **Board B** (the recommendation); wow is a human lever.

## Creativity controls — ONE coherent model (STANDARD · PUSH FURTHER · OVERHAUL)
Three tiers, no overlaps. ("creative mode" and "the overhaul button" are the SAME thing — one
capability reached two ways.)
- **STANDARD** — the default. Clean, purpose-fit; passes the full Design QA Gate + names the brand
  moment. No flag.
- **PUSH FURTHER** — incremental. The 🔥 button on the concept-board decision generates ONE bolder
  board beyond A/B/C (Board D, then E; cap at two), still standard effort. A board generator, not a
  build mode.
- **OVERHAUL / CREATIVE** — the maximal swing: a from-scratch reimagining with full creative-mode
  craft = disciplined graphic richness **AND** smooth modern interactivity (section scroll narrative,
  scroll-reveals, hover category tiles, slide-out drawers, condensing sticky header, ONE signature
  motion moment — full spec ECOMMERCE-GUIDELINES §5.9). ONE capability (`design_mode: creative` in status.json),
  reachable TWO ways: (a) the **Creative** toggle at build start (Full build), or (b) the **🎨 Overhaul**
  button on the boards card. Both offer the SAME two input modes: **"Claude develops it"** or
  **"I provide a starting point"** (`02-intake/overhaul-brief.md`, with the Mode-B guardrail: take
  inspiration, NEVER copy the reference's trade dress).
- **Three HARD invariants hold across ALL tiers:** the **parity floor** is untouched (every CARRY-OVER
  feature stays); every **studio + archetype Hard rule** is untouched; the swing is **EXPRESSION-ONLY**
  (layout / type / color / motion / graphics) — never facts, features, or guardrails.

## Command 10 — "Full build (<variant>) for <slug>" (one-click chained rehearsal build)
The dashboard's **Full build** button triggers this as a headless `claude -p` job. TWO variants
share ONE chain; the dashboard renders them mutually exclusively by stage and lays down the step
artifact `02-intake/full-build-progress.json` before spawning. You DRIVE that file: read it first;
for each step whose status isn't `done`, set it `active` (write the file), do the work, then set it
`done` with a one-line note + UTC timestamp (write again). This makes the build **resumable**
(re-running skips `done` steps) and streams live progress to the row.
- **`from-scratch`** (at `baseline-ready`, no prototype): rehearsal mode → complete-coverage
  re-scrape + full-catalog extraction → **assemble to the RECOMMENDED concept, auto-accepted** (if
  the concept decision is still OPEN, resolve it to the recommended option and record that the full
  build auto-accepted it — do NOT wait; boards are still generated/recorded) → propose + auto-bind
  backend config (DRAFT→BINDING) → Phases 2–4 on TEST creds → publish.
- **`from-prototype`** (at `prototype` and later): **PRESERVE the existing prototype EXACTLY** —
  every processed edit, the chosen concept, all design decisions stand. Run only what's missing:
  rehearsal mode → backend config (auto-bind if none BINDING; **if a BINDING config already exists,
  USE it untouched** — never overwrite confirmed decisions) → Phases 2–4 → publish.
Both: **precondition** — step `precond` confirms `02-intake/secrets/.env` has rehearsal TEST creds
tagged `# REHEARSAL`; if missing, mark the step `blocked`, OPEN a decision, and STOP (the dashboard
button is also disabled until they exist). Slug-typed confirm (enforced by `/api/full-build`).
TEST MODE banners on every surface; **cutover stays refused** while any `# REHEARSAL` credential is
in use (unchanged). On ANY fork needing the human's judgment, do NOT guess — open a decision with
`resume_job` set (so resolving it resumes the build), leave the step `active`, and STOP. Every
completed step still obeys PUBLISH-ALWAYS and the parity floor + Hard rules.

## Product correspondence (catalog builds) — binding
Every field of a product entry — name, label, price, description, AND photo — is assembled
ONLY from that product's OWN source page. In `crawl.json` each page carries its own `images[]`;
the catalog extractor must keep a product's text and its image together as they appeared on the
same page. NEVER pool images across pages and re-attach them by filename, array order, or index —
that silently produces a right-name / wrong-photo catalog.

Catalog-build verification step (run before declaring a catalog build done): spot-check 10 random
built products against their source pages (the `source_page` recorded per record) — confirm the
rendered name/species matches the photo's origin page. ANY name↔photo mismatch is a BUILD FAILURE
to fix before reporting, not a cosmetic note.

## Purpose-first reconstruction — binding build rule
NEVER port or restyle source markup. For every content/UI block in the scraped source, FIRST
designate its broad PURPOSE with a plain name — announcement banner, trust strip, category index,
product card, promo/offer, hours-or-policy notice, guarantee statement, testimonial, contact
strip, newsletter capture, etc. — and RECORD that designation. THEN implement the best modern
expression of that purpose using the component catalog (or a new component): improving aesthetics
and functionality is the EXPECTATION; fidelity to the old markup is explicitly NOT a goal. A block
whose purpose can't be confidently designated is flagged for the human's judgment, never copied.
Components are NAMED BY PURPOSE, never by appearance (`AnnouncementBanner`, not `GreenStripe`).

## Build specs (binding build orders)
Any `.md` file in a client's `02-intake/specs/` is a BINDING build order, not a
suggestion. When assembling a prototype or finishing a client, read every spec in
`02-intake/specs/` first and treat its instructions as authoritative — they override
general defaults, archetype conventions, and playbook guidance where they conflict.
Specs never override the Hard rules below (e.g. never fabricate facts, never edit
templates/ in place). If a spec conflicts with a Hard rule, follow the Hard rule and
flag the conflict FOR REVIEW.

## Industry playbooks
When assembling a prototype or finishing a client, ALWAYS check playbooks/ for a file
matching the client's industry (from brief.yaml `industry:`, or inferred from the
baseline if blank — record the inference). If a match exists, read it and apply it to
content drafting, schema, section choices, and tone. If none exists, say so explicitly,
proceed with general defaults, and suggest creating one from playbooks/_TEMPLATE.md.

## Command composition (work with the allowlist, not around it)
Bash permissions in `.claude/settings.local.json` match command PREFIXES, and a compound
command (`a && b`, `a; b`) is matched as a whole — so a chain can slip a denied command past
a deny rule, and a `cd`-prefixed chain matches none of the allow patterns. Therefore:
- Run from the project root and address other dirs with tool-native flags, not `cd`:
  `git -C /Users/ericliu/web-studio <sub>`, `npm run build --prefix <dir>`, absolute paths for
  `cp`/`python3 .claude/skills/...`. This keeps every command cwd-independent.
- Prefer SEPARATE simple commands over `&&`/`;` chains (run independent ones in parallel tool
  calls). Never glue a step onto an `echo`/`cd` just to dodge a pattern.
- Never reshape a command to evade a deny rule. If a command you genuinely need has no allow
  rule, say so and propose adding the rule — don't work around it.

## studio.py change protocol — binding (kill the stale-server class of bug)
The dashboard is a long-lived `python3 studio.py` process that loads the file ONCE at launch; a
parallel/older instance serving stale code is the recurring root cause behind "missing buttons,
inaccessible creative mode, reverting radios, broken upload." Therefore: **any task that edits
`studio.py` is NOT done until the server is restarted onto the new code AND the dashboard version
stamp is verified to equal HEAD.** Concretely:
1. After editing studio.py, restart with `./restart.sh` (kills any instance on the port, relaunches
   on current code). Do NOT hand-start a second `python3 studio.py` — the single-instance guard
   refuses a duplicate (names the incumbent PID; `STUDIO_TAKEOVER=1` to take the port).
2. VERIFY the footer version stamp / `/api/clients` `version.head` equals `git rev-parse --short HEAD`
   and `version.stale` is false. A mismatch means a stale server is still serving — restart again.
3. The dashboard self-reports staleness: a non-dismissable banner fires whenever the on-disk
   studio.py fingerprint differs from the one the running process loaded. Never report a studio.py
   change "done" while that banner would show.

**Render invariant — binding (the dashboard poll must NEVER destroy in-flight UI state).** The 4 s
auto-refresh is interaction-aware, not a wholesale `innerHTML` rebuild: each row is a data-only
`.live` zone (re-rendered every poll) plus a controls zone (stateful inputs, built once); a container
the user is touching — focus, a STAGED FILE, typed text, a flipped radio/checkbox, an open panel — is
never rebuilt, only its `.live` zone is patched (`load()`→`reconcileList()`/`interacting()`; the same
guard protects `#needs`). This is an ARCHITECTURAL property, not a per-control concern: any NEW
interactive element is automatically protected as long as it lives in the controls zone (or is caught
by `interacting()`) — do NOT reintroduce snapshot-and-restore patches or full-list `innerHTML=`
replacement. File inputs in particular can't be value-restored (browser security), so the only correct
fix is skip-while-staged, which this guarantees.

## Decision surfaces — binding
Any capability that requires the human's JUDGMENT — mode changes, config confirmations, choices
between alternatives, approvals — MUST ship with a dashboard control in the SAME commit that
creates it. A decision point reachable only via terminal or chat is an INCOMPLETE feature.
The generalized mechanism is the **decisions inbox** (filename-is-state, mirroring edits): when a
command or headless job hits a fork needing the human's call, it does NOT guess and does NOT die
silently — it writes `clients/<slug>/02-intake/decisions/NNN-OPEN-<short-name>.yaml` (studio-level:
`.claude/decisions/`) with question / context / options (each + consequence) / recommendation +
reason / what-happens-next per option. The dashboard renders OPEN decisions in a "Needs your call"
strip; resolving one records the choice + timestamp, renames OPEN→RESOLVED (immutable history),
logs to status.json, and resumes any job the decision was blocking.

## Troubleshooting workflow — binding (diagnose THEN fix)
When the human reports something not working — ANY phrasing ("X is broken", "this doesn't load",
"the button does nothing") — do NOT start changing files. First MATERIALIZE an incident:
`clients/<slug>/02-intake/incidents/NNN-OPEN-<short-name>.md` (studio-level problems →
`.claude/incidents/`), from `templates/incident-template.md`. The filename IS the state
(OPEN / BLOCKED / RESOLVED). The six sections are binding:
- **SYMPTOM** — the human's words VERBATIM + where observed (URL, screen, command).
- **DIAGNOSTIC** — evidence gathered BEFORE any fix; reproduce the failure FIRST (build output,
  status.json log, audit log, browser-visible behavior, the failing request/route); state what was
  checked and what each check showed. No reproduction ⇒ say so honestly + what's needed to reproduce.
- **ROOT CAUSE** — ONE falsifiable sentence naming the actual cause, traced to evidence. "Probably X"
  is not a root cause — keep diagnosing, or state competing hypotheses + how the fix discriminates.
- **FIX PLAN** — smallest change addressing the root cause; every file to touch + why. Reimplementation
  is allowed when the diagnostic shows the implementation itself is unsound — say so, don't patch rot.
- **VERIFICATION** — re-run the reproduction (must now pass) + re-run every parity-checklist row the
  touched files could disturb (the verification-loop rule applies).
- **RESOLUTION** — filled at close: what changed, commit(s), evidence the symptom is gone.

Execution rules:
1. **Client-site** fixes implement THROUGH the edit convention (the incident links its edit NNN);
   **studio-system** fixes commit directly with the SYSTEM.md update. Publish-always applies to site fixes.
2. **One root cause per incident.** A diagnostic that uncovers a second independent problem opens a
   SECOND incident rather than scope-creeping.
3. If the fix needs a missing client fact/credential: incident → `NNN-BLOCKED-…` naming it + a decision card.
4. Rename OPEN→RESOLVED ONLY after verification passes; RESOLVED incidents are immutable history.
5. **RECURRENCE:** a symptom matching a RESOLVED incident reopens as a NEW incident referencing the old
   one — and the diagnostic must explain why the previous fix didn't hold before any new fix lands.
Dashboard: every client row + the studio header carry a "Report a problem" box; submitting it creates
the OPEN incident (the words become the SYMPTOM) and enqueues the headless diagnostic. Open incidents
show as a count badge with the decisions card treatment. The chat tier routes problem reports through
this convention instead of ad-hoc fixing.

## Findings & reports — binding (a finding only in scrollback doesn't exist)
Any substantive finding or report — build/assemble reports, feature-census summaries, verification-loop
checklist results, Design QA audits, incident diagnostics + resolutions, correspondence-audit results,
backend phase reports, scrape coverage summaries — is WRITTEN, at the moment it is produced, as a
markdown file: `clients/<slug>/02-intake/reports/<YYYY-MM-DD-HHMM>-<kind>.md` (studio-level findings →
`.claude/reports/`). Terminal/chat output stays the conversational copy; the FILE is the record.
- Reports are **append-only history** — never edited after the fact; a correction is a NEW report that
  references the old one.
- Artifacts that ARE already the record (edit `## Resolution` blocks, incident files, the parity
  checklist, coverage.md) are **LINKED from a report, never duplicated**.
- Every finding-producing flow ends with this write: the **advance jobs, full-build chains, the
  incident workflow, the verification loop, and the intake pack** all finish by emitting their report
  file (the conventions they already follow now end with the file write — nothing to remember).
Dashboard: the row's Documents panel gains a **Reports** section (newest first; kind + timestamp +
one-line summary = the file's first heading/summary line; click renders the markdown; a "new" dot when
reports appeared since you last opened that client's panel). Studio-level reports show in the header.

## Auto-approval audit
At the END of every task, read the `.claude/audit/session.log` entries written since the
task began and emit a mini report: the total count of auto-approved actions, grouped (file
edits / shell commands / deploys) with one-line summaries, and FLAG anything outside the
routine pattern (a deploy, a deletion, anything touching paths outside the project). Then
archive the log to `.claude/audit/<YYYY-MM-DD>-<task-slug>.log` and start a fresh
`session.log`. The log is appended automatically by the PostToolUse hook in
`.claude/settings.local.json`; `.claude/audit/` is git-ignored.

## Design ground rules — binding on every build and template
1. **Named concept.** Each site has ONE recorded sentence of art direction; every visual
   decision must trace to it. No concept, no build.
2. **Distinctiveness bar.** Banned by default: generic template sameness (white bg + gray
   cards + blue accent), default system fonts, stock-gradient heroes, three-icon feature rows.
   Each site ships ONE memorable signature visual element.
3. **Typography with intent.** A characterful display face deliberately paired with a body
   face; bold scale contrast. Never default-sans-for-everything.
4. **Imagery non-negotiables.** (a) Resolve scraped images to their LARGEST variants — detect
   thumbnail URL patterns, fetch the originals, RECORD dimensions. (b) Never upscale or stretch;
   an image below the slot minimum (hero ≥1600px wide, card ≥600px) is REJECTED from that slot
   and a photography ask is added to the deliverables request. (c) One cropping/color treatment
   per site. (d) Heroes are full-bleed, single-subject, art-directed.
5. **Motion.** Subtle, purposeful microinteractions that serve the concept; always honor
   `prefers-reduced-motion`. No parallax circus.
6. **DESIGN QA GATE.** A build is NOT done until a recorded self-audit passes: names the concept
   + the signature element; zero banned patterns; every image meets its slot minimum, is
   unstretched and correspondence-correct; checked at desktop AND ~390px mobile; and answers
   honestly "would a visitor remember this tomorrow, and does it outclass the client's
   competitors?". Failures iterate BEFORE reporting. The audit is appended to the build report
   (and, for an edit, to that edit's Resolution).

Pipeline support: image records carry `source_page`, pixel `dimensions`, and the
`largest_variant` URL; builds consume that record (never raw thumbnail URLs).

## Verification loop — binding on Command 1 and any full-build chain
After assembling a prototype, do NOT report or publish "done" on belief. Run the parity checklist
(`01-baseline/parity-checklist.md`): execute each row's verification method against the BUILT OUTPUT
(`dist/`, the rendered routes) — NEVER against intentions or source code you remember writing. For
every unmet row: implement the fix, `npm run build`, re-verify THAT row and any row the fix could
have disturbed. Iterate until every row is `[x]` verified-with-evidence or `[B]` BLOCKED naming the
exact missing client fact / deliverable ID (BLOCKED is for genuinely ungated-on-us items only —
never a euphemism for "didn't get to it"). HARD CAP: 5 iterations; if rows remain unmet at the cap,
STOP, report the survivors honestly as failures with your diagnosis, and open a decision card —
never loop forever, never quietly ship around them. The completed checklist, with per-row evidence
one-liners and the iteration count, is pasted verbatim into the build report and committed alongside
the build. **Publish-always runs only after the loop exits.**
- **Scope:** the loop also runs (against the relevant checklist subset) after "Process edits" batches
  and at "Finish". The full-rehearsal chain runs it at the assemble step AND again after Phase 4 with
  the backend rows added (test checkout completes, admin CRUD works, notify-email loop fires).
- A checklist row without an executable verification method is itself invalid (fix the checklist).

## Baseline = the scrape ladder (resilient to bot-blocked sites)
`run_baseline.py` is an escalating cascade, not a fixed 3-method run: crawler → rendered browser
(Playwright, the anti-bot weapon) → wget mirror (breadth, only when content is flowing) → Wayback
archive (only when blocked; content is STALE, labelled `ARCHIVE-*`, never price/stock truth) →
human (a decision card with a ready-to-send owner-export note). Missing tools log LOUDLY and count
as rung failures — never a silent skip. `coverage.md` records each rung + which rungs the baseline
rests on; the census + tokens note evidence source LIVE vs ARCHIVE. See SYSTEM.md.

## Hard rules — always, regardless of skill loading
- NEVER fabricate a client fact. Blanks stay blank and get flagged FOR REVIEW.
- NEVER edit templates/ for a client; copy first.
- NEVER touch or advise changing MX/SPF/DKIM/DMARC records; flag email-affecting steps for the human.
- Redirects live at the host/CDN edge, never in page JavaScript.
- Staging builds keep noindex; only PUBLIC_INDEXABLE=true removes it (launch step zero, human-confirmed).
- Reuse the client's EXISTING GA4 property; issue NEW Turnstile/reCAPTCHA keys per rebuild.
- Scraped copy is DRAFT until the owner's answers or explicit human review confirm ownership (license risk).
- Images (OVERRIDES the earlier "never ship scraped imagery" rule): PROTOTYPES MAY use
  images scraped from the client's OWN website (it is their material, shown back to them).
  Protection moves to PRODUCTION: at "Finish <slug>", every image must be client-supplied or
  have provenance confirmed via intake — any image that isn't gets flagged FOR REVIEW and
  replaced before launch. Never use third-party/stock imagery scraped from elsewhere.
- All colors/fonts via @theme tokens; no literal hex in components.
