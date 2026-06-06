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
1. Read 01-baseline/ in full (inventory, drafts, audits, coverage, feature-census).
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
9. Generate `02-intake/deliverables-request.md` from `templates/deliverables-template.md` by
   FILTERING AND SPECIALIZING: keep only rows relevant to this archetype, the detected stack,
   and the spec's phases; drop the rest. SPECIALIZE from evidence — name the detected GA4 ID,
   reference detected forms by their page, name the detected CMS/CDN. §2.1 and §2.2 are ALWAYS
   BLOCKING and always kept. Populate §2.7 from any binding spec's "client facts required".
   Append an "Omitted as not applicable" list, one line + reason per dropped row, so every
   omission is auditable. (See "Process deliverables" below — this file then lives and updates.)
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
