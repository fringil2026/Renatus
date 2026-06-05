#!/usr/bin/env python3
"""Method 2 — headless browser capture (optional; needs `pip install playwright`
+ `playwright install chromium`). Renders JS, takes full-page screenshots at
desktop+mobile widths, samples computed styles, logs network endpoints.

Usage: python3 render_capture.py <client_dir> [max_pages]
Reads 00-source/crawl.json for the URL list; writes 00-source/rendered/.
Degrades gracefully if playwright is missing.
"""
import json, sys
from pathlib import Path
from urllib.parse import urlparse

def main():
    client = Path(sys.argv[1])
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    outdir = client / "00-source" / "rendered"
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        (outdir / "SKIPPED.txt").write_text(
            "playwright not installed.\npip install playwright && playwright install chromium")
        print("render: playwright not installed — skipped (method 2)")
        return
    crawl = json.loads((client / "00-source" / "crawl.json").read_text())
    urls = [p["url"] for p in crawl["pages"] if p.get("status") == 200][:max_pages]
    data = {"urls": [], "endpoints": [], "computed_colors": [], "computed_fonts": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for vp, label in [({"width": 1440, "height": 900}, "desktop"),
                          ({"width": 390, "height": 844}, "mobile")]:
            page = browser.new_page(viewport=vp)
            reqs = []
            page.on("request", lambda r: reqs.append({"url": r.url, "method": r.method,
                                                      "type": r.resource_type}))
            for u in urls:
                slug = (urlparse(u).path.strip("/").replace("/", "_") or "home")
                try:
                    page.goto(u, wait_until="networkidle", timeout=30000)
                    page.screenshot(path=str(outdir / f"{slug}-{label}.png"), full_page=True)
                    if label == "desktop":
                        data["urls"].append(page.url)
                        styles = page.evaluate("""() => {
                          const out = {colors:new Set(), fonts:new Set()};
                          for (const el of document.querySelectorAll('body, h1, h2, h3, p, a, button, header, footer, nav')) {
                            const s = getComputedStyle(el);
                            out.colors.add(s.color); out.colors.add(s.backgroundColor);
                            out.fonts.add(s.fontFamily.split(',')[0].replace(/['"]/g,'').trim());
                          }
                          return {colors:[...out.colors], fonts:[...out.fonts]};
                        }""")
                        data["computed_fonts"] += styles["fonts"]
                        for c in styles["colors"]:
                            if c.startswith("rgb") and "0, 0, 0, 0" not in c:
                                vals = [int(x) for x in c[c.find("(")+1:c.find(")")].split(",")[:3]]
                                data["computed_colors"].append("#%02x%02x%02x" % tuple(vals))
                except Exception as e:
                    data.setdefault("errors", []).append(f"{u} [{label}]: {str(e)[:120]}")
            xhr = [r for r in reqs if r["type"] in ("xhr", "fetch")]
            data["endpoints"] += xhr
            page.close()
        browser.close()
    data["computed_fonts"] = sorted(set(data["computed_fonts"]))
    data["computed_colors"] = sorted(set(data["computed_colors"]))
    seen = set()
    data["endpoints"] = [e for e in data["endpoints"]
                         if not (e["url"] in seen or seen.add(e["url"]))][:80]
    (outdir / "render.json").write_text(json.dumps(data, indent=1))
    print(f"render: {len(data['urls'])} pages, {len(data['endpoints'])} endpoints -> {outdir}")

if __name__ == "__main__":
    main()
