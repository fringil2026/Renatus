#!/usr/bin/env python3
"""Miva Merchant product-image extractor (diagnosed fix for WS-INC-ORCHIDS-BY-HAUSERMANN-001).
Miva lazy-loads the product photo via `<img id="js-main-image" data-image="graphics/00000001/<GUID>.jpeg">`
— the static `src` is a blank.gif placeholder, so the generic <img src> extractor captured nothing.
This reads each product's OWN source_page, pulls `data-image`, downloads the real photo, and pairs it
to that product (same page ⇒ correspondence-safe). Updates products.json in place.
Politeness: browser UA, ~0.8s spacing, bounded retries.
Usage: python3 extract_miva_images.py <client_dir>
"""
import json, re, ssl, sys, time, urllib.request
from pathlib import Path

try:
    import certifi; CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_default_context()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MAIN_IMG = re.compile(r'<img[^>]*\bid="js-main-image"[^>]*>', re.I)
DATA_IMG = re.compile(r'data-image="([^"]+)"', re.I)

def jpeg_size(data):
    if data[:2] != b"\xff\xd8": return None
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF: i += 1; continue
        mk = data[i+1]
        if mk in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB):
            return (int.from_bytes(data[i+7:i+9],"big"), int.from_bytes(data[i+5:i+7],"big"))
        if 0xD0 <= mk <= 0xD9 or mk == 0x01: i += 2; continue
        i += 2 + int.from_bytes(data[i+2:i+4],"big")
    return None

def fetch(url, binary=False):
    for _ in range(2):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=25, context=CTX) as resp:
                return resp.read() if binary else resp.read().decode("utf-8", "ignore")
        except Exception:
            time.sleep(1.2)
    return None

def main():
    client = Path(sys.argv[1]).resolve()
    base = re.match(r'https?://[^/]+', json.loads((client / "status.json").read_text())["domain"]).group(0)
    pj = client / "03-site" / "src" / "data" / "products.json"
    data = json.loads(pj.read_text())
    prods = data.get("products", [])
    dest = client / "03-site" / "public" / "specimens"; dest.mkdir(parents=True, exist_ok=True)
    got = small = 0
    for p in prods:
        src = p.get("source_page")
        if not src:
            continue
        html = fetch(src); time.sleep(0.8)
        if not html:
            continue
        m = MAIN_IMG.search(html)
        di = DATA_IMG.search(m.group(0)) if m else None
        if not di:
            continue
        rel = di.group(1).lstrip("/")
        img_url = f"{base}/mm5/{rel}" if not rel.startswith("http") else rel
        blob = fetch(img_url, binary=True)
        if not blob:
            continue
        code = re.sub(r"[^A-Za-z0-9_-]+", "-", p.get("id") or p.get("slug"))
        (dest / f"{code}.jpg").write_bytes(blob)
        sz = jpeg_size(blob) or [None, None]
        if sz[0] and sz[0] < 600:
            small += 1
        p["photos"] = [f"/specimens/{code}.jpg"]
        p["photo_meta"] = [{"path": f"/specimens/{code}.jpg", "alt": f"{p.get('genus','')} {p.get('species','')}".strip(),
                            "w": sz[0], "h": sz[1], "source_page": src}]
        got += 1
    pj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    cov = round(100 * got / max(1, len(prods)))
    print(f"extract_miva_images: {got}/{len(prods)} products got a real photo ({cov}%); "
          f"{small} below 600px (D-2.7.4 ask). Paired from each product's own source_page (correspondence-safe).")

if __name__ == "__main__":
    main()
