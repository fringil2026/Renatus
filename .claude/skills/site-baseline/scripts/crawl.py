#!/usr/bin/env python3
"""Method 1 — HTTP crawler. BFS over same-host links; per page captures
status, title, meta, headings, text, links, OG, JSON-LD, images, stylesheets,
scripts. Also fetches robots.txt and sitemap.xml. Output: crawl.json.

Usage: python3 crawl.py https://example.com out/crawl.json [max_pages]
"""
import json, re, sys, time
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; StudioBaseline/1.0; site rebuild discovery)"
SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|mp4|mov|webm|mp3|woff2?|ttf|eot|css|js|xml|json)(\?|$)", re.I)

def norm(base, href):
    if not href:
        return None
    href = urldefrag(urljoin(base, href.strip()))[0]
    return href.rstrip("/") or href

def page_record(url, resp, soup):
    def meta(name=None, prop=None):
        tag = soup.find("meta", attrs={"name": name} if name else {"property": prop})
        return (tag.get("content") or "").strip() if tag else ""
    jsonld = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            jsonld.append(json.loads(s.string or ""))
        except Exception:
            pass
    robots_meta = meta(name="robots")
    canon = soup.find("link", rel="canonical")
    return {
        "url": url,
        "status": resp.status_code,
        "title": (soup.title.string or "").strip() if soup.title and soup.title.string else "",
        "meta_description": meta(name="description"),
        "robots_meta": robots_meta,
        "noindex": "noindex" in robots_meta.lower(),
        "canonical": (canon.get("href") or "").strip() if canon else "",
        "h1": [h.get_text(" ", strip=True) for h in soup.find_all("h1")],
        "h2": [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:20],
        "og": {t.get("property"): (t.get("content") or "") for t in soup.find_all("meta")
               if t.get("property", "").startswith("og:")},
        "jsonld_types": sorted({d.get("@type", "?") if isinstance(d, dict) else "?"
                                for d in jsonld if d}),
        "jsonld": jsonld,
        "hreflang": [l.get("hreflang") for l in soup.find_all("link", rel="alternate") if l.get("hreflang")],
        "images": [{"src": norm(url, i.get("src")), "alt": (i.get("alt") or "").strip()}
                   for i in soup.find_all("img")][:60],
        "stylesheets": [norm(url, l.get("href")) for l in soup.find_all("link", rel="stylesheet")],
        "scripts": [norm(url, s.get("src")) for s in soup.find_all("script") if s.get("src")],
        "inline_scripts_sample": " ".join((s.string or "")[:400] for s in soup.find_all("script")
                                          if not s.get("src"))[:4000],
        "forms": [{"action": norm(url, f.get("action")) or url, "method": (f.get("method") or "GET").upper(),
                   "fields": [i.get("name") for i in f.find_all(["input", "textarea", "select"]) if i.get("name")]}
                  for f in soup.find_all("form")],
        "text": soup.get_text(" ", strip=True),
        "word_count": len(soup.get_text(" ", strip=True).split()),
    }

def crawl(start, max_pages=150, delay=0.4):
    if not start.startswith("http"):
        start = "https://" + start
    start = start.rstrip("/")
    host = urlparse(start).netloc.replace("www.", "")
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    seen, pages, links = set(), [], {}
    q = deque([start])
    while q and len(pages) < max_pages:
        url = q.popleft()
        if url in seen or SKIP_EXT.search(url):
            continue
        seen.add(url)
        try:
            r = sess.get(url, timeout=15, allow_redirects=True)
        except Exception as e:
            pages.append({"url": url, "status": 0, "error": str(e)[:200]})
            continue
        final = r.url.rstrip("/")
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype:
            pages.append({"url": url, "status": r.status_code, "content_type": ctype})
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        rec = page_record(final, r, soup)
        rec["requested_url"] = url
        rec["redirected"] = (final != url)
        pages.append(rec)
        outlinks = set()
        for a in soup.find_all("a", href=True):
            v = norm(final, a["href"])
            if v and urlparse(v).netloc.replace("www.", "") == host and not SKIP_EXT.search(v):
                outlinks.add(v)
                if v not in seen:
                    q.append(v)
        links[final] = sorted(outlinks)
        time.sleep(delay)
    # site-level files
    extras = {}
    for path in ("/robots.txt", "/sitemap.xml"):
        try:
            r = sess.get(start + path, timeout=10)
            extras[path] = {"status": r.status_code, "body": r.text[:20000]}
        except Exception as e:
            extras[path] = {"status": 0, "error": str(e)[:200]}
    return {"start": start, "host": host, "crawled": len(pages),
            "pages": pages, "links": links, "extras": extras}

def main():
    start, out = sys.argv[1], sys.argv[2]
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    data = crawl(start, max_pages)
    from pathlib import Path
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data, indent=1))
    print(f"crawl: {data['crawled']} pages -> {out}")

if __name__ == "__main__":
    main()
