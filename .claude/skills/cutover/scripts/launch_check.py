#!/usr/bin/env python3
"""Launch checker. Usage: python3 launch_check.py <url> [--production]
Staging mode (default): noindex MUST be present. Production: MUST be absent."""
import re, sys
import requests

def main():
    url = sys.argv[1]
    prod = "--production" in sys.argv
    if not url.startswith("http"):
        url = "https://" + url
    base = url.rstrip("/")
    ok = True
    def check(name, passed, detail=""):
        nonlocal ok
        ok = ok and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    try:
        r = requests.get(base, timeout=20)
    except Exception as e:
        print(f"[FAIL] site unreachable: {str(e)[:140]}")
        sys.exit(1)
    html = r.text
    noindex = bool(re.search(r'<meta[^>]+robots[^>]+noindex', html, re.I))
    if prod:
        check("noindex ABSENT (production)", not noindex, "site is telling Google not to index it!" if noindex else "")
    else:
        check("noindex PRESENT (staging)", noindex, "staging is exposed to indexing" if not noindex else "")
    rb = requests.get(base + "/robots.txt", timeout=10)
    blocking = bool(re.search(r"^disallow:\s*/\s*$", rb.text, re.I | re.M))
    if prod:
        check("robots.txt not blocking all", not blocking)
    else:
        print(f"[info] robots.txt status {rb.status_code}")
    check("canonical tag present", '<link rel="canonical"' in html or "rel='canonical'" in html)
    check("title present", bool(re.search(r"<title>[^<]{3,}</title>", html)))
    check("meta description present", bool(re.search(r'<meta[^>]+name=["\']description', html, re.I)))
    check("OG tags present", 'property="og:' in html or "property='og:" in html)
    check("JSON-LD present", "application/ld+json" in html)
    r404 = requests.get(base + "/zz-definitely-not-a-page-zz", timeout=10)
    check("custom 404 responds with 404 status", r404.status_code == 404, f"got {r404.status_code}")
    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "FAILURES PRESENT — do not proceed")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
