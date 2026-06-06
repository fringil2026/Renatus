#!/usr/bin/env python3
"""Resolve each product photo to its LARGEST available variant in the mirror, measure pixel
dimensions, copy it into the site, and flag any image below its slot minimum (design rule 4).
Records largest_variant + dimensions back into products.json. Read-only on the mirror.

Slot minimums: hero >= 1600px wide, card >= 600px wide.
Usage: python3 resolve_images.py <client_dir> [hero_slug]
"""
import json, re, shutil, sys
from pathlib import Path

VARIANTS = ["lrg", "Lrg", "LRG", "med", "Med", "MED", "sm", "Sm"]
CARD_MIN, HERO_MIN = 600, 1600


def jpeg_size(path: Path):
    try:
        data = path.read_bytes()
    except Exception:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return (w, h)
        if 0xD0 <= marker <= 0xD9 or marker == 0x01:
            i += 2
            continue
        seglen = int.from_bytes(data[i + 2:i + 4], "big")
        i += 2 + seglen
    return None


def candidates(mirror_root: Path, picid: str):
    out = []
    for size in VARIANTS:
        for sep in ("\\", "/"):
            c = mirror_root / f"images{sep}species{sep}{picid}{size}.jpg"
            if c.exists():
                out.append((size.lower(), c))
    return out


def main():
    client = Path(sys.argv[1]).resolve()
    hero_slug = sys.argv[2] if len(sys.argv) > 2 else None
    mirror_root = client / "00-source" / "mirror" / "andysorchids.com"
    dest_dir = client / "03-site" / "public" / "specimens"
    dest_dir.mkdir(parents=True, exist_ok=True)
    data_path = client / "03-site" / "src" / "data" / "products.json"
    data = json.loads(data_path.read_text())

    upgraded, rejected, report = 0, [], []
    for i, prod in enumerate(data["products"]):
        if not prod.get("photos"):
            continue
        picid = Path(prod["photos"][0]).stem
        cands = candidates(mirror_root, picid)
        best, best_w, best_variant = None, -1, None
        for variant, path in cands:
            sz = jpeg_size(path)
            if sz and sz[0] > best_w:
                best, best_w, best_variant = path, sz[0], variant
        if not best:
            continue
        sz = jpeg_size(best)
        shutil.copyfile(best, dest_dir / f"{picid}.jpg")
        is_hero = (hero_slug and prod["slug"] == hero_slug) or (hero_slug is None and i == 0)
        slot_min = HERO_MIN if is_hero else CARD_MIN
        ok = sz[0] >= slot_min
        if best_variant != "med":
            upgraded += 1
        prod["largest_variant"] = f"{picid}{best_variant}.jpg"
        prod["photo_px"] = [sz[0], sz[1]]
        prod["photo_slot_ok"] = ok
        if not ok:
            rejected.append((prod["id"], prod["slug"], sz, "HERO" if is_hero else "card", slot_min))
        report.append(f"{prod['id']:12} {best_variant:3} {sz[0]}x{sz[1]} {'HERO' if is_hero else 'card'} {'OK' if ok else 'UNDER-MIN'}")

    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"resolve_images: {len(data['products'])} products · upgraded-to-largest {upgraded} · under-min {len(rejected)}")
    for line in report:
        print("  " + line)
    if rejected:
        print("UNDER MINIMUM (flag photography ask, deliverable D-2.7.4):")
        for pid, slug, sz, slot, m in rejected:
            print(f"  {pid} ({slug}) {sz[0]}x{sz[1]} < {slot} min {m}px")


if __name__ == "__main__":
    main()
