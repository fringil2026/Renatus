#!/usr/bin/env python3
"""Performance baseline via PageSpeed Insights API (no key needed at low volume).
Usage: python3 perf.py https://example.com <client_dir>   — degrades gracefully."""
import json, sys
from pathlib import Path
import requests

def score(url, strategy):
    api = ("https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
           f"?url={url}&strategy={strategy}&category=performance&category=seo&category=accessibility")
    r = requests.get(api, timeout=120)
    r.raise_for_status()
    cats = r.json()["lighthouseResult"]["categories"]
    return {k: round(v["score"] * 100) for k, v in cats.items()}

def main():
    url, client = sys.argv[1], Path(sys.argv[2])
    out = client / "01-baseline" / "perf-baseline.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    L = [f"# Performance Baseline — {url}", ""]
    try:
        for strat in ("mobile", "desktop"):
            s = score(url if url.startswith("http") else "https://" + url, strat)
            L.append(f"{strat}: " + "  ".join(f"{k} {v}" for k, v in s.items()))
        L += ["", "These are the BEFORE numbers — quote them in the pitch and re-run after launch."]
    except Exception as e:
        L += [f"PageSpeed API unavailable ({str(e)[:120]}).",
              "Fallback: run `npx lighthouse <url>` locally or use pagespeed.web.dev manually."]
    out.write_text("\n".join(L))
    print(f"perf -> {out}")

if __name__ == "__main__":
    main()
