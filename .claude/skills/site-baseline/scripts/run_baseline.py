#!/usr/bin/env python3
"""Scrape LADDER — an escalating cascade resilient to bot-blocked sites.
    python3 run_baseline.py https://example.com clients/<slug>

Rungs (each fallback rung runs only when the live rungs captured insufficient content):
  1 crawler (requests)      — fast, polite, identified UA. Block detection: 5xx/403 on homepage
                              OR a Cloudflare challenge marker (/cdn-cgi/challenge-platform/).
  2 rendered browser (PW)   — the primary anti-bot weapon: real Chromium, human-pace navigation.
  3 wget mirror             — breadth tool; runs ONLY when rungs 1–2 are getting content.
  4 archive_fetch (Wayback) — runs ONLY when live rungs are blocked. Content is STALE (ARCHIVE-*).
  5 human                   — if all rungs insufficient: open a decision card with a ready-to-send
                              owner-export note.
Missing tools (wget, Playwright) LOG LOUDLY and count as rung failures — never a silent skip.
Politeness is law: identified UA, generous delays, bounded retries; two failed unblock attempts
means move DOWN the ladder, not try harder. Writes coverage.md + 00-source/evidence-source.txt.
"""
import json, re, shutil, signal, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHALLENGE = "/cdn-cgi/challenge-platform/"

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

def kill_stray_wget(client):
    mirror = str((client / "00-source" / "mirror").resolve())
    try:
        subprocess.run(["pkill", "-9", "-f", f"wget.*{re.escape(mirror)}"], capture_output=True)
    except Exception:
        pass

def bump(client, stage=None, msg=None):
    sp = client / "status.json"
    st = json.loads(sp.read_text()) if sp.exists() else {"log": []}
    if stage:
        st["stage"] = stage
    if msg:
        st.setdefault("log", []).append(f"{now()} {msg}")
    sp.write_text(json.dumps(st, indent=2))

def run(cmd, client, label, env=None):
    bump(client, msg=f"{label} started")
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
    bump(client, msg=f"{label}: {tail[0][:160]}")
    return p.returncode, tail[0]

def playwright_ready():
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False

def crawl_assessment(client):
    """Return (pages_with_text, blocked, reason). The Cloudflare challenge SCRIPT
    (/cdn-cgi/challenge-platform/) ships inside NORMAL 200 pages, so its presence ALONE is NOT a
    block (incident WS-INC-SEATTLE-ORCHIDS-001). Treat as blocked only on an actual failure —
    homepage 4xx/5xx — OR a challenge marker WITH little real content (a true interstitial)."""
    f = client / "00-source" / "crawl.json"
    if not f.exists():
        return 0, True, "crawl.json missing"
    raw = f.read_text(errors="ignore")
    try:
        data = json.loads(raw)
    except Exception:
        return 0, True, "crawl.json unparseable"
    pages = data.get("pages", [])
    pwt = sum(1 for p in pages if len((p.get("text") or "")) > 200)
    bad_status = any(isinstance(v, dict) and v.get("status") in (403, 500, 502, 503, 429)
                     for k, v in (data.get("extras", {}) or {}).items() if k in ("/", ""))
    challenge_wall = (CHALLENGE in raw) and pwt < 3   # marker AND no real content = real interstitial
    blocked = bad_status or challenge_wall
    reason = ("homepage 4xx/5xx" if bad_status else
              "challenge interstitial (no content)" if challenge_wall else
              "low page yield" if pwt < 3 else "")
    return pwt, blocked, reason

def rendered_count(client):
    """render_capture writes one <page>-desktop.png per captured page (+ render.json), NOT HTML
    (incident WS-INC-SEATTLE-ORCHIDS-001 — counting *.html always returned 0)."""
    d = client / "00-source" / "rendered"
    if not d.exists():
        return 0
    n = len(list(d.glob("*-desktop.png")))
    if n:
        return n
    rj = d / "render.json"
    if rj.exists():
        try:
            data = json.loads(rj.read_text())
            return len(data) if isinstance(data, list) else len(data.get("pages", []))
        except Exception:
            return 0
    return len(list(d.rglob("*.png")))

def write_decision_owner_export(client, domain):
    dd = client / "02-intake" / "decisions"
    dd.mkdir(parents=True, exist_ok=True)
    n = len(list(dd.glob("*.yaml"))) + 1
    f = dd / f"{n:03d}-OPEN-owner-export-needed.yaml"
    note = (f"Hi! To rebuild {domain} we need a quick export from your store admin — about ten "
            "minutes. If you're on Shopify: Products → Export → CSV (all products); Online Store → "
            "Themes → Actions → Download theme; and please save 3–4 key pages as PDF (home, about, "
            "shipping). Email those over and we'll take it from there. Thank you!")
    f.write_text(
        'question: "Site is bot-blocked — request an export from the owner?"\n'
        "recommendation: send-owner-note\n"
        'reason: "all automated rungs (crawl, render, wget, Wayback) yielded insufficient LIVE content"\n'
        "context:\n"
        f'  - "{domain} blocks automated access (Cloudflare challenge / 5xx)."\n'
        '  - "Archive (Wayback) content, if any, is STALE — usable for design/copy/census, not price/stock."\n'
        "options:\n"
        "  - id: send-owner-note\n"
        '    label: "Send the owner the export request"\n'
        '    consequence: "Owner spends ~10 min; we rebuild from their real, current data."\n'
        '    next: "Paste the note below to the owner; on receipt, import the CSV + theme."\n'
        "  - id: proceed-archive\n"
        '    label: "Proceed on archive evidence only"\n'
        '    consequence: "Build drafts from stale snapshots; prices/stock flagged unverified."\n'
        '    next: "Continue with ARCHIVE-labelled drafts; owner confirms facts later."\n'
        "ready_to_send_note: |\n"
        f"  {note}\n"
    )
    bump(client, msg=f"decision OPENED: {f.name} (ready-to-send owner-export note included)")

def write_coverage(client, rungs, rests_on, evidence_source):
    L = ["# Coverage — scrape ladder", "", f"Evidence source: **{evidence_source}**", "",
         "| Rung | Method | Attempted | Result |", "|---|---|---|---|"]
    for r in rungs:
        L.append(f"| {r['n']} | {r['method']} | {r['attempted']} | {r['result']} |")
    L += ["", f"**Final baseline rests on:** {', '.join(rests_on) or 'NONE (human rung)'}.", "",
          "ARCHIVE evidence is stale — usable for design tokens, copy drafts, and feature census; "
          "NEVER as current price/stock truth."]
    (client / "01-baseline").mkdir(parents=True, exist_ok=True)
    (client / "01-baseline" / "coverage.md").write_text("\n".join(L) + "\n")

def main():
    domain, client = sys.argv[1], Path(sys.argv[2]).resolve()
    py = sys.executable
    rungs, rests_on = [], []

    def _on_signal(signum, _frame):
        kill_stray_wget(client)
        bump(client, stage="error", msg=f"interrupted (signal {signum}) — killed stray wget")
        sys.exit(1)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    kill_stray_wget(client)
    bump(client, stage="scraping", msg=f"LADDER started for {domain}")
    try:
        # ---- Rung 1: crawler ----
        run([py, str(HERE / "crawl.py"), domain, str(client / "00-source" / "crawl.json"), "150"],
            client, "rung1 crawl")
        pwt, blocked, reason = crawl_assessment(client)
        crawl_ok = pwt >= 3 and not blocked
        rungs.append({"n": 1, "method": "crawler (requests)", "attempted": "yes",
                      "result": f"{pwt} pages w/ text" + (f"; BLOCKED ({reason})" if blocked else "; ok")})
        if crawl_ok:
            rests_on.append("crawl")
        else:
            bump(client, msg=f"⚠ RUNG 1 insufficient ({reason or 'low yield'}) — escalating to rendered browser")

        # ---- Rung 2: rendered browser (Playwright) — primary anti-bot capture ----
        if playwright_ready():
            run([py, str(HERE / "render_capture.py"), str(client)], client, "rung2 render (Playwright)")
            rc = rendered_count(client)
            render_ok = rc >= 3
            rungs.append({"n": 2, "method": "rendered browser (Chromium)", "attempted": "yes",
                          "result": f"{rc} rendered pages" + ("" if render_ok else " (insufficient)")})
            if render_ok:
                rests_on.append("render")
        else:
            render_ok = False
            rungs.append({"n": 2, "method": "rendered browser (Chromium)", "attempted": "NO",
                          "result": "FAILED — Playwright not installed (pip install playwright && playwright install chromium)"})
            bump(client, msg="‼ RUNG 2 FAILED LOUDLY: Playwright missing — install it; not a silent skip")

        live_sufficient = crawl_ok or render_ok

        # ---- Rung 3: wget mirror — breadth, only when getting content ----
        if live_sufficient:
            if shutil.which("wget"):
                run(["bash", str(HERE / "mirror.sh"), domain, str(client)], client, "rung3 wget mirror")
                mc = len(list((client / "00-source" / "mirror").rglob("*.html"))) if (client / "00-source" / "mirror").exists() else 0
                rungs.append({"n": 3, "method": "wget mirror", "attempted": "yes", "result": f"{mc} html files"})
                if mc > 0:
                    rests_on.append("mirror")
            else:
                rungs.append({"n": 3, "method": "wget mirror", "attempted": "NO",
                              "result": "FAILED — wget not installed"})
                bump(client, msg="‼ RUNG 3 FAILED LOUDLY: wget missing — not a silent skip")
        else:
            rungs.append({"n": 3, "method": "wget mirror", "attempted": "skipped",
                          "result": "skipped — breadth tool, not an unblocker (live rungs blocked)"})

        # ---- Rung 4: Wayback archive — only when blocked ----
        archive_ok = False
        if not live_sufficient:
            run([py, str(HERE / "archive_fetch.py"), str(client), "25"], client, "rung4 archive (Wayback)")
            man = client / "00-source" / "archive" / "MANIFEST.json"
            if man.exists():
                try:
                    saved = sum(1 for m in json.loads(man.read_text()).get("captured", []) if m.get("file"))
                except Exception:
                    saved = 0
                archive_ok = saved > 0
                rungs.append({"n": 4, "method": "Wayback archive", "attempted": "yes",
                              "result": f"{saved} snapshots (STALE)"})
                if archive_ok:
                    rests_on.append("archive (STALE)")
            else:
                rungs.append({"n": 4, "method": "Wayback archive", "attempted": "yes", "result": "no snapshots"})
        else:
            rungs.append({"n": 4, "method": "Wayback archive", "attempted": "skipped",
                          "result": "skipped — live content sufficient"})

        # ---- Rung 5: human ----
        if not live_sufficient:
            write_decision_owner_export(client, domain)
            rungs.append({"n": 5, "method": "human (owner export)", "attempted": "yes",
                          "result": "decision card opened with ready-to-send note"})

        evidence_source = "LIVE" if live_sufficient else ("ARCHIVE" if archive_ok else "NONE")
        (client / "00-source").mkdir(parents=True, exist_ok=True)
        (client / "00-source" / "evidence-source.txt").write_text(evidence_source + "\n")

        # ---- Platform catalog enumeration (Volusion exposes the catalog only via /sitemap.xml,
        #      not via category-link following — WS-INC-SEATTLE-ORCHIDS-002) ----
        cj = client / "00-source" / "crawl.json"
        platform = ""
        if cj.exists():
            low = cj.read_text(errors="ignore").lower()
            if "volusion" in low or "/v/vspfiles/" in low:
                platform = "volusion"
        if platform == "volusion" and live_sufficient:
            run([py, str(HERE / "scrape_volusion.py"), str(client)], client, "volusion catalog (sitemap enum)")

        # ---- Extracts (feed on whatever rungs captured) ----
        run([py, str(HERE / "extract.py"), str(client)], client, "extract baseline")
        run([py, str(HERE / "feature_census.py"), str(client)], client, "feature census")
        run([py, str(HERE / "perf.py"), domain, str(client)], client, "performance baseline")
        write_coverage(client, rungs, rests_on, evidence_source)

        if live_sufficient or archive_ok:
            bump(client, stage="baseline-ready",
                 msg=f'baseline ready ({evidence_source}) — rests on {", ".join(rests_on)}; next: "Assemble prototype"')
        else:
            bump(client, stage="baseline-ready",
                 msg="⚠ baseline INSUFFICIENT — all rungs blocked; owner-export decision opened (human rung)")
    except Exception as e:
        kill_stray_wget(client)
        bump(client, stage="error", msg=f"ladder exception: {str(e)[:200]}")

if __name__ == "__main__":
    main()
