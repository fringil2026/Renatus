# Web Studio — two-human-step website rebuild pipeline

The entire rebuild collapses to two human actions:
1. **Type a domain** into the dashboard → automated scraping (3 methods) + baseline extraction + a prototype assembled from your base template.
2. **Paste the owner's questionnaire answers** → final site, redirect map, cutover prechecks.

## One-time setup
    pip install requests beautifulsoup4        # crawler deps
    pip install playwright && playwright install chromium   # optional: method-2 scraper (screenshots, JS rendering)
    # wget is method 3 — preinstalled on macOS/Linux

## Run it
    python3 studio.py            # local dashboard at http://localhost:8788
    ./tunnel.sh                  # OR: temporary PUBLIC dashboard (trycloudflare.com URL
                                 #     + access token; dies on Ctrl+C). Needs cloudflared.
    claude                       # in this folder, in a second terminal

Concurrency: multiple clients scrape in parallel (MAX_SCRAPES env, default 3);
extras queue automatically and start as slots free.
Lifecycle: when a project is done, hit ARCHIVE on its row — the client moves to
archive/<slug>-<timestamp>/ (a fresh folder per finished project) and the row
clears for the next build. Auth: set STUDIO_TOKEN (tunnel.sh auto-generates one);
open the dashboard as /?key=<token> once and a cookie keeps you in.

Dashboard = the two human inputs + live status. Claude Code = the assembly engine.
The root CLAUDE.md teaches Claude the whole pipeline; .claude/skills/ hold the
scraping, intake, and cutover procedures with their scripts.

## Map
    studio.py                  dashboard UI: concurrent scrapes + queue, auth, archive
    tunnel.sh                  temporary public access (Cloudflare quick tunnel + token)
    CLAUDE.md                  pipeline orchestrator for Claude Code
    templates/                 master base templates (never customized in place)
    .claude/skills/
      site-baseline/           3-method scraper + extractors → baseline files
      apply-intake/            owner answers + intake → finished site
      cutover/                 launch checks, redirect validation, zone diff
    archive/<slug>-<timestamp>/   finished projects (one folder per completed build)
    clients/<slug>/
      00-source/               raw scrapes (crawl.json, mirror/, rendered/)
      01-baseline/             url-inventory.csv, content-draft.md, tokens-draft.json,
                               metadata-audit.md, tech-fingerprint.md, coverage.md, perf-baseline.md
      02-intake/               brief.yaml, owner-answers.txt, assets/, redirect-map.csv
      03-site/                 the client's Astro project (copy of a template, customized)
      04-cutover/              runbook, zone snapshots, check reports
      status.json              stage tracker the dashboard reads
