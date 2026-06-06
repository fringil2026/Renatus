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
# primary image ref looks like images/species/1234lrg.jpg (fwd slashes); thumbs use backslashes + med
IMG_REF = re.compile(r"images[\\/]+species[\\/]+(\d+)(lrg|med)\.jpg", re.I)

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
        # collect candidate picids referenced; prefer the first 'lrg' (primary)
        refs = IMG_REF.findall(html)
        primary = next((pid for pid, sz in refs if sz.lower() == "lrg"), None) \
            or (refs[0][0] if refs else None)
        if not primary:
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
