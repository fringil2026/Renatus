#!/usr/bin/env python3
"""Pipeline runner: domain -> 00-source scrapes (3 methods) -> 01-baseline extracts.
Called by studio.py in the background; also runnable by hand:
    python3 run_baseline.py https://example.com clients/<slug>
Updates <client>/status.json as it progresses."""
import json, re, signal, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

def kill_stray_wget(client):
    """Kill any wget still mirroring THIS client — a leftover from an interrupted
    or prior run. Scoped to the client's mirror dir (via wget's -P target) so a
    concurrent scrape of a DIFFERENT client is never touched."""
    mirror = str((client / "00-source" / "mirror").resolve())
    try:
        subprocess.run(["pkill", "-9", "-f", f"wget.*{re.escape(mirror)}"],
                       capture_output=True)
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

def run(cmd, client, label):
    bump(client, msg=f"{label} started")
    p = subprocess.run(cmd, capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
    bump(client, msg=f"{label}: {tail[0][:160]}")
    return p.returncode

def main():
    domain, client = sys.argv[1], Path(sys.argv[2]).resolve()
    py = sys.executable

    def _on_signal(signum, _frame):
        kill_stray_wget(client)   # interrupted mid-scrape — don't orphan wget
        bump(client, stage="error", msg=f"interrupted (signal {signum}) — killed stray wget")
        sys.exit(1)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    kill_stray_wget(client)   # rerun safety: clear any wget left over from a prior run
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
        run([py, str(HERE / "feature_census.py"), str(client)], client, "feature census")
        run([py, str(HERE / "perf.py"), domain, str(client)], client, "performance baseline")
        bump(client, stage="baseline-ready",
             msg='baseline ready — next: claude -> "Assemble prototype for <slug>"')
    except Exception as e:
        kill_stray_wget(client)   # leave no orphaned wget behind on failure
        bump(client, stage="error", msg=f"pipeline exception: {str(e)[:200]}")

if __name__ == "__main__":
    main()
