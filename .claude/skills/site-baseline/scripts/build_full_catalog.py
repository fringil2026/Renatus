#!/usr/bin/env python3
"""Build the ENTIRE catalog from the mirror (rehearsal completeness pass). For every product page:
genus/species (meta), the TRUE cover image (js-product-cover; nophoto => type-led no-photo card),
largest on-disk photo variant + dimensions, and DRAFT real price + description scraped from the page
(labelled DRAFT — client facts pending owner confirmation; never fabricated where absent).
Dedupes by slug, writes 03-site/src/data/products.json, copies photos to public/specimens/, prints
coverage stats. No limit. Read-only on the mirror.
Usage: python3 build_full_catalog.py <client_dir>
"""
import json, re, shutil, sys
from pathlib import Path

GENUS_SPECIES = re.compile(r"orchid\s+genus:\s*([A-Za-z()\- ]+?)\s*,\s*orchid\s+species:\s*([A-Za-z0-9'’.\- ]+)", re.I)
COVER = re.compile(r'<img[^>]*js-product-cover[^>]*>', re.I)
COVER_PICID = re.compile(r'src="[^"]*?species[\\/]+(\d+)', re.I)
META_DESC = re.compile(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', re.I | re.S)
PRICE_NEAR = re.compile(r'class="[^"]*price[^"]*"[^>]*>\s*\$?\s*([0-9]{1,4}(?:\.[0-9]{2})?)', re.I)
PRICE_ANY = re.compile(r'\$\s?([0-9]{1,4}\.[0-9]{2})')
VARIANTS = ["lrg", "Lrg", "LRG", "med", "Med", "MED", "sm", "Sm"]
SKIP_GENERA = {"supplies", "books", "supply"}


def jpeg_size(path):
    try: data = path.read_bytes()
    except Exception: return None
    if data[:2] != b"\xff\xd8": return None
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF: i += 1; continue
        mk = data[i + 1]
        if mk in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB):
            return (int.from_bytes(data[i+7:i+9],"big"), int.from_bytes(data[i+5:i+7],"big"))
        if 0xD0 <= mk <= 0xD9 or mk == 0x01: i += 2; continue
        i += 2 + int.from_bytes(data[i+2:i+4],"big")
    return None


def cover_of(html):
    m = COVER.search(html)
    if not m: return None, False
    tag = m.group(0)
    if "nophoto" in tag.lower(): return None, False
    s = COVER_PICID.search(tag)
    return (s.group(1) if s else None), True


def largest(mirror, picid):
    best, bw, bv = None, -1, None
    for v in VARIANTS:
        for sep in ("\\", "/"):
            c = mirror / f"images{sep}species{sep}{picid}{v}.jpg"
            if c.exists():
                sz = jpeg_size(c)
                if sz and sz[0] > bw: best, bw, bv = c, sz[0], v
    return best


def slugify(g, s):
    return re.sub(r"[^a-z0-9]+", "-", f"{g} {s}".lower()).strip("-")


def main():
    client = Path(sys.argv[1]).resolve()
    mirror = client / "00-source" / "mirror" / "andysorchids.com"
    dest = client / "03-site" / "public" / "specimens"; dest.mkdir(parents=True, exist_ok=True)
    out, seen = [], set()
    with_photo = no_photo = with_price = 0
    for p in sorted(mirror.glob("pictureframe.asp?*id=*.html")):
        html = p.read_text(errors="ignore")
        m = GENUS_SPECIES.search(html)
        if not m: continue
        genus = m.group(1).strip().rstrip("."); species = m.group(2).strip().rstrip(".")
        if not species or len(species) > 48 or genus.lower() in SKIP_GENERA: continue
        if "inch" in species.lower() or "basket" in species.lower(): continue
        slug = slugify(genus, species)
        if slug in seen: continue
        seen.add(slug)
        cpic, has = cover_of(html)
        photos = []
        if has and cpic:
            img = largest(mirror, cpic)
            if img:
                shutil.copyfile(img, dest / f"{cpic}.jpg"); sz = jpeg_size(img) or [None, None]
                photos = [{"path": f"/specimens/{cpic}.jpg", "alt": f"{genus} {species}", "w": sz[0], "h": sz[1]}]
        if photos: with_photo += 1
        else: no_photo += 1
        # DRAFT price (prefer a price-classed element, else any $) and DRAFT description (meta)
        pm = PRICE_NEAR.search(html) or PRICE_ANY.search(html)
        price_cents = int(round(float(pm.group(1)) * 100)) if pm else 0
        if pm: with_price += 1
        dm = META_DESC.search(html)
        desc = re.sub(r"\s+", " ", dm.group(1)).strip()[:400] if dm else ""
        pid = re.search(r"id=0*(\d+)\.html", p.name, re.I)
        out.append({
            "id": f"AO-{cpic or (pid.group(1) if pid else slug)}", "slug": slug,
            "genus": genus, "species": species, "common_name": "", "origin": "",
            "description": desc, "price_cents": price_cents, "currency": "USD",
            "stock_qty": 0, "availability": "in-stock", "status": "active",
            "care_light": "", "care_water": "", "care_temp": "", "difficulty": "intermediate",
            "bloom_now": False, "photos": [ph["path"] for ph in photos], "photo_meta": photos,
            "source_page": p.name, "draft": True,
        })
    data = {"_meta": "REHEARSAL FULL CATALOG — entire scraped catalog. genus/species + photos are REAL "
            "(client's own site). PRICES and DESCRIPTIONS are scraped REAL data, DRAFT (client facts "
            "pending owner confirmation). STOCK is unknown (0; availability='in-stock' so the demo "
            "browses everything); owner sets real stock in admin. No fabricated facts.",
            "products": out}
    (client / "03-site" / "src" / "data" / "products.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"build_full_catalog: {len(out)} products · with photo {with_photo} · no photo {no_photo} · "
          f"with DRAFT price {with_price} ({round(100*with_photo/max(1,len(out)))}% photo coverage)")


if __name__ == "__main__":
    main()
