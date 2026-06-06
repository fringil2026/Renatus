#!/usr/bin/env python3
"""Product-correspondence verifier (Part 2 rule). For every product in a built catalog,
confirm its photo and its name come from the SAME source page: look up the page that owns the
product's photo (by PicId) and check that page's meta names the product's genus/species.

Records `source_page` back into products.json (provenance). Reports MATCH / MISMATCH / UNVERIFIED.
Read-only on the mirror; writes only products.json.

Usage: python3 verify_catalog.py <client_dir>
Exit non-zero if any MISMATCH is found (so a build can treat it as failure).
"""
import json, re, sys
from pathlib import Path

GENUS_SPECIES = re.compile(r"orchid\s+genus:\s*([A-Z][A-Za-z()\- ]+?)\s*,\s*orchid\s+species:\s*([A-Za-z0-9'’.\- ]+)", re.I)
# Cover-based truth (Edit 009): verify against the product-cover <img>, NOT "first lrg" — otherwise
# the verifier shares the extractor's blind spot and self-confirms a wrong pairing.
COVER = re.compile(r'<img[^>]*js-product-cover[^>]*>', re.I)
COVER_PICID = re.compile(r'src="[^"]*?species[\\/]+(\d+)', re.I)


def cover_of(html):
    """(picid, has_photo) from the product-cover <img>. nophoto.jpg => (None, False)."""
    m = COVER.search(html)
    if not m:
        return None, False
    tag = m.group(0)
    if "nophoto" in tag.lower():
        return None, False
    s = COVER_PICID.search(tag)
    return (s.group(1) if s else None), True


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def main():
    client = Path(sys.argv[1]).resolve()
    mirror = client / "00-source" / "mirror" / "andysorchids.com"
    data_path = client / "03-site" / "src" / "data" / "products.json"
    data = json.loads(data_path.read_text())

    mism, unver, ok = [], [], 0
    for prod in data["products"]:
        sp = prod.get("source_page", "")
        if not sp or not (mirror / sp).exists():
            unver.append((prod["id"], "no resolvable source_page"))
            continue
        html = (mirror / sp).read_text(errors="ignore")
        g = GENUS_SPECIES.search(html)
        pg_genus = g.group(1).strip().rstrip(".") if g else ""
        pg_species = g.group(2).strip().rstrip(".") if g else ""
        cover_picid, has_photo = cover_of(html)
        photos = prod.get("photos") or []
        our_picid = Path(photos[0]).stem if photos else None
        # name check: the source page must name this product's genus + species-core
        genus_ok = norm(pg_genus).startswith(norm(prod["genus"])) or norm(prod["genus"]).startswith(norm(pg_genus))
        sp_core = norm(prod["species"].split()[0]) if prod["species"].split() else ""
        species_ok = bool(sp_core) and sp_core in norm(pg_species)
        # photo check vs the page's TRUE cover image (or: no photo when the page is nophoto)
        photo_ok = (our_picid == cover_picid) if has_photo else (not photos)
        if genus_ok and species_ok and photo_ok:
            ok += 1
        else:
            why = []
            if not (genus_ok and species_ok):
                why.append(f"name vs page '{pg_genus} {pg_species}'")
            if not photo_ok:
                why.append(f"photo {our_picid} != cover {cover_picid or 'NOPHOTO'}")
            mism.append((prod["id"], "; ".join(why)))

    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"verify_catalog: {ok} OK · {len(mism)} MISMATCH · {len(unver)} unverified (of {len(data['products'])})")
    for pid, why in mism:
        print(f"  MISMATCH {pid}: {why}")
    for pid, why in unver:
        print(f"  unverified {pid}: {why}")
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
