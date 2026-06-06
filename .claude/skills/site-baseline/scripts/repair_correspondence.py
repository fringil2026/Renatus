#!/usr/bin/env python3
"""Repair products.json photo pairings using cover-image truth (Edit 009). Keeps curated
names/care/prices; fixes ONLY the photo (and id/dims) per product. Re-IDs to AO-<coverPicId>;
a page whose cover is nophoto.jpg becomes photos:[] (the site renders the placeholder).
Read-only on the mirror; writes products.json + copies the correct images.
Usage: python3 repair_correspondence.py <client_dir>
"""
import json, re, shutil, sys
from pathlib import Path

COVER = re.compile(r'<img[^>]*js-product-cover[^>]*>', re.I)
COVER_PICID = re.compile(r'src="[^"]*?species[\\/]+(\d+)', re.I)
PAGE_PICID = re.compile(r'id=0*(\d+)\.html', re.I)
VARIANTS = ["lrg", "Lrg", "LRG", "med", "Med", "MED"]


def jpeg_size(path):
    try:
        data = path.read_bytes()
    except Exception:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1; continue
        mk = data[i + 1]
        if mk in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            return (int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big"))
        if 0xD0 <= mk <= 0xD9 or mk == 0x01:
            i += 2; continue
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


def cover_of(html):
    m = COVER.search(html)
    if not m:
        return None, False
    tag = m.group(0)
    if "nophoto" in tag.lower():
        return None, False
    s = COVER_PICID.search(tag)
    return (s.group(1) if s else None), True


def largest(mirror, picid):
    best, bw, bv = None, -1, None
    for v in VARIANTS:
        for sep in ("\\", "/"):
            c = mirror / f"images{sep}species{sep}{picid}{v}.jpg"
            if c.exists():
                sz = jpeg_size(c)
                if sz and sz[0] > bw:
                    best, bw, bv = c, sz[0], v
    return best, bv


def main():
    client = Path(sys.argv[1]).resolve()
    mirror = client / "00-source" / "mirror" / "andysorchids.com"
    dest = client / "03-site" / "public" / "specimens"
    dest.mkdir(parents=True, exist_ok=True)
    dp = client / "03-site" / "src" / "data" / "products.json"
    data = json.loads(dp.read_text())

    changed, nophoto, report = 0, 0, []
    for prod in data["products"]:
        sp = prod.get("source_page", "")
        old = prod.get("photos") or []
        old_pic = Path(old[0]).stem if old else None
        if not sp or not (mirror / sp).exists():
            report.append(f"{prod['id']}: no source_page — skipped"); continue
        html = (mirror / sp).read_text(errors="ignore")
        cpic, has = cover_of(html)
        pagepic = PAGE_PICID.search(sp).group(1) if PAGE_PICID.search(sp) else (cpic or "x")
        if has and cpic:
            img, variant = largest(mirror, cpic)
            sz = jpeg_size(img) if img else None
            if img:
                shutil.copyfile(img, dest / f"{cpic}.jpg")
                prod["photo_px"] = [sz[0], sz[1]] if sz else [0, 0]
                prod["photo_slot_ok"] = bool(sz and sz[0] >= 600)
                prod["largest_variant"] = f"{cpic}{variant}.jpg"
            prod["photos"] = [f"/specimens/{cpic}.jpg"]
            prod["id"] = f"AO-{cpic}"
            if old_pic != cpic:
                changed += 1
            report.append(f"AO-{cpic} {prod['slug']}: photo {old_pic} -> {cpic} {prod.get('photo_px')}")
        else:
            prod["id"] = f"AO-{pagepic}"
            prod["photos"] = []
            for k in ("largest_variant", "photo_px", "photo_slot_ok"):
                prod.pop(k, None)
            prod["no_photo_on_source"] = True
            nophoto += 1
            if old:
                changed += 1
            report.append(f"AO-{pagepic} {prod['slug']}: NOPHOTO on source -> placeholder (was {old_pic})")

    dp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"repair_correspondence: {changed} photos changed; {nophoto} now no-photo (placeholder)")
    for r in report:
        print("  " + r)


if __name__ == "__main__":
    main()
