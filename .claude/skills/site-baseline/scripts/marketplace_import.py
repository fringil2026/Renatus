#!/usr/bin/env python3
"""Marketplace-export intake (SYSTEM.md §1a) — map an owner-authorized Etsy/eBay listings CSV
+ the owner's own photos into DRAFT product records, photos matched by SKU / listing-id / filename.

This is NOT a scraper. The only inputs are an owner-authorized export (the seller ran it from
their OWN Shop Manager / Seller Hub, or granted access) + the owner's own photos. It NEVER touches
a marketplace account and is NEVER used against other sellers' listings.

Usage:
  marketplace_import.py <client_dir> [--quiet]

Reads:
  <client_dir>/02-intake/marketplace-export.csv   the uploaded listings export (Etsy or eBay)
  <client_dir>/02-intake/assets/                   the owner's product photos (any depth)
  <client_dir>/status.json                         catalog.{source,owner} provenance (optional)

Writes:
  <client_dir>/01-baseline/catalog-draft.json      DRAFT product records, correspondence-safe

Prints (stdout, last line):
  a JSON summary {products, with_photo, products_without_photo, unmatched_photos, ...} for the
  dashboard import preview. Everything is read from files, so it is correct after refresh/restart.
"""
import csv, json, re, struct, sys
from pathlib import Path

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".tif", ".tiff", ".bmp"}


# ---------------- header normalisation + platform detection ----------------
def _norm_key(k):
    return re.sub(r"\s+", " ", (k or "").strip().lower())


def detect_platform(headers):
    """Auto-detect Etsy vs eBay from the CSV header row (case/space tolerant)."""
    h = {_norm_key(x) for x in headers}
    # eBay Seller Hub / File Exchange signatures
    if {"item number"} & h or {"custom label (sku)"} & h or {"available quantity"} & h \
       or {"start price"} & h or {"buy it now price"} & h:
        return "ebay"
    # Etsy "Currently for sale listings" download signatures
    if {"currency_code"} & h or {"image1"} & h or {"variation 1 type"} & h \
       or ({"title", "quantity", "tags"} <= h):
        return "etsy"
    # Fallbacks: prefer Etsy when a TITLE+PRICE shape with IMAGEn exists, else eBay
    if {"title", "price"} <= h:
        return "etsy"
    return "ebay" if ("item number" in h) else "etsy"


def _row_getter(row):
    """Return g(*names) -> first present, non-empty cell for any of the given header names
    (case/space tolerant)."""
    lut = {_norm_key(k): v for k, v in row.items() if k is not None}

    def g(*names):
        for n in names:
            v = lut.get(_norm_key(n))
            if v is not None and str(v).strip() != "":
                return str(v).strip()
        return ""
    return g


def _split_multi(s):
    if not s:
        return []
    parts = re.split(r"[|,;]", s)
    return [p.strip() for p in parts if p.strip()]


def _clean_price(s):
    """Keep the numeric price as a DRAFT string; strip currency symbols/thousands separators."""
    if not s:
        return ""
    m = re.search(r"\d+(?:[.,]\d+)?", s.replace(",", ""))
    return m.group(0) if m else s.strip()


def _basename_stems(urls):
    """Filename stems from a list of export image URLs (for filename-based photo matching)."""
    out = []
    for u in urls:
        name = re.split(r"[?#]", u.strip())[0].rstrip("/").split("/")[-1]
        if name:
            out.append(Path(name).stem)
    return out


# ---------------- per-platform record mapping ----------------
def map_etsy(row):
    g = _row_getter(row)
    img_urls = [g(f"IMAGE{i}") for i in range(1, 11)]
    img_urls = [u for u in img_urls if u]
    variants = []
    for i in (1, 2):
        vt, vv = g(f"VARIATION {i} TYPE"), g(f"VARIATION {i} VALUES")
        if vt or vv:
            variants.append({"type": vt, "values": _split_multi(vv)})
    return {
        "name": g("TITLE"),
        "description": g("DESCRIPTION"),
        "price": _clean_price(g("PRICE")),
        "currency": g("CURRENCY_CODE", "CURRENCY"),
        "quantity": g("QUANTITY"),
        "sku": g("SKU"),
        "listing_id": g("LISTING ID", "LISTING_ID"),
        "tags": _split_multi(g("TAGS")),
        "category": (g("SECTION") or (_split_multi(g("TAGS"))[:1] or [""])[0]),
        "variants": variants,
        "source_image_urls": img_urls,
    }


def map_ebay(row):
    g = _row_getter(row)
    img_urls = _split_multi(g("Photo URL", "PicURL", "Picture URL", "Image URL"))
    var = g("Variation details", "Variation")
    variants = [{"type": "variation", "values": _split_multi(var)}] if var else []
    return {
        "name": g("Title"),
        "description": g("Description"),
        "price": _clean_price(g("Current price", "Start price", "Buy It Now price", "Price")),
        "currency": g("Currency"),
        "quantity": g("Available quantity", "Quantity"),
        "sku": g("Custom label (SKU)", "Custom label", "SKU"),
        "listing_id": g("Item number", "Item ID", "ItemID"),
        "tags": [],
        "category": g("Category name", "Category"),
        "variants": variants,
        "source_image_urls": img_urls,
    }


# ---------------- photo correspondence (matched by SKU / listing-id / filename) ----------------
def _norm_token(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def list_assets(assets_dir):
    out = []
    if assets_dir.is_dir():
        for p in sorted(assets_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMG_EXTS:
                out.append(p)
    return out


def match_photos(products, assets_dir):
    """Pair each product's photo from the assets folder by SKU, then listing-id, then filename.
    NEVER by array order or index — that silently produces a right-name / wrong-photo catalog
    (CLAUDE.md product-correspondence rule). A photo is claimed by at most one product so the
    pairing stays one-to-one and unmatched photos surface honestly."""
    assets = list_assets(assets_dir)
    stems = {p: _norm_token(p.stem) for p in assets}
    used = set()

    def find(keys, exact_first=True):
        keys = [_norm_token(k) for k in keys if k and len(_norm_token(k)) >= 3]
        if not keys:
            return None
        # exact stem match wins, then "stem startswith key" / "key in stem"
        for k in keys:
            for p in assets:
                if p in used:
                    continue
                if stems[p] == k:
                    return p
        for k in keys:
            for p in assets:
                if p in used:
                    continue
                if stems[p].startswith(k) or k in stems[p]:
                    return p
        return None

    for prod in products:
        photo, mtype = None, "none"
        p = find([prod.get("sku")])
        if p:
            mtype = "sku"
        if not p:
            p = find([prod.get("listing_id")])
            if p:
                mtype = "listing-id"
        if not p:
            # filename match: export image filenames, then the product-name slug
            cands = _basename_stems(prod.get("source_image_urls", [])) + [prod.get("name", "")]
            p = find([c for c in cands if len(_norm_token(c)) >= 5])
            if p:
                mtype = "filename"
        if p:
            used.add(p)
            try:
                photo = "assets/" + str(p.relative_to(assets_dir)).replace("\\", "/")
            except ValueError:
                photo = "assets/" + p.name
        prod["photo"] = photo
        prod["photo_match"] = mtype
        prod["photo_dimensions"] = image_size(p) if p else None

    unmatched = [str(p.relative_to(assets_dir)).replace("\\", "/") for p in assets if p not in used]
    return assets, unmatched


# ---------------- best-effort image dimensions (no PIL dependency; null on any doubt) ----------------
def image_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", head[16:24])
                return [w, h]
            if head[:6] in (b"GIF87a", b"GIF89a"):
                w, h = struct.unpack("<HH", head[6:10])
                return [w, h]
            if head[:2] == b"\xff\xd8":  # JPEG — walk the markers for SOF
                f.seek(2)
                b = f.read(1)
                while b and b == b"\xff":
                    while b == b"\xff":
                        b = f.read(1)
                    marker = b[0]
                    if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return [w, h]
                    seg = f.read(2)
                    if len(seg) < 2:
                        break
                    f.seek(struct.unpack(">H", seg)[0] - 2, 1)
                    b = f.read(1)
    except Exception:
        return None
    return None


# ---------------- driver ----------------
def parse_csv(csv_path):
    raw = Path(csv_path).read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(raw.splitlines())
    headers = reader.fieldnames or []
    platform = detect_platform(headers)
    mapper = map_etsy if platform == "etsy" else map_ebay
    products = []
    for row in reader:
        if not any((v or "").strip() for v in row.values()):
            continue
        rec = mapper(row)
        if not rec.get("name"):
            continue
        rec["draft"] = True
        rec["source_listing"] = rec.get("sku") or rec.get("listing_id") or rec.get("name")
        products.append(rec)
    return platform, headers, products


def run(client_dir):
    cdir = Path(client_dir)
    csv_path = cdir / "02-intake" / "marketplace-export.csv"
    assets_dir = cdir / "02-intake" / "assets"
    if not csv_path.exists():
        return {"ok": False, "error": "no marketplace-export.csv in 02-intake/ yet"}

    # provenance from status.json (source/owner), falling back to the detected platform
    source, owner = "", ""
    try:
        st = json.loads((cdir / "status.json").read_text())
        cat = st.get("catalog", {}) or {}
        source, owner = cat.get("source", ""), cat.get("owner", "")
    except Exception:
        pass

    platform, headers, products = parse_csv(csv_path)
    if not source:
        source = f"{platform}-export"
    if not owner:
        owner = "self"
    assets, unmatched = match_photos(products, assets_dir)

    out = {
        "platform": platform, "source": source, "owner": owner,
        "csv": csv_path.name, "extracted_count": len(products), "products": products,
    }
    (cdir / "01-baseline").mkdir(parents=True, exist_ok=True)
    (cdir / "01-baseline" / "catalog-draft.json").write_text(json.dumps(out, indent=2))

    with_photo = sum(1 for p in products if p.get("photo"))
    return {
        "ok": True, "platform": platform, "source": source, "owner": owner,
        "csv": csv_path.name, "headers": headers,
        "products": len(products), "with_photo": with_photo,
        "products_without_photo": [p["name"] for p in products if not p.get("photo")],
        "unmatched_photos": unmatched, "assets_total": len(assets),
        "match_breakdown": {k: sum(1 for p in products if p.get("photo_match") == k)
                            for k in ("sku", "listing-id", "filename")},
        "draft": True,
    }


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(json.dumps({"ok": False, "error": "usage: marketplace_import.py <client_dir>"}))
        sys.exit(2)
    summary = run(args[0])
    print(json.dumps(summary))
    sys.exit(0 if summary.get("ok") else 1)
