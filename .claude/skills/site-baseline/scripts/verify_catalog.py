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
IMG_REF = re.compile(r"images[\\/]+species[\\/]+(\d+)(lrg|med)\.jpg", re.I)


def page_index(mirror_root: Path):
    """Map primary-image PicId -> (genus, species, page_filename) for every product page."""
    idx = {}
    for p in sorted(mirror_root.glob("pictureframe.asp?*id=*.html")):
        html = p.read_text(errors="ignore")
        m = GENUS_SPECIES.search(html)
        if not m:
            continue
        refs = IMG_REF.findall(html)
        primary = next((pid for pid, sz in refs if sz.lower() == "lrg"), None) or (refs[0][0] if refs else None)
        if primary and primary not in idx:
            idx[primary] = (m.group(1).strip().rstrip("."), m.group(2).strip().rstrip("."), p.name)
    return idx


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def main():
    client = Path(sys.argv[1]).resolve()
    data_path = client / "03-site" / "src" / "data" / "products.json"
    data = json.loads(data_path.read_text())
    idx = page_index(client / "00-source" / "mirror" / "andysorchids.com")

    mism, unver, ok = [], [], 0
    for prod in data["products"]:
        photos = prod.get("photos") or []
        if not photos:
            unver.append((prod["id"], "no photo"))
            continue
        picid = Path(photos[0]).stem  # /specimens/8865.jpg -> 8865
        page = idx.get(picid)
        if not page:
            unver.append((prod["id"], f"photo {picid} not found on any product page"))
            continue
        pg_genus, pg_species, pg_name = page
        prod["source_page"] = pg_name
        # correspondence: the photo's own page must name this product's genus + species-core
        genus_ok = norm(pg_genus).startswith(norm(prod["genus"])) or norm(prod["genus"]).startswith(norm(pg_genus))
        species_core = norm(prod["species"].split()[0]) if prod["species"].split() else ""
        species_ok = species_core and species_core in norm(pg_species)
        if genus_ok and species_ok:
            ok += 1
        else:
            mism.append((prod["id"], f"photo {picid}'s page is '{pg_genus} {pg_species}' but product says '{prod['genus']} {prod['species']}'"))

    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"verify_catalog: {ok} OK · {len(mism)} MISMATCH · {len(unver)} unverified (of {len(data['products'])})")
    for pid, why in mism:
        print(f"  MISMATCH {pid}: {why}")
    for pid, why in unver:
        print(f"  unverified {pid}: {why}")
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
