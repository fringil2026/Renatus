#!/usr/bin/env python3
"""Generate correspondence QA data: for each built product, pull the TRUTH from its source page
(raw <title>, meta genus/species, and the real product-cover <img> alt+src) so a human can eyeball
every name<->photo pairing at once. Writes src/data/_qa.json for the temporary /_qa/ page.
Read-only on the mirror. Usage: python3 qa_correspondence.py <client_dir>
"""
import json, re, sys
from pathlib import Path

TITLE = re.compile(r"<title>\s*(.*?)\s*</title>", re.I | re.S)
META_GS = re.compile(r"orchid\s+genus:\s*([A-Za-z()\- ]+?)\s*,\s*orchid\s+species:\s*([A-Za-z0-9'’.\- ]+)", re.I)
COVER = re.compile(r'<img[^>]*js-product-cover[^>]*>', re.I)
SRC = re.compile(r'src="([^"]+)"', re.I)
ALT = re.compile(r'alt="([^"]*)"', re.I)


def main():
    client = Path(sys.argv[1]).resolve()
    mirror = client / "00-source" / "mirror" / "andysorchids.com"
    data = json.loads((client / "03-site" / "src" / "data" / "products.json").read_text())
    rows = []
    for p in data["products"]:
        sp = p.get("source_page", "")
        title = meta = cover_src = cover_alt = ""
        if sp and (mirror / sp).exists():
            html = (mirror / sp).read_text(errors="ignore")
            m = TITLE.search(html)
            title = (m.group(1).strip() if m else "")[:120]
            g = META_GS.search(html)
            meta = f"{g.group(1).strip()} {g.group(2).strip()}" if g else "(no genus/species meta)"
            c = COVER.search(html)
            if c:
                s = SRC.search(c.group(0)); a = ALT.search(c.group(0))
                cover_src = s.group(1) if s else ""
                cover_alt = a.group(1) if a else ""
        rows.append({
            "id": p["id"],
            "our_name": f"{p['genus']} {p['species']} — {p['common_name']}",
            "our_photo": p["photos"][0] if p.get("photos") else "",
            "source_page": sp,
            "source_title": title,
            "source_meta": meta,
            "cover_src": cover_src,      # the TRUE main image on the source page
            "cover_alt": cover_alt,      # the TRUE product name on the source page
        })
    out = client / "03-site" / "src" / "data" / "_qa.json"
    out.write_text(json.dumps({"products": rows}, indent=2, ensure_ascii=False) + "\n")
    print(f"qa_correspondence: wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
