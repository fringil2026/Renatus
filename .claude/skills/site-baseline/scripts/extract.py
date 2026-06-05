#!/usr/bin/env python3
"""Merge scrape outputs into 01-baseline/ deliverables.

Inputs : 00-source/crawl.json (method 1, required)
         00-source/mirror/    (method 3, optional wget archive)
         00-source/rendered/render.json (method 2, optional playwright)
Outputs: 01-baseline/url-inventory.csv, content-draft.md, tokens-draft.json,
         metadata-audit.md, tech-fingerprint.md, coverage.md

Usage: python3 extract.py <client_dir>
"""
import csv, json, re, sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests

FINGERPRINTS = [
    ("WordPress", r"wp-content|wp-includes|/wp-json"),
    ("Wix", r"wixstatic\.com|wix-code"),
    ("Squarespace", r"squarespace\.com|sqsp\.net"),
    ("Webflow", r"webflow\.(io|com)|wf-"),
    ("Shopify", r"cdn\.shopify\.com|myshopify"),
    ("Drupal", r"/sites/default/files|drupal"),
    ("Google Analytics 4", r"gtag\(|googletagmanager\.com/gtag|G-[A-Z0-9]{6,}"),
    ("Google Tag Manager", r"googletagmanager\.com/gtm"),
    ("Universal Analytics (legacy)", r"UA-\d{4,}-\d"),
    ("Meta Pixel", r"connect\.facebook\.net|fbq\("),
    ("LinkedIn Insight", r"snap\.licdn\.com"),
    ("HubSpot", r"js\.hs-scripts\.com|hubspot"),
    ("Mailchimp", r"chimpstatic|list-manage\.com"),
    ("Calendly", r"calendly\.com"),
    ("Intercom", r"intercom(cdn)?\.com"),
    ("reCAPTCHA", r"google\.com/recaptcha"),
    ("Cloudflare Turnstile", r"challenges\.cloudflare\.com"),
    ("jQuery", r"jquery"),
    ("React", r"react(-dom)?(\.production)?\.min\.js|__NEXT_DATA__|data-reactroot"),
]

HEX = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
FONT = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)

def path_of(u):
    p = urlparse(u).path or "/"
    p = re.sub(r"/index\.html$", "/", p)
    p = re.sub(r"\.html?$", "", p)
    return p if p == "/" else (p.rstrip("/") or "/")

def load(client):
    crawl = json.loads((client / "00-source" / "crawl.json").read_text())
    rendered = None
    rp = client / "00-source" / "rendered" / "render.json"
    if rp.exists():
        try:
            rendered = json.loads(rp.read_text())
        except Exception:
            pass
    mirror_paths = set()
    mdir = client / "00-source" / "mirror"
    if mdir.exists():
        for f in mdir.rglob("*.html"):
            rel = "/" + "/".join(f.relative_to(mdir).parts[1:])  # drop host dir
            rel = re.sub(r"/index\.html$", "", rel) or "/"
            rel = re.sub(r"\.html$", "", rel)
            mirror_paths.add(rel if rel == "/" else rel.rstrip("/"))
    return crawl, rendered, mirror_paths

def write_inventory(out, pages):
    with open(out / "url-inventory.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "status", "redirected", "noindex", "canonical",
                    "title", "meta_description", "h1", "word_count"])
        for p in pages:
            w.writerow([p.get("url"), p.get("status"), p.get("redirected", ""),
                        p.get("noindex", ""), p.get("canonical", ""),
                        p.get("title", ""), p.get("meta_description", ""),
                        " | ".join(p.get("h1", [])), p.get("word_count", "")])

def write_content(out, pages):
    L = ["# Content Draft — scraped, UNVERIFIED (ownership unconfirmed; treat as DRAFT)", ""]
    for p in pages:
        if p.get("status") != 200 or not p.get("text"):
            continue
        L += [f"## {path_of(p['url'])}", f"title: {p.get('title','')}"]
        for h in p.get("h1", []):
            L.append(f"h1: {h}")
        L += ["", p["text"][:1800], ""]
        for fm in p.get("forms", []):
            L.append(f"[form -> {fm['action']} ({fm['method']}) fields: {', '.join(fm['fields'])}]")
        L.append("")
    (out / "content-draft.md").write_text("\n".join(L))

def write_tokens(out, pages, rendered):
    colors, fonts = Counter(), Counter()
    css_urls = {u for p in pages for u in (p.get("stylesheets") or []) if u}
    for u in list(css_urls)[:12]:
        try:
            css = requests.get(u, timeout=10).text
        except Exception:
            continue
        for c in HEX.findall(css):
            colors[c.lower()] += 1
        for fam in FONT.findall(css):
            f = fam.split(",")[0].strip().strip("'\"")
            if f and not f.startswith("var("):
                fonts[f] += 1
    if rendered:  # computed styles from method 2 win where present
        for c in rendered.get("computed_colors", []):
            colors[c.lower()] += 5
        for f in rendered.get("computed_fonts", []):
            fonts[f] += 5
    drop = {"#fff", "#ffffff", "#000", "#000000", "transparent"}
    palette = [c for c, _ in colors.most_common(20) if c not in drop][:8]
    (out / "tokens-draft.json").write_text(json.dumps({
        "_comment": "DRAFT — extracted from the existing site. Verify/refresh before applying.",
        "palette_by_frequency": palette,
        "all_colors_seen": dict(colors.most_common(25)),
        "fonts_by_frequency": [f for f, _ in fonts.most_common(8)],
    }, indent=2))

def write_metadata_audit(out, crawl, pages):
    L = ["# Metadata & SEO Audit (automated)", ""]
    rb = crawl["extras"].get("/robots.txt", {})
    sm = crawl["extras"].get("/sitemap.xml", {})
    L.append(f"robots.txt: status {rb.get('status')}"
             + (" — contains 'Disallow: /' (!)" if "disallow: /" in rb.get("body", "").lower() else ""))
    L.append(f"sitemap.xml: status {sm.get('status')}")
    noindexed = [p["url"] for p in pages if p.get("noindex")]
    L.append(f"pages with noindex: {len(noindexed)}" + (f" -> {noindexed[:5]}" if noindexed else ""))
    no_desc = [path_of(p["url"]) for p in pages if p.get("status") == 200 and not p.get("meta_description")]
    L.append(f"pages missing meta description: {len(no_desc)} {no_desc[:8]}")
    no_canon = sum(1 for p in pages if p.get("status") == 200 and not p.get("canonical"))
    L.append(f"pages missing canonical: {no_canon}")
    og_home = next((p.get("og", {}) for p in pages if path_of(p.get("url", "")) == "/"), {})
    L.append(f"homepage OG tags: {sorted(og_home.keys()) or 'NONE'}")
    types = sorted({t for p in pages for t in p.get("jsonld_types", [])})
    L.append(f"JSON-LD types found site-wide: {types or 'NONE'}")
    hre = sorted({h for p in pages for h in p.get("hreflang", [])})
    if hre:
        L.append(f"hreflang present: {hre}")
    bad = [(p["url"], p["status"]) for p in pages if p.get("status") not in (200, None) or p.get("error")]
    L.append(f"non-200 / errored URLs: {len(bad)}")
    for u, s in bad[:15]:
        L.append(f"  {s}  {u}")
    missing_alt = sum(1 for p in pages for i in p.get("images", []) if not i.get("alt"))
    L.append(f"images missing alt text (sampled): {missing_alt}")
    (out / "metadata-audit.md").write_text("\n".join(L))

def write_fingerprint(out, pages):
    blob = " ".join((" ".join(p.get("scripts") or []) + " " + p.get("inline_scripts_sample", "")
                     + " " + " ".join(p.get("stylesheets") or [])) for p in pages)[:400000]
    hits = [name for name, pat in FINGERPRINTS if re.search(pat, blob, re.I)]
    ga4 = sorted(set(re.findall(r"\bG-[A-Z0-9]{6,12}\b", blob)))
    L = ["# Tech Fingerprint (automated)", "",
         "Detected: " + (", ".join(hits) if hits else "nothing recognized"), ""]
    if ga4:
        L.append(f"GA4 measurement ID(s) seen: {ga4}  <- carry this property forward")
    forms = [(path_of(p["url"]), f) for p in pages for f in p.get("forms", [])]
    L.append(f"forms found: {len(forms)}")
    for path, f in forms[:10]:
        L.append(f"  {path}: {f['method']} -> {f['action']} (fields: {', '.join(f['fields'][:8])})")
    L += ["", "Questions this generates for the owner: account ownership for each detected service."]
    (out / "tech-fingerprint.md").write_text("\n".join(L))

def write_coverage(out, crawl, rendered, mirror_paths):
    crawl_paths = {path_of(p["url"]) for p in crawl["pages"] if p.get("status") == 200}
    sets = {"crawler (method 1)": crawl_paths}
    if mirror_paths:
        sets["wget mirror (method 3)"] = mirror_paths
    if rendered and rendered.get("urls"):
        sets["rendered browser (method 2)"] = {path_of(u) for u in rendered["urls"]}
    union = set().union(*sets.values())
    L = ["# Cross-Method Coverage", "",
         f"union of all methods: {len(union)} unique paths", ""]
    for name, s in sets.items():
        L.append(f"{name}: {len(s)} paths")
    for name, s in sets.items():
        only = sorted(union - s)
        if only:
            L += ["", f"MISSED by {name} ({len(only)}):"] + [f"  {p}" for p in only[:20]]
    if len(sets) == 1:
        L += ["", "NOTE: only method 1 ran — install wget and/or playwright for cross-validation."]
    (out / "coverage.md").write_text("\n".join(L))

def main():
    client = Path(sys.argv[1])
    out = client / "01-baseline"
    out.mkdir(parents=True, exist_ok=True)
    crawl, rendered, mirror_paths = load(client)
    pages = crawl["pages"]
    write_inventory(out, pages)
    write_content(out, pages)
    write_tokens(out, pages, rendered)
    write_metadata_audit(out, crawl, pages)
    write_fingerprint(out, pages)
    write_coverage(out, crawl, rendered, mirror_paths)
    print(f"extract: baseline written -> {out}")

if __name__ == "__main__":
    main()
