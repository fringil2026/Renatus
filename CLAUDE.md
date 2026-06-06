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
1. Read 01-baseline/ in full (inventory, drafts, audits, coverage).
2. Copy the matching archetype from templates/ into 03-site/ (`cp -R`, never build in templates/).
3. Apply 01-baseline/tokens-draft.json to the @theme block; mirror to 03-site/tokens.json.
4. Map content-draft.md into the data slots; everything is marked DRAFT (it is scraped, unverified).
5. Seed 02-intake/brief.yaml with every fact the baseline established (domain, detected
   GA4/CMS from tech-fingerprint.md) — leave unknown fields blank, never guessed.
6. Seed 02-intake/redirect-map.csv from url-inventory.csv (old URL column filled, new column proposed).
7. `npm install && npm run build` in 03-site/ to verify; fix failures.
8. Set stage=prototype, then awaiting-owner. Report: what was applied, what is DRAFT, what is blank.

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

## Command 6 — "Publish preview for <slug>"
Deploy the current `03-site` build as a PRIVATE preview for owner review.
1. Build with noindex ON — previews NEVER get `PUBLIC_INDEXABLE` (so `npm run build`,
   never the production flag). The staging noindex meta must be present in the output.
2. Deploy `03-site/dist/` to Cloudflare Pages via wrangler as project `ws-<slug>`:
   `wrangler pages deploy 03-site/dist --project-name ws-<slug>`.
3. Report the public `*.pages.dev` URL.
First run only: wrangler isn't set up. Do NOT fail — walk the human through the one-time
setup (`npm i -g wrangler` then `wrangler login`, which opens a browser), then continue.
This is a preview, not a launch: no DNS, no custom domain, no MX/email changes.

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

## Auto-approval audit
At the END of every task, read the `.claude/audit/session.log` entries written since the
task began and emit a mini report: the total count of auto-approved actions, grouped (file
edits / shell commands / deploys) with one-line summaries, and FLAG anything outside the
routine pattern (a deploy, a deletion, anything touching paths outside the project). Then
archive the log to `.claude/audit/<YYYY-MM-DD>-<task-slug>.log` and start a fresh
`session.log`. The log is appended automatically by the PostToolUse hook in
`.claude/settings.local.json`; `.claude/audit/` is git-ignored.

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
