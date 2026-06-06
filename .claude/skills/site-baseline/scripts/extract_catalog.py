#!/usr/bin/env python3
"""Best-effort product-catalog extraction from a wget mirror (e-commerce baselines).
Scans 00-source/mirror product pages, pulls genus/species from the page meta, and pairs
each with its primary on-disk photo. Emits JSON to stdout. Read-only on the mirror; no network.

Usage: python3 extract_catalog.py <client_dir> [limit] [--copy <dest_dir>]
With --copy, each product's photo is copied to <dest_dir>/<picid>.jpg (clean name) and the
record gains image_web = /<dest_basename>/<picid>.jpg for direct use in the site.
"""
import json, re, shutil, sys
from pathlib import Path

SKIP_GENERA = {"supplies", "books", "supply"}

GENUS_SPECIES = re.compile(r"orchid\s+genus:\s*([A-Z][A-Za-z()\- ]+?)\s*,\s*orchid\s+species:\s*([A-Za-z0-9'’.\- ]+)", re.I)
TITLE_NAME = re.compile(r"<title>\s*(.*?)\s*</title>", re.I | re.S)
# CORRECTNESS FIX (Edit 009): the product's main photo is the js-product-cover <img>, NOT the
# first images/species/*lrg.jpg on the page — pages render a stray featured/related image first,
# so "first lrg" pairs the wrong plant's photo. Parse the cover tag; nophoto.jpg => no photo.
COVER = re.compile(r'<img[^>]*js-product-cover[^>]*>', re.I)
COVER_PICID = re.compile(r'src="[^"]*?species[\\/]+(\d+)', re.I)

def cover_image(html):
    """Return (picid, has_photo) from the product-cover <img>. nophoto.jpg => (None, False)."""
    m = COVER.search(html)
    if not m:
        return None, False
    tag = m.group(0)
    if "nophoto" in tag.lower():
        return None, False
    s = COVER_PICID.search(tag)
    return (s.group(1) if s else None), True

def find_image_on_disk(mirror_root, picid):
    """The mirror stored files with literal backslashes in the name. Try lrg then med,
    both slash styles and common case variants."""
    for size in ("lrg", "Lrg", "LRG", "med", "Med", "MED"):
        for sep in ("\\", "/"):
            cand = mirror_root / f"images{sep}species{sep}{picid}{size}.jpg"
            if cand.exists():
                return cand
    # last resort: any file whose name ends with <picid><something>.jpg
    for f in mirror_root.glob(f"*{picid}*.jpg"):
        return f
    return None

def main():
    args = sys.argv[1:]
    copy_dest = None
    if "--copy" in args:
        i = args.index("--copy")
        copy_dest = Path(args[i + 1]).resolve()
        del args[i:i + 2]
    client = Path(args[0]).resolve()
    limit = int(args[1]) if len(args) > 1 else 9999
    mirror_root = client / "00-source" / "mirror" / "andysorchids.com"
    pages = sorted(mirror_root.glob("pictureframe.asp?*id=*.html"))
    out, seen = [], set()
    for p in pages:
        try:
            html = p.read_text(errors="ignore")
        except Exception:
            continue
        m = GENUS_SPECIES.search(html)
        if not m:
            continue
        genus = m.group(1).strip().rstrip(".")
        species = m.group(2).strip().rstrip(".")
        key = (genus.lower(), species.lower())
        if key in seen or not species or len(species) > 40:
            continue
        if genus.lower() in SKIP_GENERA or "inch" in species.lower() or "basket" in species.lower():
            continue
        # the product's TRUE photo is the cover <img> (Edit 009 fix). nophoto => skip (no image
        # to ship for this product; image-bearing builds want only products with a real photo).
        primary, has_photo = cover_image(html)
        if not has_photo or not primary:
            continue
        img = find_image_on_disk(mirror_root, primary)
        if not img:
            continue
        seen.add(key)
        rec = {
            "picid": primary,
            "genus": genus,
            "species": species,
            "image_disk": str(img),
            "source_page": p.name,
        }
        if copy_dest:
            copy_dest.mkdir(parents=True, exist_ok=True)
            dest = copy_dest / f"{primary}.jpg"
            shutil.copyfile(img, dest)
            rec["image_web"] = f"/{copy_dest.name}/{primary}.jpg"
        out.append(rec)
        if len(out) >= limit:
            break
    print(json.dumps({"count": len(out), "products": out}, indent=2))

if __name__ == "__main__":
    main()
