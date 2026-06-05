#!/usr/bin/env python3
"""Redirect map validator. Usage: python3 redirect_check.py <map.csv> <base_url>
CSV columns: old_path,new_path. Verifies single-hop 301s to the mapped target."""
import csv, sys
from urllib.parse import urlparse
import requests

def main():
    path, base = sys.argv[1], sys.argv[2].rstrip("/")
    fails = chains = 0
    rows = list(csv.DictReader(open(path)))
    home_hits = 0
    for row in rows:
        old, new = row["old_path"].strip(), row["new_path"].strip()
        url, hops = base + old, 0
        try:
            while hops < 6:
                r = requests.get(url, allow_redirects=False, timeout=15)
                if r.status_code in (301, 302, 308):
                    hops += 1
                    url = r.headers.get("Location", "")
                    if url.startswith("/"):
                        url = base + url
                else:
                    break
        except Exception as e:
            print(f"[FAIL] {old}: request error {str(e)[:80]}")
            fails += 1
            continue
        landed = urlparse(url).path or "/"
        want = new if new.startswith("/") else urlparse(new).path
        if hops == 0:
            print(f"[FAIL] {old}: no redirect (status {r.status_code})"); fails += 1
        elif hops > 1:
            print(f"[FAIL] {old}: {hops} hops (chain) -> {landed}"); fails += 1; chains += 1
        elif landed.rstrip("/") != want.rstrip("/").split("#")[0]:
            print(f"[FAIL] {old}: lands on {landed}, expected {want}"); fails += 1
        if landed == "/" and want.rstrip("/") not in ("", "/"):
            home_hits += 1
    if home_hits > max(2, len(rows) // 3):
        print(f"[WARN] {home_hits} old URLs land on the homepage — looks like a blanket redirect (soft-404 risk)")
    print(f"\n{len(rows)-fails}/{len(rows)} OK · {chains} chains · RESULT:",
          "PASS" if fails == 0 else "FAIL")
    sys.exit(0 if fails == 0 else 1)

if __name__ == "__main__":
    main()
