#!/usr/bin/env python3
"""Feature census — detect the macro-features of an existing site from EXISTING 00-source
(no re-scrape) and classify each for the rebuild. Reads crawl.json (forms/scripts/links/urls)
and, if present, the wget mirror's filenames. Read-only; no network.

Each detected feature is classified:
  CARRY-OVER  — static-feasible; MUST appear in the prototype.
  STUB+FLAG   — needs a backend or client input; ship a visible honest stub + add an unblock
                fact to the deliverables request (§2.7).
  OBSOLETE    — recommend dropping, with a reason.

Output: <client>/01-baseline/feature-census.md
Usage:  python3 feature_census.py <client_dir>
Also called by run_baseline.py after extract.
"""
import json, re, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def load_evidence(client: Path):
    crawl = json.loads((client / "00-source" / "crawl.json").read_text())
    pages = crawl.get("pages", [])
    paths, form_actions, query_keys, scripts = set(), set(), set(), []
    text_blob = []
    for p in pages:
        u = urlparse(p.get("url", ""))
        paths.add((u.path or "/").lower())
        for k in parse_qs(u.query):
            query_keys.add(k.lower())
        for f in p.get("forms", []):
            form_actions.add((f.get("action") or "").lower())
            for fld in f.get("fields", []):
                query_keys.add(str(fld).lower())
        scripts += [s.lower() for s in (p.get("scripts") or [])]
        scripts.append((p.get("inline_scripts_sample") or "").lower())
        if p.get("text"):
            text_blob.append(p["text"][:500].lower())
    mirror = client / "00-source" / "mirror"
    mirror_names = ""
    if mirror.exists():
        mirror_names = " ".join(f.name.lower() for f in mirror.rglob("*.html"))
    return {
        "paths": paths,
        "form_actions": " ".join(form_actions),
        "query_keys": query_keys,
        "scripts": " ".join(scripts),
        "text": " ".join(text_blob),
        "mirror_names": mirror_names,
        "n_forms": sum(len(p.get("forms", [])) for p in pages),
    }


def has_path(ev, *needles):
    return any(any(n in p for p in ev["paths"]) for n in needles)


# (name, detect(ev)->evidence_str|None, class, static_feasible, unblock, recommendation)
def build_features():
    def search(ev):
        if "search" in ev["form_actions"] or "quicksearch" in ev["mirror_names"] or has_path(ev, "searchresults", "powersearch"):
            return f"search forms ({ev['n_forms']} forms; quicksearch/searchresults present)"
        return None

    def filt(ev):
        keys = ev["query_keys"] & {"sort", "sorter", "offset", "alpha", "family", "genus", "species", "country"}
        if keys:
            return f"filter/sort params: {', '.join(sorted(keys))}"
        return None

    def pag(ev):
        if ev["query_keys"] & {"page", "offset"}:
            return "pagination params: page/offset"
        return None

    def catnav(ev):
        if has_path(ev, "category", "genlist", "famlist", "gclist"):
            return "category/genus index pages (category/genlist/famlist/gclist)"
        return None

    def cart(ev):
        return "cart.asp present" if has_path(ev, "cart.asp") else None

    def checkout(ev):
        return "checkout flow present" if has_path(ev, "checkout", "ordrinfo") else None

    def login(ev):
        return "login/account pages (login.asp/forgot.asp)" if has_path(ev, "login.asp", "forgot.asp", "maintinfo", "orderlist") else None

    def wishlist(ev):
        return "wishlist present" if has_path(ev, "wishlist", "wishfind") else None

    def reviews(ev):
        return "review content present" if ("review" in ev["text"] and "reviews" in ev["text"]) else None

    def newsletter(ev):
        if "newsletter" in ev["text"] or "subscribe" in ev["form_actions"] or "mailing list" in ev["text"]:
            return "newsletter/subscribe signal"
        return None

    def contact(ev):
        return "contact page present" if has_path(ev, "contact") else None

    def compare(ev):
        return "product compare present" if has_path(ev, "compare") else None

    def pixel(ev):
        hits = [n for n in ("facebook", "fbq", "connect.facebook", "gtag", "googletagmanager") if n in ev["scripts"]]
        return f"tracking/pixel scripts: {', '.join(hits)}" if hits else None

    return [
        ("Site search",          search,    "CARRY-OVER", True,  "",        "Reimplement as client-side search over the catalog."),
        ("Filter / sort",        filt,      "CARRY-OVER", True,  "",        "Genus/care/bloom filters + sort, client-side."),
        ("Pagination",           pag,       "CARRY-OVER", True,  "",        "Static pagination or lazy reveal over the grid."),
        ("Category / genus nav", catnav,    "CARRY-OVER", True,  "",        "Genus filter chips + per-genus care pages."),
        ("Contact form",         contact,   "STUB+FLAG",  True,  "D-2.3.1", "Static form UI; wire to the owner's inbox/handler."),
        ("Cart",                 cart,      "STUB+FLAG",  False, "D-2.7.1", "Cart UI now; live at checkout phase (Stripe)."),
        ("Checkout",             checkout,  "STUB+FLAG",  False, "D-2.7.1", "Hosted Stripe Checkout; needs the owner's account."),
        ("Accounts / login",     login,     "STUB+FLAG",  False, "D-2.7.2", "Auth via the data backend (Supabase); needs project."),
        ("Wishlist",             wishlist,  "STUB+FLAG",  False, "D-2.7.2", "Account-bound; ships after auth."),
        ("Newsletter signup",    newsletter,"STUB+FLAG",  True,  "D-2.7.3", "Capture UI now; sends once email infra (Resend) is verified."),
        ("Tracking pixels",      pixel,     "STUB+FLAG",  True,  "D-2.4.4", "Re-add behind a consent banner; needs pixel-account access."),
        ("Product reviews",      reviews,   "OBSOLETE",   False, "",        "Not present / low value at this catalog size; revisit later."),
        ("Product compare",      compare,   "OBSOLETE",   True,  "",        "Low-value on a specialist catalog; drop in favor of search + care guides."),
    ]


def main():
    client = Path(sys.argv[1]).resolve()
    ev = load_evidence(client)
    rows = []
    for name, detect, klass, static, unblock, rec in build_features():
        evidence = detect(ev)
        if evidence:
            rows.append((name, evidence, klass, static, unblock, rec))

    counts = {"CARRY-OVER": 0, "STUB+FLAG": 0, "OBSOLETE": 0}
    for r in rows:
        counts[r[2]] += 1

    L = ["# Feature Census — detected from existing 00-source (no re-scrape)", "",
         f"Detected {len(rows)} macro-features · "
         f"CARRY-OVER {counts['CARRY-OVER']} · STUB+FLAG {counts['STUB+FLAG']} · OBSOLETE {counts['OBSOLETE']}", "",
         "| Feature | Evidence | Class | Static-feasible | Unblock (deliverable) | Recommendation |",
         "|---|---|---|---|---|---|"]
    for name, evidence, klass, static, unblock, rec in rows:
        L.append(f"| {name} | {evidence} | **{klass}** | {'yes' if static else 'no'} | {unblock or '—'} | {rec} |")
    L += ["",
          "## How to read this",
          "- **CARRY-OVER** features MUST appear in the prototype (parity floor; additions come on top).",
          "- **STUB+FLAG** features get a visible, honest stub in the prototype and an unblock fact in",
          "  `02-intake/deliverables-request.md` §2.7 (cross-referenced above).",
          "- **OBSOLETE** features are recommended for removal with the reason given — confirm with the human."]
    out = client / "01-baseline" / "feature-census.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print(f"feature-census: {len(rows)} features "
          f"(CARRY-OVER {counts['CARRY-OVER']}, STUB+FLAG {counts['STUB+FLAG']}, OBSOLETE {counts['OBSOLETE']}) -> {out}")


if __name__ == "__main__":
    main()
