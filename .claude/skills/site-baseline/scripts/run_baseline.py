#!/usr/bin/env python3
"""Pipeline runner: domain -> 00-source scrapes (3 methods) -> 01-baseline extracts.
Called by studio.py in the background; also runnable by hand:
    python3 run_baseline.py https://example.com clients/<slug>
Updates <client>/status.json as it progresses."""
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

def bump(client, stage=None, msg=None):
    sp = client / "status.json"
    st = json.loads(sp.read_text()) if sp.exists() else {"log": []}
    if stage:
        st["stage"] = stage
    if msg:
        st.setdefault("log", []).append(f"{now()} {msg}")
    sp.write_text(json.dumps(st, indent=2))

def run(cmd, client, label):
    bump(client, msg=f"{label} started")
    p = subprocess.run(cmd, capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
    bump(client, msg=f"{label}: {tail[0][:160]}")
    return p.returncode

def main():
    domain, client = sys.argv[1], Path(sys.argv[2]).resolve()
    py = sys.executable
    bump(client, stage="scraping", msg=f"baseline pipeline started for {domain}")
    try:
        rc = run([py, str(HERE / "crawl.py"), domain,
                  str(client / "00-source" / "crawl.json"), "150"], client, "crawl (method 1)")
        if rc != 0 or not (client / "00-source" / "crawl.json").exists():
            bump(client, stage="error", msg="crawl failed — cannot continue")
            return
        run(["bash", str(HERE / "mirror.sh"), domain, str(client)], client, "mirror (method 3)")
        run([py, str(HERE / "render_capture.py"), str(client)], client, "render (method 2)")
        run([py, str(HERE / "extract.py"), str(client)], client, "extract baseline")
        run([py, str(HERE / "perf.py"), domain, str(client)], client, "performance baseline")
        bump(client, stage="baseline-ready",
             msg='baseline ready — next: claude -> "Assemble prototype for <slug>"')
    except Exception as e:
        bump(client, stage="error", msg=f"pipeline exception: {str(e)[:200]}")

if __name__ == "__main__":
    main()
