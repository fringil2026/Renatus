#!/usr/bin/env python3
"""Volusion catalog scraper (diagnosed fix for WS-INC-SEATTLE-ORCHIDS-002 — UNCRAWLED).
Volusion exposes the whole catalog in /sitemap.xml as `/<Name>-p/<sku>.htm` product URLs (sku is
ALPHANUMERIC). The generic crawler followed category `-s/` links and capped out before any product.
This enumerates the sitemap and fetches+parses product pages from their STATIC HTML (og:title,
og:image, "Our Price $X") — no JS, no unblocking tricks. Politeness is law: browser UA, ~1s spacing,
bounded retries, bounded count.
Usage: python3 scrape_volusion.py <client_dir> [max_products]   (env SCRAPE_MAX overrides; 0 = all)
"""
import json, re, ssl, sys, time, urllib.request, os
from pathlib import Path

try:
    import certifi; CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def get(url):
    for _ in range(2):  # bounded retries — never an arms race
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=25, context=CTX) as resp:
                return resp.status, resp.read().decode("utf-8", "ignore")
        except Exception:
            time.sleep(1.5)
    return None, ""

def first(pat, html, flags=re.S):
    m = re.search(pat, html, flags)
    return m.group(1).strip() if m else ""

def main():
    client = Path(sys.argv[1]).resolve()
    domain = json.loads((client / "status.json").read_text()).get("domain", "").rstrip("/")
    base = re.match(r'https?://[^/]+', domain).group(0)
    cap = int(os.environ.get("SCRAPE_MAX", sys.argv[2] if len(sys.argv) > 2 else "60"))

    s, sm = get(base + "/sitemap.xml")
    locs = re.findall(r'<loc>(.*?)</loc>', sm)
    products = [u for u in locs if re.search(r'-p/[\w\-]+\.htm', u)]
    cats = [u for u in locs if re.search(r'-s/\d+\.htm', u)]
    todo = products if cap == 0 else products[:cap]
    print(f"sitemap: {len(locs)} urls -> {len(products)} products, {len(cats)} categories; fetching {len(todo)}")

    pdir = client / "00-source" / "products"; pdir.mkdir(parents=True, exist_ok=True)
    out, with_price, with_photo = [], 0, 0
    for i, u in enumerate(todo):
        st, html = get(u)
        time.sleep(1.0)   # polite
        if not html:
            continue
        sku = re.search(r'-p/([\w\-]+)\.htm', u).group(1)
        (pdir / f"{sku}.html").write_text(html)
        name = first(r'og:title"\s*content="([^"]+)"', html) or first(r'itemprop="name"[^>]*>([^<]+)', html)
        img = first(r'og:image"\s*content="([^"]+)"', html)
        if img and not re.search(r'\.(jpg|jpeg|png|webp)$', img, re.I):
            img = img + ".jpg"   # Volusion og:image often omits the extension
        price = first(r'[Oo]ur\s+[Pp]rice[^$]*\$([0-9][0-9.,]*)', html) or first(r'\$([0-9]+\.[0-9]{2})', html)
        cents = int(round(float(price.replace(",", "")) * 100)) if price else 0
        if cents: with_price += 1
        if img: with_photo += 1
        out.append({"sku": sku, "name": name, "price_cents": cents, "price_draft": True,
                    "photo": img, "source_url": u})
        if (i + 1) % 25 == 0:
            print(f"  …{i+1}/{len(todo)} fetched")
    data = {"_meta": "Volusion catalog draft. names + photos REAL (client's own site); prices DRAFT "
            "(scraped 'Our Price', pending owner confirmation). NOT fabricated where absent.",
            "platform": "volusion", "discovered_products": len(products), "fetched": len(todo),
            "products": out}
    (client / "01-baseline").mkdir(parents=True, exist_ok=True)
    (client / "01-baseline" / "catalog-draft.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    cov = round(100 * with_photo / max(1, len(out)))
    print(f"scrape_volusion: extracted {len(out)} products · with price {with_price} · with photo "
          f"{with_photo} ({cov}%) · discovered total {len(products)} -> 01-baseline/catalog-draft.json")

if __name__ == "__main__":
    main()
