# CLAUDE.md — Web Studio Orchestrator
Multi-client website-rebuild studio. The human gives two inputs per client (a domain, then the
owner's questionnaire answers); everything else is automated by `.claude/skills/` and by you.
Deeper background (architecture, glossary, deliverables): read CONTEXT.md when needed.

## Client folder contract (never deviate)
```
clients/<slug>/
  00-source/    raw scrapes — read-only evidence, never edit
  01-baseline/  extracted facts & drafts from the site-baseline skill
  02-intake/    human truth: brief.yaml, owner-answers.txt, assets/, redirect-map.csv
  03-site/      the client's Astro project (copied from templates/, then customized)
  04-cutover/   runbook, snapshots, check reports
  status.json   {stage, log[]} — update stage after every pipeline step
```
Stages: queued → scraping → baseline-ready → prototype → awaiting-owner → answers-received →
final → cutover-checked → (archived). Clients run concurrently; `clients/` holds only ACTIVE
work. Finished projects move to `archive/<slug>-<timestamp>/` (read-only history).

## Command 1 — "Assemble prototype for <slug>" (trigger: stage == baseline-ready)
0. Build to the design concept the human picked on the "Choose the design concept" decision. If
   that decision is unresolved, STOP and surface it — never guess the concept.
1. Read all of `01-baseline/` (inventory, drafts, audits, coverage, feature-census) and
   `02-intake/redesign-plan.md`. PARITY FLOOR: carry every CARRY-OVER feature; give every
   STUB+FLAG feature a visible honest stub. New/better features come ON TOP of parity, never
   instead of it. Dropping a CARRY-OVER feature is a build failure unless the census marked it
   OBSOLETE.
2. Copy the matching archetype from `templates/` into `03-site/` (`cp -R`; never build in templates/).
3. Apply `01-baseline/tokens-draft.json` to the @theme block; mirror to `03-site/tokens.json`.
4. Map `content-draft.md` into the data slots; everything is marked DRAFT (scraped, unverified).
5. Seed `02-intake/brief.yaml` with every baseline-established fact (domain, GA4/CMS from
   tech-fingerprint.md); leave unknown fields blank, never guessed.
6. Seed `02-intake/redirect-map.csv` from url-inventory.csv (old URLs filled, new proposed).
7. `npm install && npm run build` in 03-site/; fix failures.
8. Set stage=prototype, then awaiting-owner. Report what was applied, what is DRAFT, what is blank.
9. UPDATE `02-intake/deliverables-request.md` (created at intake) with build-time discoveries
   (integrations confirmed in code, image-resolution gaps, forms wired). Never silently drop rows.
10. Generate `01-baseline/block-purpose-map.md` — table: source block (page + identifier) →
    purpose designation → target component → improvement made. Proves every block was UNDERSTOOD,
    not transcribed. (Refreshed at "Finish" too.)
11. Generate `02-intake/production-roadmap.md` — CLIENT-FACING, plain-language description of what
    the complete product does that the prototype doesn't yet:
    - Sources merged: the binding spec's phased features; the census STUB+FLAG list (EVERY stub
      must appear, honestly labelled); the playbook's Tier 2/3 features, marked as optional later
      additions, not promises.
    - Each entry: feature name → one sentence on what it does for the client's business (no jargon,
      no phase numbers, no stack names) → one line on what unblocks it, cross-referenced to the
      deliverables request (e.g. "available once we have your Stripe account — item D-2.7.1").
    - Two sections: "Included in your complete site" / "Optional additions we'd recommend down the
      road." Tone: confident, concrete, honest. Living doc: live features move to a "Now live" list
      at top; rows never silently vanish.

## Command 2 — "Finish <slug>" (trigger: 02-intake/owner-answers.txt exists)
Use the apply-intake skill: parse answers (answered / UNSURE / DELEGATED / SKIPPED), reconcile into
brief.yaml, resolve UNSURE items marked permission_to_investigate=YES via technical lookups, replace
DRAFT content with verified facts, finalize redirect-map and emit edge config, rebuild, set
stage=final. Produce `04-cutover/launch-runbook.md` and a FOR-REVIEW list.

## Command 3 — "Run cutover prechecks for <slug>"
Use the cutover skill and its scripts (launch_check.py, redirect_check.py, zone_diff.py). Write
reports into `04-cutover/`. Set stage=cutover-checked only if all checks pass.

## Command 4 — "Archive <slug>"
Normally done via the dashboard button; if asked: verify stage is final or cutover-checked (warn
otherwise), then move `clients/<slug>/` to `archive/<slug>-<YYYYmmdd-HHMMSS>/`. Never delete client
folders; archive is the only removal path.

## Command 5 — "Process edits for <slug>"
Each revision request is a file `clients/<slug>/02-intake/edits/NNN-PENDING-<short-name>.md` (from
`templates/edit-template.md`). The filename IS the state — PENDING / DONE / BLOCKED;
`ls 02-intake/edits/` is the ledger. Handle every PENDING file in ascending numeric order:
1. Implement the change in 03-site/.
2. Verify with `npm run build`; a failing build is not done.
3. Fill `## Resolution` (what changed, files, commit hash, date).
4. Set frontmatter `status: DONE`, rename `NNN-PENDING-…` → `NNN-DONE-…`.
5. Commit, one per edit, message `edit NNN: <scope>`.
If an edit needs a missing client fact or conflicts with a Hard rule: do NOT implement it — write
the exact blocking reason into `## Resolution`, set `status: BLOCKED`, rename to `NNN-BLOCKED-…`,
commit, and CONTINUE. DONE/BLOCKED files are immutable. Duplicate edit-id: highest NNN wins.
When the human describes a change conversationally, first author the edit file (next NNN, PENDING),
SHOW it to the human, THEN process it — the record exists before the change does.

## Command 6 — "Publish preview for <slug>" + PUBLISH-ALWAYS
Deploy the current `03-site` build as a PRIVATE preview:
1. Build with noindex ON — previews NEVER get `PUBLIC_INDEXABLE`; staging noindex meta must be in
   output (`npm run build`, never the production flag).
2. `wrangler pages deploy 03-site/dist --project-name ws-<slug>`.
3. Report the `*.pages.dev` URL; write `preview_url` + `preview_published_at` to status.json.
First run only: if wrangler isn't set up, don't fail — walk the human through one-time setup
(`npm i -g wrangler`, then `wrangler login`), then continue. Preview, not launch: no DNS, no custom
domain, no MX/email changes. Concept boards are disposable: deploying `03-site/dist` replaces any
boards at `ws-<slug>.pages.dev/concepts/a|b|c/`; NEVER carry `/concepts/` into `03-site/public/`.
The screenshots in `02-intake/concepts/` are the permanent record.

PUBLISH-ALWAYS (universal): ANY completed change to a client's `03-site` (prototype, edit, spec
phase, chat fix) is not done until it is live at the preview URL. Every change ends with, in order:
1. `npm run build` (MANDATORY — a failing build is never published or reported done);
2. an automatic Publish preview (no need to be asked);
3. `preview_url` + `preview_published_at` refreshed in status.json.
Report the preview URL as where to see the WORK; do NOT offer `npm run dev` as the review path (your
debugging only). The studio dashboard at `localhost:8788` is NOT a client site — it's the control
panel and stays the local entry point. On deploy failure: the work STILL commits; log the failure
loudly to status.json `log[]` and set `preview_stale: true` on the prior preview_url (never leave a
stale URL unflagged); surface the failure in the report.

## Command 7 — "Process deliverables for <slug>"
`02-intake/deliverables-request.md` is LIVING: update each row's status IN PLACE (NEEDED → REQUESTED
→ RECEIVED → VERIFIED); rows are never deleted. On run: reconcile new info, then report (a) what is
still BLOCKING (nothing launches until RECEIVED/VERIFIED — §2.1 and §2.2 always count) and (b) which
build phase each newly-unblocked item releases. A received asset confirming provenance also clears
the matching image/copy FOR REVIEW flag at "Finish".

## Command 8 — "Propose backend config for <slug>"
For a commerce client (ecommerce-catalog) at/after prototype: read
`templates/ecommerce-catalog/BACKEND.md` (necessity tiers) plus the client's feature-census,
binding spec, matching playbook, and deliverables-request. Emit `02-intake/backend-config.yaml`
listing EVERY BACKEND.md module with its tier, on/off, and one-line reason (evidence citation for
EVIDENCED; rationale for JUDGMENT). Baseline rule: REQUIRED + EVIDENCED ON by default; JUDGMENT gets
a recommended on/off + reason; DEFERRED off unless requested. Signature block:
`config-id: WS-BCFG-<CLIENT>-NNN`, `version`, `status: DRAFT` until the human confirms, then
`BINDING`. A BINDING config is a BUILD ORDER: Phase 2+ implements EXACTLY its ON set; changes need a
NEW version, never silent edits. (Dashboard can enqueue this and flip DRAFT→BINDING on slug-typed
confirm.)

## Rehearsal mode (prove Phases 2–4 before a real client depends on them)
A client may carry `mode: rehearsal` in backend-config.yaml. Phase 2–4 deliverables gating is then
satisfied by STUDIO TEST RESOURCES instead of client facts: a studio Supabase project, Stripe
TEST-MODE keys, Resend's onboarding/test domain. Client FACTS are never faked — dummy
catalogue/content is loudly labelled, never invented as client truth.
Hard guarantees:
- (a) Every rehearsal surface shows a visible TEST MODE banner — admin header AND checkout.
- (b) Rehearsal credentials live in `clients/<slug>/02-intake/secrets/.env` (git-ignored), each
  tagged `# REHEARSAL`. Never commit secrets.
- (c) "Finish"/cutover REFUSES to run while ANY `REHEARSAL`-tagged credential is in use.
  Un-rehearsal is an explicit human step per the swap checklist in BACKEND.md (changes: 4 env vars
  + Stripe webhook endpoint + Resend domain; unchanged: schema, code, content).
- Dashboard Advance/Phase buttons honor rehearsal — enabled with a REHEARSAL badge instead of
  blocked-on-deliverables. The config must still be BINDING.

Step 1 of the rehearsal chain is a COMPLETENESS PASS before any building ("full" = complete coverage
+ the ENTIRE real catalog):
1. Complete baseline. Run any scrape rung not yet run (incl. rendered-browser). Mirror runs with a
   raised but STILL-BOUNDED cap (e.g. `MIRROR_MAX_FILES=5000 MIRROR_MAX_SECONDS=2700` — logged,
   never unbounded) so every product page is captured. Enumerate ALL product URLs from
   robots/sitemaps + the site's own category indexes; fetch any pages the mirror missed.
2. Full feature census over the complete evidence union — parity floor is EVERY feature found.
3. Entire catalog, exactly. Extract ALL products (no limit) with cover-image pairing — real names,
   real photos at largest honest variants, photo-less products as clean type-led cards. Scraped
   prices/descriptions import as DRAFT-labelled REAL data (labelled, never silently trusted, never
   fabricated where absent). Run the correspondence verifier over the full set + generate the human
   QA sheet; sign-off is a PENDING DECISION (inbox), not a chain-blocker.
4. Phase 2 seeds Supabase with this COMPLETE catalog.
Report: products extracted vs the original catalog count (with evidence), photo-coverage stats, and
any pages the scrape provably missed.

## Command 9 — "Prepare intake pack for <slug>" (auto-enqueued at baseline-ready)
Produces two documents in `02-intake/`, grounded ENTIRELY in baseline evidence, all DRAFT-labelled:
1. `redesign-plan.md`:
   - 2–3 NAMED art-direction concept proposals (commerce: per brand-moment rules): one sentence +
     palette + type pairing + signature element + WHERE the brand moment lives — each traceable to
     the client's actual world.
   - Feature plan from the census: CARRY-OVER (parity floor) · STUB+FLAG (+ unblock facts) ·
     OBSOLETE (+ reasons).
   - Block-purpose preview: major source blocks → purpose designations (seeds the full map at build).
   - Scope summary: archetype, playbook routed, binding specs found, phases anticipated.
2. `deliverables-request.md` — generated here by the filtering/specializing rules; §2.1/2.2 always
   BLOCKING; auditable "Omitted" list.
3. CONCEPT BOARDS — three visual mockups across a CREATIVITY SPECTRUM, not documents. Build one
   static HTML homepage impression per concept (hero + nav + 3–4 product cards + one section band),
   type-led where photography is weak, using the client's REAL scraped images at largest honest
   variants + evidence-derived brand colours. The three boards MUST differ STRUCTURALLY, not just
   palette:
   - A · CLASSIC — safe, conversion-proven; a cautious owner says yes instantly.
   - B · CONFIDENT — the studio's RECOMMENDATION: distinctive, editorial, clearly designed.
   - C · BOLD — pushes hard: unconventional grid, dramatic type scale, a structural idea.
   Divergence test (binding): the boards must differ in layout archetype AND typographic attitude
   AND one structural idea each. Three palettes on one layout is a GENERATION FAILURE — regenerate
   (the generator enforces this and exits non-zero). All three obey the ground rules (honest
   imagery, accessibility, explicit language, parity-compatible, reduced-motion). Each board is
   labelled "CONCEPT BOARD — not the final build" + tier, carries `<meta robots noindex>`, no JS.
   Pipeline: write `02-intake/concepts/concepts.json` (per board: letter/id/name/tier
   (classic|confident|bold|experimental)/recommended/type_attitude/structural_idea/palette/fonts/
   signature/layout/nav/hero/band/products[]; exactly ONE board recommended = the confident one;
   `images:[]` ⇒ type-led), then run
   `python3 .claude/skills/site-baseline/scripts/concept_boards.py clients/<slug>` (emits board HTML
   under `02-intake/concepts/site/`, desktop+390px screenshots `02-intake/concepts/<letter>-<id>.png`,
   `boards.json` with `divergence_pass`). DEPLOY to the preview project
   (`wrangler pages deploy 02-intake/concepts/site --project-name ws-<slug>`; create the project
   first if needed) so boards live at `ws-<slug>.pages.dev/concepts/a|b|c/`, then write the deployed
   base into `boards.json` `deploy_url`.
Then OPEN the VISUAL concept decision (inbox): "Choose the design concept for <slug>" — each option
carries `tier` (`tag:`), `board_url` + `thumb` (screenshot filename) so the dashboard renders
clickable thumbnails, recommendation marked. The chosen option is what Command 1 step 0 builds; an
experimental choice also gets a one-line risk note in the redesign plan. Boards are disposable
(`/concepts/` routes drop at next publish; PNGs persist as the permanent record).

THE WOW LEVER — "🔥 Push further" (optional, human-in-the-loop, only AFTER the 3 boards exist):
generates Board D, then E — experimental concepts BEYOND Board C, respecting the Hard rules; cap at
two escalations. Full-build from-scratch auto-accepts Board B. Mechanism: SYSTEM.md §4.

## Creativity controls — STANDARD · PUSH FURTHER · OVERHAUL (one model, no overlaps)
- STANDARD — default. Clean, purpose-fit; passes the Design QA Gate + names the brand moment. No flag.
- PUSH FURTHER — the 🔥 button: generates ONE bolder board beyond A/B/C (D, then E; cap two), still
  standard effort. A board generator, not a build mode.
- OVERHAUL / CREATIVE — the maximal swing: a from-scratch reimagining with full creative-mode craft
  (graphic richness + modern interactivity: scroll narrative, scroll-reveals, hover tiles, slide-out
  drawers, condensing sticky header, ONE signature motion moment — full spec GUIDELINES §5.9). ONE
  capability (`design_mode: creative` in status.json), reached two ways: the Creative toggle at build
  start, or the 🎨 Overhaul button on the boards card. Both offer "Claude develops it" or "I provide
  a starting point" (`02-intake/overhaul-brief.md`; Mode-B guardrail: take inspiration, NEVER copy
  the reference's trade dress). Mechanism: SYSTEM.md §4.
Three HARD invariants across ALL tiers: the parity floor is untouched (every CARRY-OVER stays); every
studio + archetype Hard rule is untouched; the swing is EXPRESSION-ONLY (layout/type/color/motion/
graphics) — never facts, features, or guardrails.

## Command 10 — "Full build (<variant>) for <slug>" (one-click chained rehearsal build)
Triggered by the dashboard's Full build button as a headless `claude -p` job. Two variants share one
chain; the dashboard lays down `02-intake/full-build-progress.json` before spawning. DRIVE that
file: read it first; for each step not `done`, set it `active` (write), do the work, set it `done`
with a one-line note + UTC timestamp (write). This makes the build resumable and streams progress.
- `from-scratch` (at baseline-ready, no prototype): rehearsal mode → complete-coverage re-scrape +
  full-catalog extraction → assemble to the RECOMMENDED concept, auto-accepted (if the concept
  decision is still OPEN, resolve it to the recommended option and record the auto-accept; don't
  wait; boards still generated/recorded) → propose + auto-bind backend config (DRAFT→BINDING) →
  Phases 2–4 on TEST creds → publish.
- `from-prototype` (at prototype or later): PRESERVE the existing prototype EXACTLY (every processed
  edit, the chosen concept, all design decisions stand). Run only what's missing: rehearsal mode →
  backend config (auto-bind if none BINDING; if a BINDING config exists, USE it untouched) →
  Phases 2–4 → publish.
Both: precondition step `precond` confirms `02-intake/secrets/.env` has rehearsal TEST creds tagged
`# REHEARSAL`; if missing, mark the step `blocked`, OPEN a decision, STOP (the button is also
disabled). Slug-typed confirm (enforced by `/api/full-build`). TEST MODE banners on every surface;
cutover stays refused while any `# REHEARSAL` credential is in use. On ANY fork needing human
judgment, do NOT guess — open a decision with `resume_job` set, leave the step `active`, STOP. Every
step obeys PUBLISH-ALWAYS + the parity floor + Hard rules.

## Product correspondence (catalog builds) — binding
Every field of a product entry — name, label, price, description, AND photo — is assembled ONLY from
that product's OWN source page. In `crawl.json` each page carries its own `images[]`; keep a
product's text and image together as they appeared on the same page. NEVER pool images across pages
and re-attach by filename, array order, or index — that silently produces right-name/wrong-photo.
Verification (before declaring a catalog build done): spot-check 10 random built products against
their source pages (`source_page` per record) — confirm name/species matches the photo's origin
page. ANY name↔photo mismatch is a BUILD FAILURE to fix before reporting.

## Purpose-first reconstruction — binding
NEVER port or restyle source markup. For every content/UI block in the source, FIRST designate its
broad PURPOSE with a plain name (announcement banner, trust strip, category index, product card,
promo/offer, hours-or-policy notice, guarantee, testimonial, contact strip, newsletter capture…)
and RECORD it. THEN implement the best modern expression of that purpose using the component catalog
(or a new component): improving aesthetics and functionality is the EXPECTATION; fidelity to old
markup is explicitly NOT a goal. A block whose purpose can't be confidently designated is flagged
for the human, never copied. Components are NAMED BY PURPOSE (`AnnouncementBanner`, not `GreenStripe`).

## Build specs — binding build orders
Any `.md` in a client's `02-intake/specs/` is a BINDING build order. When assembling or finishing,
read every spec first and treat it as authoritative — it overrides general defaults, archetype
conventions, and playbook guidance on conflict. Specs never override the Hard rules; on conflict,
follow the Hard rule and flag it FOR REVIEW.

## Industry playbooks
When assembling or finishing, ALWAYS check `playbooks/` for a file matching the client's industry
(brief.yaml `industry:`, or inferred from baseline if blank — record the inference). If matched,
read and apply it to content drafting, schema, section choices, tone. If none, say so, use general
defaults, and suggest creating one from `playbooks/_TEMPLATE.md`.

## Command composition (work with the allowlist, not around it)
Bash permissions in `.claude/settings.local.json` match command PREFIXES, and a compound command
(`a && b`, `a; b`) is matched as a whole — a chain can slip a denied command past a deny rule, and a
`cd`-prefixed chain matches no allow pattern. Therefore:
- Run from the project root; address other dirs with tool-native flags, not `cd`:
  `git -C /Users/ericliu/web-studio <sub>`, `npm run build --prefix <dir>`, absolute paths for
  `cp`/`python3 .claude/skills/...`.
- Prefer SEPARATE simple commands over `&&`/`;` chains (run independent ones in parallel tool calls).
- Never reshape a command to evade a deny rule; if a needed command has no allow rule, say so and
  propose adding the rule.

## studio.py change protocol — binding (kill the stale-server bug class)
The dashboard is a long-lived `python3 studio.py` that loads the file ONCE at launch; a
parallel/older instance serving stale code is the recurring cause of "missing buttons, inaccessible
creative mode, reverting radios, broken upload." Any task that edits studio.py is NOT done until the
server is restarted onto new code AND the version stamp equals HEAD:
1. Restart with `./restart.sh` (kills the instance on the port, relaunches on current code). Do NOT
   hand-start a second `python3 studio.py` — the single-instance guard refuses a duplicate
   (`STUDIO_TAKEOVER=1` to take the port).
2. VERIFY the footer version stamp / `/api/clients` `version.head` equals
   `git rev-parse --short HEAD` and `version.stale` is false; else restart again.
3. The dashboard fires a non-dismissable staleness banner whenever on-disk studio.py differs from
   the loaded fingerprint. Never report a studio.py change done while that banner would show.

Render invariant — binding (the 4s poll must NEVER destroy in-flight UI state). The auto-refresh is
interaction-aware, not a wholesale `innerHTML` rebuild: each row is a data-only `.live` zone
(re-rendered every poll) plus a controls zone (stateful inputs, built once); a container the user is
touching (focus, a staged file, typed text, a flipped radio/checkbox, an open panel) is never
rebuilt, only its `.live` zone is patched (`load()`→`reconcileList()`/`interacting()`; same guard
protects `#needs`). Any NEW interactive element is auto-protected as long as it lives in the controls
zone (or is caught by `interacting()`). Do NOT reintroduce snapshot-and-restore patches or full-list
`innerHTML=` replacement. File inputs can't be value-restored (browser security), so skip-while-
staged is the only correct fix, which this guarantees.

## Decision surfaces — binding
Any capability requiring human JUDGMENT (mode changes, config confirmations, choices, approvals)
MUST ship with a dashboard control in the SAME commit. A decision point reachable only via terminal
or chat is INCOMPLETE. Mechanism: the decisions inbox (filename-is-state, like edits). When a
command/job hits a fork needing the human's call, it does NOT guess or die silently — it writes
`clients/<slug>/02-intake/decisions/NNN-OPEN-<short-name>.yaml` (studio-level: `.claude/decisions/`)
with question / context / options (each + consequence) / recommendation + reason / what-happens-next
per option. The dashboard renders OPEN decisions in a "Needs your call" strip; resolving one records
the choice + timestamp, renames OPEN→RESOLVED (immutable), logs to status.json, resumes any blocked job.

## Troubleshooting workflow — binding (diagnose THEN fix)
When the human reports something not working (any phrasing), do NOT start changing files. First
materialize an incident: `clients/<slug>/02-intake/incidents/NNN-OPEN-<short-name>.md` (studio-level
→ `.claude/incidents/`), from `templates/incident-template.md`. Filename IS the state (OPEN /
BLOCKED / RESOLVED). The six binding sections:
- SYMPTOM — the human's words VERBATIM + where observed (URL, screen, command).
- DIAGNOSTIC — evidence gathered BEFORE any fix; reproduce the failure FIRST (build output,
  status.json log, audit log, browser behavior, the failing request/route); state what was checked
  and what each check showed. No reproduction ⇒ say so + what's needed.
- ROOT CAUSE — ONE falsifiable sentence naming the actual cause, traced to evidence. "Probably X" is
  not a root cause — keep diagnosing, or state competing hypotheses + how the fix discriminates.
- FIX PLAN — smallest change addressing the root cause; every file to touch + why. Reimplementation
  is allowed when the diagnostic shows the implementation is unsound — say so, don't patch rot.
- VERIFICATION — re-run the reproduction (must pass) + re-run every parity-checklist row the touched
  files could disturb (the verification-loop rule applies).
- RESOLUTION — filled at close: what changed, commit(s), evidence the symptom is gone.
Execution: (1) client-site fixes implement THROUGH the edit convention (incident links its edit NNN);
studio-system fixes commit directly with the SYSTEM.md update — publish-always applies to site fixes.
(2) One root cause per incident; a second independent problem opens a SECOND incident. (3) If the fix
needs a missing fact/credential: incident → `NNN-BLOCKED-…` naming it + a decision card. (4) Rename
OPEN→RESOLVED ONLY after verification passes; RESOLVED is immutable. (5) RECURRENCE: a symptom
matching a RESOLVED incident reopens as a NEW incident referencing the old one, and the diagnostic
must explain why the previous fix didn't hold before any new fix lands. Dashboard: every row + the
header carry a "Report a problem" box that creates the OPEN incident and enqueues the diagnostic.

## Findings & reports — binding (a finding only in scrollback doesn't exist)
Any substantive finding/report (build/assemble reports, census summaries, verification-loop results,
Design QA audits, incident diagnostics/resolutions, correspondence audits, backend phase reports,
scrape coverage) is WRITTEN when produced as `clients/<slug>/02-intake/reports/<YYYY-MM-DD-HHMM>-
<kind>.md` (studio-level → `.claude/reports/`). Terminal output is the conversational copy; the FILE
is the record. Reports are append-only (a correction is a NEW report referencing the old). Artifacts
that are already the record (edit Resolution blocks, incident files, the parity checklist,
coverage.md) are LINKED, never duplicated. Every finding-producing flow ends with this write (advance
jobs, full-build chains, the incident workflow, the verification loop, the intake pack).

## Auto-approval audit
At the END of every task, read `.claude/audit/session.log` entries since the task began and emit a
mini report: total auto-approved actions grouped (file edits / shell commands / deploys) with
one-line summaries, FLAGGING anything outside the routine pattern (a deploy, a deletion, anything
touching paths outside the project). Then archive the log to `.claude/audit/<YYYY-MM-DD>-<task-slug>
.log` and start a fresh `session.log`. The log is appended by the PostToolUse hook;
`.claude/audit/` is git-ignored.

## Design ground rules — binding on every build and template
1. Named concept. ONE recorded sentence of art direction; every visual decision traces to it. No
   concept, no build.
2. Distinctiveness bar. Banned by default: generic template sameness (white bg + gray cards + blue
   accent), default system fonts, stock-gradient heroes, three-icon feature rows. Ship ONE memorable
   signature visual element.
3. Typography with intent. A characterful display face deliberately paired with a body face; bold
   scale contrast. Never default-sans-for-everything.
4. Imagery non-negotiables. (a) Resolve scraped images to LARGEST variants (detect thumbnail URL
   patterns, fetch originals, RECORD dimensions). (b) Never upscale or stretch; an image below the
   slot minimum (hero ≥1600px wide, card ≥600px) is REJECTED from that slot and a photography ask is
   added to the deliverables request. (c) One cropping/color treatment per site. (d) Heroes are
   full-bleed, single-subject, art-directed.
5. Motion. Subtle, purposeful microinteractions that serve the concept; always honor
   `prefers-reduced-motion`. No parallax circus.
6. DESIGN QA GATE. A build is NOT done until a recorded self-audit passes: names the concept + the
   signature element; zero banned patterns; every image meets its slot minimum, is unstretched and
   correspondence-correct; checked at desktop AND ~390px mobile; and honestly answers "would a
   visitor remember this tomorrow, and does it outclass the client's competitors?". Iterate before
   reporting. Append the audit to the build report (for an edit, to that edit's Resolution).
Pipeline support: image records carry `source_page`, pixel `dimensions`, and `largest_variant` URL;
builds consume that record, never raw thumbnail URLs.

## Verification loop — binding on Command 1 and any full-build chain
After assembling a prototype, do NOT report/publish on belief. Run the parity checklist
(`01-baseline/parity-checklist.md`): execute each row's verification method against the BUILT OUTPUT
(`dist/`, rendered routes), NEVER against intentions or remembered source. For every unmet row:
implement the fix, `npm run build`, re-verify THAT row and any row the fix could disturb. Iterate
until every row is `[x]` verified-with-evidence or `[B]` BLOCKED naming the exact missing client
fact / deliverable ID (BLOCKED is for genuinely ungated-on-us items only, never "didn't get to it").
HARD CAP: 5 iterations; if rows remain unmet, STOP, report the survivors honestly as failures with
your diagnosis, open a decision card — never loop forever, never quietly ship around them. Paste the
completed checklist (per-row evidence one-liners + iteration count) verbatim into the build report,
committed alongside the build. Publish-always runs only after the loop exits. Scope: the loop also
runs (relevant subset) after "Process edits" batches and at "Finish"; the full-rehearsal chain runs
it at assemble AND again after Phase 4 with backend rows (test checkout completes, admin CRUD works,
notify-email loop fires). A row without an executable verification method is invalid (fix the checklist).

## Baseline = the scrape ladder (resilient to bot-blocked sites)
`run_baseline.py` is an escalating cascade, not a fixed 3-method run: crawler → rendered browser
(Playwright, the anti-bot weapon) → wget mirror (breadth, only when content flows) → Wayback archive
(only when blocked; content is STALE, labelled `ARCHIVE-*`, never price/stock truth) → human (a
decision card with a ready-to-send owner-export note). Missing tools log LOUDLY and count as rung
failures, never a silent skip. `coverage.md` records each rung + which rungs the baseline rests on;
the census + tokens note evidence source LIVE vs ARCHIVE. See SYSTEM.md.

## Hard rules — always, regardless of skill loading
- NEVER fabricate a client fact. Blanks stay blank and get flagged FOR REVIEW.
- NEVER edit templates/ for a client; copy first.
- NEVER touch or advise changing MX/SPF/DKIM/DMARC records; flag email-affecting steps for the human.
- Redirects live at the host/CDN edge, never in page JavaScript.
- Staging builds keep noindex; only PUBLIC_INDEXABLE=true removes it (launch step zero, human-confirmed).
- Reuse the client's EXISTING GA4 property; issue NEW Turnstile/reCAPTCHA keys per rebuild.
- Scraped copy is DRAFT until owner answers or explicit human review confirm ownership (license risk).
- Images: PROTOTYPES MAY use images scraped from the client's OWN website (their material, shown
  back to them). At "Finish", every image must be client-supplied or have provenance confirmed via
  intake; any that isn't is flagged FOR REVIEW and replaced before launch. Never use third-party/
  stock imagery scraped from elsewhere.
- All colors/fonts via @theme tokens; no literal hex in components.
