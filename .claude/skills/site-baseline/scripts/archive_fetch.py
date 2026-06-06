#!/usr/bin/env python3
"""Rung 4 of the scrape ladder — Wayback Machine fallback for bot-blocked sites.
Pulls the most recent web.archive.org snapshots (HTTP 200) of the homepage + known URLs
(crawl.json discoveries + sitemap locs), via polite Python requests. Saves raw snapshot HTML to
00-source/archive/ and writes archive/MANIFEST.json with the snapshot date per URL.

ARCHIVE evidence may be STALE — usable for design tokens, copy drafts, and the feature census,
NEVER as current price/stock truth. Everything it captures is labelled ARCHIVE-<snapshot-date>.

Politeness is law: identified UA, 1.5s between requests, 2 retries max, bounded URL count.
Usage: python3 archive_fetch.py <client_dir> [max_urls]
"""
import json, re, ssl, sys, time, urllib.parse, urllib.request
from pathlib import Path

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()
UA = "StudioBaseline/1.0 (+baseline archival fallback; polite)"
CDX = "http://web.archive.org/cdx/search/cdx"


def get(url, timeout=25):
    for attempt in range(2):  # bounded retries — never an arms race
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.status, r.read()
        except Exception:
            time.sleep(1.5)
    return None, None


def latest_snapshot(url):
    """Most recent 200 snapshot of url -> (timestamp, original) or None."""
    q = urllib.parse.urlencode({"url": url, "output": "json", "filter": "statuscode:200",
                                "collapse": "urlkey", "limit": "-1"})
    st, body = get(f"{CDX}?{q}")
    if not body:
        return None
    try:
        rows = json.loads(body)
    except Exception:
        return None
    if len(rows) < 2:
        return None
    # rows[0] is the header; take the last (most recent) data row
    cols = rows[0]
    last = rows[-1]
    rec = dict(zip(cols, last))
    return rec.get("timestamp"), rec.get("original")


def candidate_urls(client, domain, cap):
    urls = [domain]
    crawl = client / "00-source" / "crawl.json"
    if crawl.exists():
        try:
            data = json.loads(crawl.read_text())
            for p in data.get("pages", []):
                u = p.get("url")
                if u and u not in urls:
                    urls.append(u)
            # sitemap locs if the crawl captured a real one
            sm = data.get("extras", {}).get("/sitemap.xml", {}).get("body", "") or ""
            for loc in re.findall(r"<loc>(.*?)</loc>", sm):
                if loc not in urls:
                    urls.append(loc)
        except Exception:
            pass
    return urls[:cap]


def main():
    client = Path(sys.argv[1]).resolve()
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    st = json.loads((client / "status.json").read_text())
    domain = st.get("domain", "")
    outdir = client / "00-source" / "archive"
    outdir.mkdir(parents=True, exist_ok=True)
    manifest, saved = [], 0
    for url in candidate_urls(client, domain, cap):
        snap = latest_snapshot(url)
        time.sleep(1.5)  # politeness between CDX lookups
        if not snap or not snap[0]:
            manifest.append({"url": url, "snapshot": None})
            continue
        ts, original = snap
        raw = f"http://web.archive.org/web/{ts}id_/{original}"
        code, body = get(raw)
        time.sleep(1.5)
        if body:
            safe = re.sub(r"[^a-z0-9]+", "_", urllib.parse.urlparse(url).path.lower()).strip("_") or "home"
            (outdir / f"{safe}.html").write_bytes(body)
            manifest.append({"url": url, "snapshot": ts, "label": f"ARCHIVE-{ts[:8]}", "file": f"{safe}.html"})
            saved += 1
        else:
            manifest.append({"url": url, "snapshot": ts, "label": f"ARCHIVE-{ts[:8]}", "file": None})
    (outdir / "MANIFEST.json").write_text(json.dumps({"source": "wayback", "domain": domain,
                                                      "captured": manifest}, indent=2))
    dates = sorted({m["snapshot"][:8] for m in manifest if m.get("snapshot")})
    print(f"archive_fetch: {saved} snapshots saved -> {outdir} · "
          f"snapshot dates {dates[:1]}..{dates[-1:]} (STALE — design/copy/census only, never price/stock)")


if __name__ == "__main__":
    main()
