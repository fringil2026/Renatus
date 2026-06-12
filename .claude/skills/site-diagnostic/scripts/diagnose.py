#!/usr/bin/env python3
"""Site diagnostic capture — the MEASURABLE half of the outreach diagnostic engine.

One URL in -> evidence out. Captures rendered desktop + 390px screenshots, runs a
bounded polite mini-crawl, fetches CSS, measures every objective Axis-1 signal
(responsive, HTTPS, performance, dated-tech tells, a11y basics) and aggregates the
raw Axis-2 industry-completeness signals. It NEVER judges aesthetics and NEVER
invents a deficiency: every finding carries its evidence string, and ambiguous
signals are reported as ambiguous (the model phrases those carefully or drops them).

Usage:
  python3 diagnose.py <url> <out_dir> [--max-pages N] [--skip-psi]

Writes:
  <out_dir>/capture/home-desktop.png      full-page render, 1440x900 viewport
  <out_dir>/capture/home-mobile-390.png   full-page render, 390x844 viewport
  <out_dir>/capture/home.html             rendered homepage HTML (post-JS)
  <out_dir>/diagnostic.json               every measurement + evidence
  <out_dir>/MEASURABLES.md                human-readable summary

Exit 0 even on partial capture (the JSON records what failed); exit 2 only when
the site was completely unreachable by every method.
"""
import json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent.parent / "site-baseline" / "scripts"))
from crawl import crawl as mini_crawl   # reuse the baseline BFS crawler (polite, same-host)

UA_CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
NOW_YEAR = datetime.now(timezone.utc).year

# Stack fingerprints (superset of extract.py's list + dated-platform tells).
FINGERPRINTS = [
    ("WordPress", r"wp-content|wp-includes|/wp-json"),
    ("Wix", r"wixstatic\.com|wix-code"),
    ("Squarespace", r"squarespace\.com|sqsp\.net"),
    ("Webflow", r"webflow\.(io|com)|wf-"),
    ("Shopify", r"cdn\.shopify\.com|myshopify"),
    ("Drupal", r"/sites/default/files|drupal"),
    ("Google Analytics 4", r"gtag\(|googletagmanager\.com/gtag|G-[A-Z0-9]{6,}"),
    ("Google Tag Manager", r"googletagmanager\.com/gtm"),
    ("Universal Analytics (legacy, dead since 2023)", r"UA-\d{4,}-\d"),
    ("Meta Pixel", r"connect\.facebook\.net|fbq\("),
    ("jQuery", r"jquery"),
    ("React", r"react(-dom)?(\.production)?\.min\.js|__NEXT_DATA__|data-reactroot"),
    ("Volusion", r"volusion\.com|/v/vspfiles"),
    ("Miva", r"mivamerchant|/mm5/"),
    ("3dcart/Shift4Shop", r"3dcart|shift4shop"),
    ("osCommerce", r"oscommerce|osCsid"),
    ("Zen Cart", r"zen-cart|zencart"),
    ("GoDaddy Website Builder", r"wsimg\.com|godaddy"),
    ("Google Sites", r"sites\.google\.com|googleusercontent\.com/sitesv"),
    ("Adobe Flash (dead since 2020)", r"\.swf[\"'?]|shockwave-flash"),
]
DATED_GENERATORS = r"frontpage|dreamweaver|microsoft word|publisher|netobjects|golive|claris|webplus|coffeecup|sitebuilder|homestead"


def _ev(value, evidence, confidence="high"):
    return {"value": value, "evidence": evidence, "confidence": confidence}


def fetch(url, timeout=20, verify=True):
    return requests.get(url, timeout=timeout, verify=verify,
                        headers={"User-Agent": UA_CHROME}, allow_redirects=True)


# ---------------- HTTPS ----------------
def check_https(domain):
    out = {"https_ok": None, "cert_valid": None, "http_redirects_to_https": None, "notes": []}
    try:
        r = fetch(f"https://{domain}")
        out["https_ok"] = r.status_code < 500
        out["cert_valid"] = True
        out["final_url"] = r.url
    except requests.exceptions.SSLError as e:
        out["https_ok"] = False
        out["cert_valid"] = False
        out["notes"].append(f"SSL error: {str(e)[:160]}")
        try:
            r = fetch(f"https://{domain}", verify=False)
            out["https_reachable_insecure"] = True
        except Exception:
            pass
    except Exception as e:
        out["https_ok"] = False
        out["notes"].append(f"https fetch failed: {str(e)[:160]}")
    try:
        r = fetch(f"http://{domain}")
        out["http_redirects_to_https"] = urlparse(r.url).scheme == "https"
        out["http_final_url"] = r.url
    except Exception as e:
        out["notes"].append(f"http fetch failed: {str(e)[:160]}")
    return out


# ---------------- rendered capture (hardened Playwright) ----------------
def render_homepage(url, capdir):
    """Desktop + 390px full-page screenshots, rendered HTML, in-page measurements,
    network weight. Hardened context (real-Chrome UA, webdriver hidden) so a
    Cloudflare-fronted site doesn't read as 'broken'. Returns {} if playwright missing."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"error": "playwright not installed", "captured": False}
    out = {"captured": False, "challenge_suspected": False}
    CHALLENGE = re.compile(r"just a moment|attention required|checking your browser|enable javascript and cookies", re.I)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        try:
            for label, vp in (("desktop", {"width": 1440, "height": 900}),
                              ("mobile-390", {"width": 390, "height": 844})):
                ctx = browser.new_context(viewport=vp, user_agent=UA_CHROME, locale="en-US",
                                          timezone_id="America/Los_Angeles",
                                          device_scale_factor=2)
                ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
                page = ctx.new_page()
                nreq, nbytes = [0], [0]
                page.on("request", lambda r: nreq.__setitem__(0, nreq[0] + 1))
                page.on("response", lambda r: nbytes.__setitem__(0, nbytes[0] + int(r.headers.get("content-length") or 0)))
                t0 = time.time()
                try:
                    page.goto(url, wait_until="load", timeout=45000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                except Exception as e:
                    out.setdefault("errors", []).append(f"{label}: goto failed: {str(e)[:160]}")
                    page.close(); ctx.close()
                    continue
                # challenge interstitials sometimes clear after a beat — give them one
                if CHALLENGE.search(page.title() or ""):
                    page.wait_for_timeout(8000)
                    if CHALLENGE.search(page.title() or ""):
                        out["challenge_suspected"] = True
                load_s = round(time.time() - t0, 1)
                page.screenshot(path=str(capdir / f"home-{label}.png"), full_page=True)
                m = page.evaluate("""() => ({
                    title: document.title,
                    scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth,
                    bodyFontPx: parseFloat(getComputedStyle(document.body).fontSize) || null,
                })""")
                out[label] = {"load_seconds": load_s, "requests": nreq[0],
                              "bytes_seen": nbytes[0], **m}
                if label == "desktop":
                    (capdir / "home.html").write_text(page.content(), errors="replace")
                    out["rendered_title"] = m["title"]
                    out["fonts"] = page.evaluate("""() => {
                        const f = new Set();
                        for (const el of document.querySelectorAll('body,h1,h2,h3,p,a,button,nav'))
                            f.add(getComputedStyle(el).fontFamily.split(',')[0].replace(/['"]/g,'').trim());
                        return [...f];
                    }""")
                    out["contrast_samples"] = page.evaluate("""() => {
                        const out = [];
                        for (const el of document.querySelectorAll('p,a,li,h1,h2,h3,span,td')) {
                            if (out.length >= 40) break;
                            const direct = [...el.childNodes].some(c => c.nodeType === 3 && c.textContent.trim().length > 10);
                            if (!direct) continue;
                            const s = getComputedStyle(el);
                            let bg = 'rgba(0, 0, 0, 0)', n = el, overImage = false;
                            while (n && n !== document.documentElement) {
                                const cs = getComputedStyle(n);
                                if (cs.backgroundImage && cs.backgroundImage !== 'none') overImage = true;
                                if (n.querySelector && n !== el && n.querySelector(':scope > img, :scope > picture, :scope > video')) overImage = true;
                                const b = cs.backgroundColor;
                                if (b && !b.includes('0, 0, 0, 0')) { bg = b; break; }
                                n = n.parentElement;
                            }
                            if (bg.includes('0, 0, 0, 0')) bg = 'rgb(255, 255, 255)';
                            out.push({color: s.color, bg, overImage, sizePx: parseFloat(s.fontSize),
                                      bold: parseInt(s.fontWeight) >= 700,
                                      text: el.textContent.trim().slice(0, 50)});
                        }
                        return out;
                    }""")
                out["captured"] = True
                page.close(); ctx.close()
        finally:
            browser.close()
    return out


def _rgb(c):
    m = re.findall(r"[\d.]+", c or "")
    return [float(x) for x in m[:3]] if len(m) >= 3 else None


def contrast_ratio(fg, bg):
    def lum(rgb):
        ch = []
        for c in rgb:
            c /= 255.0
            ch.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def contrast_report(samples):
    fails, checked, over_image = [], 0, 0
    for s in samples or []:
        fg, bg = _rgb(s.get("color")), _rgb(s.get("bg"))
        if not fg or not bg:
            continue
        if s.get("overImage"):
            over_image += 1   # text over an image — computed-color contrast is unscorable, never "failing"
            continue
        checked += 1
        ratio = contrast_ratio(fg, bg)
        large = s.get("sizePx", 16) >= 24 or (s.get("sizePx", 16) >= 18.66 and s.get("bold"))
        if ratio < (3.0 if large else 4.5):
            fails.append({"text": s.get("text", "")[:40], "ratio": round(ratio, 2),
                          "color": s.get("color"), "bg": s.get("bg")})
    return {"checked": checked, "failing": len(fails), "skipped_over_image": over_image,
            "worst": sorted(fails, key=lambda f: f["ratio"])[:5]}


# ---------------- static HTML/CSS analysis ----------------
def analyze_html(html, base_url, session_https):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    vp = soup.find("meta", attrs={"name": "viewport"})
    out["viewport_meta"] = _ev(bool(vp), (vp.get("content", "") if vp else "no <meta name=viewport> in homepage HTML"))
    out["html_lang"] = _ev(bool(soup.html and soup.html.get("lang")),
                           f"<html lang={soup.html.get('lang')!r}>" if soup.html and soup.html.get("lang") else "no lang attribute")
    first = html[:200].lower()
    out["doctype_html5"] = _ev(first.lstrip().startswith("<!doctype html>"),
                               first.strip().split("\n")[0][:80])
    gen = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    out["generator_meta"] = (gen.get("content", "") if gen else "")
    out["dated_generator"] = bool(re.search(DATED_GENERATORS, out["generator_meta"], re.I))

    # dated markup tells
    tells = {}
    for tag in ("font", "center", "marquee", "frameset", "frame", "blink"):
        n = len(soup.find_all(tag))
        if n:
            tells[f"<{tag}>"] = n
    swf = len(re.findall(r"\.swf[\"'?]", html, re.I))
    if swf:
        tells["flash .swf refs"] = swf
    tables = soup.find_all("table")
    layoutish = [t for t in tables if t.get("cellpadding") or t.get("cellspacing") or t.get("border") in ("0", 0)
                 or t.find("table")]
    table_text = sum(len(t.get_text(" ", strip=True)) for t in tables)
    total_text = max(1, len(soup.get_text(" ", strip=True)))
    out["table_layout"] = _ev(len(layoutish) >= 2 and table_text / total_text > 0.5,
                              f"{len(tables)} <table> tags, {len(layoutish)} layout-style (cellpadding/nested), "
                              f"{round(100*table_text/total_text)}% of page text inside tables")
    # fixed-width tells: layout-tag ATTRIBUTES/inline styles only (raw width values inside
    # inline JSON/scripts are not layout) — and only meaningful on a non-responsive page,
    # which measurable_score gates on.
    fixed = re.findall(r'<(?:table|td|tr|body|div|center)[^>]{0,200}?width\s*[:=]\s*["\']?(\d{3,4})(?:px)?["\']?',
                       html, re.I)
    wide_fixed = [w for w in fixed if 700 <= int(w) <= 1400]
    out["fixed_width_tells"] = _ev(len(wide_fixed) >= 2,
                                   f"{len(wide_fixed)} fixed layout widths in 700-1400px range: {sorted(set(wide_fixed))[:6]}",
                                   "medium")
    out["dated_markup"] = tells

    # copyright year (max year within 60 chars of a copyright token)
    years = []
    for m in re.finditer(r"(?:©|&copy;|copyright)", html, re.I):
        for y in re.findall(r"(19[89]\d|20[0-4]\d)", html[m.start():m.start() + 80]):
            years.append(int(y))
    out["copyright_year"] = _ev(max(years) if years else None,
                                f"latest year near a © token: {max(years)}" if years else "no copyright year found",
                                "high" if years else "low")

    # mixed content — LOADED resources only (src= / stylesheet href=); plain <a href> links are NOT mixed content
    if session_https:
        mixed = re.findall(r'src=["\']http://[^"\']{8,80}', html)
        mixed += re.findall(r'<link[^>]{0,200}?href=["\']http://[^"\']{8,80}', html)
        out["mixed_content"] = _ev(bool(mixed), f"{len(mixed)} http:// LOADED resources on an https page; e.g. {mixed[:2]}")
    else:
        out["mixed_content"] = _ev(False, "site not served over https (see https checks)")

    # jQuery era
    jq = re.findall(r"jquery[-.]?(\d+)\.(\d+)", html, re.I)
    out["jquery_version"] = ".".join(jq[0]) if jq else ""
    out["jquery_era_old"] = bool(jq and int(jq[0][0]) < 3)

    # stylesheets -> media query count
    sheets, mq = [], 0
    mq += len(re.findall(r"@media", html))
    for l in soup.find_all("link", rel="stylesheet")[:4]:
        href = urljoin(base_url, l.get("href") or "")
        if not href.startswith("http"):
            continue
        try:
            css = fetch(href, timeout=12).text
            sheets.append(href)
            mq += len(re.findall(r"@media", css))
        except Exception:
            pass
    out["media_queries"] = _ev(mq, f"{mq} @media rules across inline styles + {len(sheets)} fetched stylesheets")

    # form label coverage (a11y basic)
    inputs = [i for i in soup.find_all(("input", "textarea", "select"))
              if i.get("type") not in ("hidden", "submit", "button", "image")]
    labelled = 0
    label_for = {l.get("for") for l in soup.find_all("label") if l.get("for")}
    for i in inputs:
        if i.get("id") in label_for or i.get("aria-label") or i.get("title") or i.find_parent("label"):
            labelled += 1
    out["form_label_coverage"] = _ev(f"{labelled}/{len(inputs)}" if inputs else "n/a",
                                     f"{labelled} of {len(inputs)} visible form fields have a label/aria-label")
    return out


# ---------------- PageSpeed Insights ----------------
def psi(url):
    out = {}
    for strategy in ("mobile", "desktop"):
        try:
            api = ("https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
                   f"?url={url}&strategy={strategy}&category=performance&category=seo&category=accessibility")
            r = requests.get(api, timeout=120)
            if r.status_code == 429:          # unkeyed PSI rate limit — one polite retry
                time.sleep(25)
                r = requests.get(api, timeout=120)
            r.raise_for_status()
            lr = r.json()["lighthouseResult"]
            cats = {k: round(v["score"] * 100) for k, v in lr["categories"].items() if v.get("score") is not None}
            audits = lr.get("audits", {})
            metrics = {}
            for k in ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time",
                      "first-contentful-paint", "speed-index"):
                if k in audits and audits[k].get("displayValue"):
                    metrics[k] = audits[k]["displayValue"]
            vp_audit = audits.get("viewport", {})
            out[strategy] = {"scores": cats, "metrics": metrics,
                             "lighthouse_viewport_ok": vp_audit.get("score") == 1}
        except Exception as e:
            out[strategy] = {"error": str(e)[:200]}
    return out


# ---------------- completeness signals (Axis 2 raw evidence) ----------------
ADDR_RE = re.compile(r"\b\d{1,5}\s+[A-Z][A-Za-z]+(?:\s[A-Za-z]+){0,3}\s(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Hwy|Suite|Ste)\b")
def completeness_signals(crawl_data):
    pages = [p for p in crawl_data.get("pages", []) if p.get("status") == 200 and p.get("word_count")]
    all_text = " ".join(p.get("text", "")[:20000] for p in pages).lower()
    all_html_urls = " ".join(p.get("url", "") for p in pages).lower()
    links = {u for us in crawl_data.get("links", {}).values() for u in us}
    link_blob = " ".join(links).lower()
    forms = [f for p in pages for f in p.get("forms", [])]
    jsonld = sorted({t for p in pages for t in p.get("jsonld_types", [])})

    def kw(*words):
        return [w for w in words if w in all_text]

    def lnk(pattern):
        return [u for u in links if re.search(pattern, u, re.I)][:5]

    sig = {
        "pages_sampled": len(pages),
        "page_titles": [p.get("title", "")[:80] for p in pages[:15]],
        "nav_link_sample": sorted(links)[:40],
        "jsonld_types": jsonld,
        "forms": [{"action": f.get("action", ""), "fields": f.get("fields", [])[:8]} for f in forms[:10]],
        "commerce": {
            "product_urls": lnk(r"/(product|item|shop|store|catalog|p/)"),
            "cart_urls": lnk(r"cart|basket"),
            "checkout_urls": lnk(r"checkout"),
            "add_to_cart_text": "add to cart" in all_text or "add to basket" in all_text,
            "price_tokens": len(re.findall(r"\$\s?\d{1,5}(?:[.,]\d{2})?", all_text)),
            "product_jsonld": "Product" in jsonld,
        },
        "contact": {
            "tel_links": "tel:" in link_blob or bool(re.search(r"tel:", all_html_urls)),
            "phone_in_text": bool(re.search(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", all_text)),
            "mailto": "mailto:" in link_blob,
            "contact_page": bool(lnk(r"contact")),
            "address_found": bool(ADDR_RE.search(" ".join(p.get("text", "")[:20000] for p in pages))),
            "hours_keywords": bool(kw("hours", "mon-fri", "monday")),
            "contact_form": any("contact" in (f.get("action") or "").lower()
                                or {"email", "message"} & set(x.lower() for x in f.get("fields", []) if x)
                                for f in forms),
        },
        "trust": {
            "about_page": bool(lnk(r"about")),
            "testimonials_reviews": bool(kw("testimonial", "reviews", "review")),
            "privacy_policy": bool(lnk(r"privacy")),
            "terms": bool(lnk(r"terms")),
            "returns_guarantee": bool(kw("return policy", "guarantee", "refund", "warranty")),
            "social_links": sorted({d for d in ("facebook", "instagram", "youtube", "linkedin", "twitter", "tiktok", "yelp")
                                    if d in link_blob})[:7],
            "certifications_keywords": bool(kw("licensed", "insured", "certified", "accredited", "bbb")),
        },
        "content": {
            "blog_news": bool(lnk(r"blog|news|articles")),
            "faq": bool(lnk(r"faq") or kw("frequently asked")),
            "gallery": bool(lnk(r"gallery|portfolio|photos")),
            "search": any("search" in (f.get("action") or "").lower() or
                          "q" in [x.lower() for x in f.get("fields", []) if x] or
                          "s" in [x.lower() for x in f.get("fields", []) if x] for f in forms),
            "newsletter": bool(kw("newsletter", "subscribe", "mailing list")),
        },
        "images_alt_coverage": None,
    }
    imgs = [i for p in pages for i in p.get("images", []) if i.get("src")]
    if imgs:
        with_alt = sum(1 for i in imgs if i.get("alt"))
        sig["images_alt_coverage"] = {"with_alt": with_alt, "total": len(imgs),
                                      "pct": round(100 * with_alt / len(imgs))}
    return sig


# ---------------- responsive + measurable scoring ----------------
def responsive_verdict(static, render):
    vp = bool(static.get("viewport_meta", {}).get("value"))
    mq = (static.get("media_queries", {}).get("value") or 0) > 0
    mob = render.get("mobile-390") or {}
    overflow = None
    if mob.get("scrollWidth") and mob.get("clientWidth"):
        overflow = mob["scrollWidth"] > mob["clientWidth"] * 1.06
    signals = {"viewport_meta": vp, "media_queries": mq,
               "mobile_overflow": overflow,
               "mobile_overflow_evidence": (f"scrollWidth {mob.get('scrollWidth')} vs viewport {mob.get('clientWidth')}"
                                            if mob else "no mobile render captured")}
    pos = sum([vp, mq, overflow is False])
    neg = sum([not vp, not mq, overflow is True])
    if pos == 3:
        v = "responsive"
    elif not vp and not mq:
        v = "not-responsive"          # high confidence: no viewport meta AND no media queries
    elif neg >= 2:
        v = "poor-mobile"
    else:
        v = "partial"
    return {"verdict": v, "signals": signals,
            "confidence": "high" if v in ("responsive", "not-responsive") else "medium"}


def measurable_score(diag):
    """0-100 from objective checks only; each component records its evidence.
    Weights: responsive 30, performance 20, dated-tech 20, https 10, a11y 10, delivery 10."""
    parts = {}
    rv = diag["responsive"]["verdict"]
    parts["responsive"] = {"weight": 30, "score": {"responsive": 1.0, "partial": 0.6, "poor-mobile": 0.25, "not-responsive": 0.0}[rv],
                           "evidence": rv}
    perf = None
    p = diag.get("psi", {}).get("mobile", {})
    if p.get("scores", {}).get("performance") is not None:
        perf = p["scores"]["performance"]
        parts["performance"] = {"weight": 20, "score": perf / 100, "evidence": f"PSI mobile performance {perf}"}
    else:
        load = (diag.get("render", {}).get("desktop") or {}).get("load_seconds")
        if load is not None:
            parts["performance"] = {"weight": 20, "score": max(0.0, min(1.0, (12 - load) / 10)),
                                    "evidence": f"no PSI; measured desktop load {load}s"}
        else:
            parts["performance"] = {"weight": 20, "score": 0.5, "evidence": "unmeasured (no PSI, no render)", "unmeasured": True}
    st = diag["static"]
    dated_hits = []
    if st.get("table_layout", {}).get("value"): dated_hits.append("table layout")
    if st.get("dated_markup"): dated_hits.append(f"dated tags {st['dated_markup']}")
    if st.get("jquery_era_old"): dated_hits.append(f"jQuery {st.get('jquery_version')}")
    if st.get("dated_generator"): dated_hits.append(f"generator: {st.get('generator_meta')}")
    if not st.get("doctype_html5", {}).get("value"): dated_hits.append("pre-HTML5 doctype")
    cy = st.get("copyright_year", {}).get("value")
    if cy and cy < NOW_YEAR - 1: dated_hits.append(f"copyright {cy}")
    if st.get("fixed_width_tells", {}).get("value") and diag["responsive"]["verdict"] != "responsive":
        dated_hits.append("fixed-width layout tells")
    parts["dated_tech"] = {"weight": 20, "score": max(0.0, 1.0 - 0.25 * len(dated_hits)),
                           "evidence": dated_hits or "no dated-tech tells"}
    h = diag["https"]
    hs = 1.0 if (h.get("https_ok") and h.get("http_redirects_to_https")) else (0.5 if h.get("https_ok") else 0.0)
    parts["https"] = {"weight": 10, "score": hs,
                      "evidence": f"https_ok={h.get('https_ok')} cert_valid={h.get('cert_valid')} http→https={h.get('http_redirects_to_https')}"}
    a11y = []
    alt = diag.get("completeness", {}).get("images_alt_coverage")
    ascore = 1.0
    if alt and alt["pct"] < 50: ascore -= 0.35; a11y.append(f"alt coverage {alt['pct']}%")
    if not st.get("html_lang", {}).get("value"): ascore -= 0.2; a11y.append("no html lang")
    con = diag.get("contrast", {})
    if con.get("checked") and con["failing"] / max(1, con["checked"]) > 0.25:
        ascore -= 0.45; a11y.append(f"contrast: {con['failing']}/{con['checked']} sampled text fails WCAG AA")
    pa = diag.get("psi", {}).get("mobile", {}).get("scores", {}).get("accessibility")
    if pa is not None and pa < 70: ascore = min(ascore, pa / 100); a11y.append(f"PSI a11y {pa}")
    parts["accessibility"] = {"weight": 10, "score": max(0.0, ascore), "evidence": a11y or "no basic a11y failures detected"}
    mx = st.get("mixed_content", {}).get("value")
    parts["delivery"] = {"weight": 10, "score": 0.4 if mx else 1.0,
                         "evidence": "mixed http content on https page" if mx else "clean delivery"}
    total = round(sum(p["weight"] * p["score"] for p in parts.values()))
    return {"score": total, "parts": parts}


# ---------------- main ----------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) < 2:
        print(__doc__); sys.exit(1)
    url, outdir = args[0], Path(args[1])
    max_pages = 12
    for f in flags:
        if f.startswith("--max-pages="):
            max_pages = int(f.split("=")[1])
    if not url.startswith("http"):
        url = "https://" + url
    domain = urlparse(url).netloc.replace("www.", "")
    capdir = outdir / "capture"
    capdir.mkdir(parents=True, exist_ok=True)
    diag = {"url": url, "domain": domain, "captured_at": datetime.now(timezone.utc).isoformat(),
            "tool": "site-diagnostic/diagnose.py"}

    print(f"[1/6] https checks for {domain}")
    diag["https"] = check_https(domain)
    base = diag["https"].get("final_url") or url

    print(f"[2/6] mini-crawl ({max_pages} pages max, polite)")
    try:
        cr = mini_crawl(base, max_pages=max_pages, delay=0.5)
    except Exception as e:
        cr = {"pages": [], "error": str(e)[:200]}
    ok_pages = [p for p in cr.get("pages", []) if p.get("status") == 200]
    diag["crawl"] = {"pages_ok": len(ok_pages), "pages_tried": len(cr.get("pages", [])),
                     "error": cr.get("error", "")}

    print("[3/6] rendered capture (desktop + 390px)")
    diag["render"] = render_homepage(base, capdir)
    if diag["render"].get("contrast_samples"):
        diag["contrast"] = contrast_report(diag["render"].pop("contrast_samples"))

    # homepage HTML: prefer rendered (post-JS), fall back to crawl
    html = ""
    if (capdir / "home.html").exists():
        html = (capdir / "home.html").read_text(errors="replace")
    elif ok_pages:
        try:
            html = fetch(base).text
            (capdir / "home.html").write_text(html, errors="replace")
        except Exception:
            pass
    if not html and not ok_pages:
        diag["unreachable"] = True
        (outdir / "diagnostic.json").write_text(json.dumps(diag, indent=1))
        print(f"UNREACHABLE: no method captured {url}")
        sys.exit(2)

    print("[4/6] static HTML/CSS analysis")
    diag["static"] = analyze_html(html, base, urlparse(base).scheme == "https")
    blob = html + " " + " ".join((p.get("url") or "") for p in cr.get("pages", [])) + \
        " ".join(s or "" for p in cr.get("pages", []) for s in p.get("scripts", []))
    diag["tech_fingerprint"] = [n for n, pat in FINGERPRINTS if re.search(pat, blob, re.I)]

    print("[5/6] PageSpeed Insights (skippable with --skip-psi)")
    diag["psi"] = {} if "--skip-psi" in flags else psi(base)

    print("[6/6] completeness signals + scoring")
    diag["completeness"] = completeness_signals(cr)
    diag["responsive"] = responsive_verdict(diag["static"], diag["render"])
    diag["measurable"] = measurable_score(diag)

    (outdir / "diagnostic.json").write_text(json.dumps(diag, indent=1))
    write_summary(outdir, diag)
    print(f"done: measurable score {diag['measurable']['score']}/100, responsive={diag['responsive']['verdict']} -> {outdir}")


def write_summary(outdir, d):
    L = [f"# Measurables — {d['domain']}", "",
         f"Captured {d['captured_at']} · {d['crawl']['pages_ok']} pages crawled · "
         f"render captured: {d.get('render', {}).get('captured')}", ""]
    m = d.get("measurable", {})
    L.append(f"**Measurable score: {m.get('score')}/100**  (objective checks only — judged axis comes from the model)")
    L.append("")
    L.append("| component | weight | score | evidence |")
    L.append("|---|---|---|---|")
    for k, p in m.get("parts", {}).items():
        L.append(f"| {k} | {p['weight']} | {round(p['score'], 2)} | {str(p['evidence'])[:120]} |")
    L += ["", f"- responsive: **{d['responsive']['verdict']}** ({d['responsive']['confidence']}) — {d['responsive']['signals']}",
          f"- tech: {', '.join(d.get('tech_fingerprint', [])) or 'none detected'}",
          f"- psi: {json.dumps({k: v.get('scores', v.get('error', ''))[:90] if isinstance(v.get('scores', ''), str) else v.get('scores') for k, v in d.get('psi', {}).items()})}",
          f"- challenge_suspected: {d.get('render', {}).get('challenge_suspected')}"]
    (outdir / "MEASURABLES.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
