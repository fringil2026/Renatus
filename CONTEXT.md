# CONTEXT.md — Full System Background
Read this for deeper context than CLAUDE.md: new session on unfamiliar work, architectural changes,
building new templates/skills, or when the human references concepts not defined in CLAUDE.md.

## The business
A website-rebuild service. The operator handles outreach and client relationships; this studio
automates everything technical. The build collapses to two human inputs per client: (1) the domain —
typed into the dashboard, triggering the scrape ladder → a prototype; (2) the owner's discovery
questionnaire answers — pasted in, leading to the finished site and cutover prep. Everything between
is scripts plus Claude Code.

## The component map
- **studio.py** — dashboard server (the human surface): new-client intake, live status from each
  status.json, owner-answer paste box, archive/rerun. Concurrent scrapes up to MAX_SCRAPES with an
  auto-promoting queue. Token auth; `tunnel.sh` exposes it publicly+temporarily via a Cloudflare quick
  tunnel.
- **.claude/skills/site-baseline/** — discovery automation (the scrape ladder, SYSTEM.md §1),
  cross-validated in coverage.md. Outputs the 01-baseline deliverables that seed prototype + intake.
- **.claude/skills/apply-intake/** — owner answers + intake files → final build. Answer statuses drive
  behavior: answered=truth, UNSURE+permission=resolve technically with evidence, DELEGATED/SKIPPED=
  FOR-REVIEW. Never guess.
- **.claude/skills/cutover/** — launch verification: launch_check.py (noindex/robots/canonical/schema/
  OG/404), redirect_check.py (single-hop 301s, chain + blanket-to-home detection), zone_diff.py (DNS
  diff that ERRORs on lost MX/SPF/DKIM/DMARC).
- **.claude/skills/site-diagnostic/** — outreach rebuild-verdict engine (SYSTEM.md §7).
- **templates/** — base archetypes (Astro 5 + Tailwind 4, static output), each with its own component
  catalog. Copied per client, never customized in place. `intake-template/` + INTAKE.md is the
  per-client input framework (brief.yaml, tokens.json, content.md, redirect-map.csv, assets/).

## External deliverables that pair with this repo
- The **owner discovery questionnaire** (self-contained HTML the operator sends): 22 questions, each
  with three exits — answered / not sure (captures who-might-know + permission to investigate) /
  someone else handles it. Its generated summary is what gets pasted as owner-answers.txt.
- The **Discovery & Cutover handbook** + the **operating workflow doc** — the human-readable doctrine
  this studio encodes; the WHY behind rules (redirect one-hop, noindex step zero, email-DNS
  untouchability).

## Design decisions already made (do not relitigate casually)
- **Astro + Tailwind, static output:** fast builds for agent verification, file-based routing,
  near-free CDN hosting, no server runtime. Next.js rejected as overkill.
- **Archetypes × tokens × content slots:** visual diversity comes from structurally different base
  templates; per-client customization is a token layer + section variants + data slots — never
  hand-edited component internals.
- **The scrape ladder (multi-rung):** any single method misses things (JS rendering, blocked crawlers,
  redirect quirks); coverage diffing converts "missed" into a visible flag.
- **Skill vs guardrail split:** procedures+scripts live in skills (loaded on relevance); inviolable
  rules live in CLAUDE.md (always loaded). A rule that might not load is not a guardrail.
- **Two-folder truth model:** 00-source/01-baseline are machine-derived and DRAFT; 02-intake is
  human/owner truth and always wins on conflict.

## Glossary
master / base archetype — the pristine template in templates/; copied per client, never customized in
place. · baseline — the automated discovery extraction. · intake — the per-client input
folder/framework. · prototype — template + scraped DRAFTs, built before owner input. · cutover — DNS
switch + launch verification. · archive — `archive/<slug>-<timestamp>/`, one read-only folder per
finished project; the only removal path.

## Operator profile
Python-comfortable, frontend-new; prefers conversation-driven changes over hand-editing code. Use the
component-catalog vocabulary in reports. Surface FOR-REVIEW lists prominently; keep explanations
concrete and command-level.
