# CONTEXT.md — Full System Background
Read this when deeper context than CLAUDE.md is needed: new session on unfamiliar work,
architectural changes, building new templates/skills, or when the human references
concepts not defined in CLAUDE.md.

## The business
A website-rebuild service. The operator (the human) handles outreach and client
relationships; this studio automates everything technical. The entire build collapses
to two human inputs per client: (1) the domain — typed into the dashboard, which
triggers a three-method scrape and leads to a prototype; (2) the owner's discovery
questionnaire answers — pasted into the dashboard, which leads to the finished site
and cutover preparation. Everything between those inputs is scripts plus Claude Code.

## The component map
- **studio.py** — dashboard server (the human surface): new-client intake, live status
  from each client's status.json, owner-answer paste box, archive button, rerun.
  Concurrent scrapes up to MAX_SCRAPES with an auto-promoting queue. Token auth;
  tunnel.sh exposes it publicly and temporarily via a Cloudflare quick tunnel.
- **.claude/skills/site-baseline/** — discovery automation. Three independent scrape
  methods (HTTP crawler / headless Chromium render / wget mirror) cross-validated in
  coverage.md. Outputs the 01-baseline deliverables that seed both the prototype and
  the intake.
- **.claude/skills/apply-intake/** — turns owner answers + intake files into the final
  build. Answer statuses drive behavior: answered=truth, UNSURE+permission=resolve
  technically with evidence, DELEGATED/SKIPPED=FOR-REVIEW list. Never guess.
- **.claude/skills/cutover/** — launch verification with deterministic scripts:
  launch_check.py (noindex/robots/canonical/schema/OG/404), redirect_check.py
  (single-hop 301s, chain and blanket-to-home detection), zone_diff.py (DNS diff that
  ERRORs on lost MX/SPF/DKIM/DMARC).
- **templates/nerc-cip-base/** — first base archetype: B2B professional services,
  NERC-CIP managed compliance. Astro 5 + Tailwind 4, static output. Its own CLAUDE.md
  holds the component catalog (the shared vocabulary of blocks and variants).
- **templates/intake-template/ + INTAKE.md** — the per-client input framework:
  brief.yaml (required facts + build directives), tokens.json (look), content.md
  (words), redirect-map.csv, assets/, reference/.

## External deliverables that pair with this repo
- The **owner discovery questionnaire** (self-contained HTML the operator sends to
  clients): 22 questions, each with three exits — answered / not sure / someone else
  handles it. "Not sure" captures who-might-know + permission to investigate. Its
  generated summary is exactly what gets pasted into the dashboard as owner-answers.txt.
- The **Discovery & Cutover handbook** and the **operating workflow document** — the
  human-readable doctrine this studio encodes. When in doubt about WHY a rule exists
  (redirect one-hop, noindex step zero, email-DNS untouchability), the reasoning lives there.

## Design decisions already made (do not relitigate casually)
- **Astro + Tailwind, static output**: fast builds for agent verification, file-based
  routing, near-free CDN hosting, no server runtime. Next.js rejected as overkill.
- **Archetypes × tokens × content slots**: visual diversity comes from structurally
  different base templates; per-client customization is a token layer + section
  variants + data slots — never hand-edited component internals.
- **Three scrape methods**: any single method misses things (JS rendering, blocked
  crawlers, redirect quirks). Coverage diffing converts "missed" into a visible flag.
- **Skill vs guardrail split**: procedures+scripts live in skills (loaded on
  relevance); inviolable rules live in CLAUDE.md (always loaded). A rule that might
  not load is not a guardrail.
- **Two-folder truth model**: 00-source/01-baseline are machine-derived and DRAFT;
  02-intake is human/owner truth and always wins on conflict.

## Glossary
master / base archetype — the pristine template folder in templates/; copied per
client, never customized in place. · baseline — the automated discovery extraction
(Phase 1 of the doctrine). · intake — the per-client input folder/framework. ·
prototype — template + scraped DRAFTs, built before owner input. · cutover — DNS
switch + launch verification. · archive — archive/<slug>-<timestamp>/, one read-only
folder per finished project; the only removal path for client work.

## Operator profile
Python-comfortable, frontend-new; prefers conversation-driven changes over hand-editing
code. Use the component-catalog vocabulary in reports. Surface FOR-REVIEW lists
prominently; keep explanations concrete and command-level.
