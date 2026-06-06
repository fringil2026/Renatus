#!/usr/bin/env python3
"""Concept boards — three small static HTML homepage mockups (one per art-direction concept)
plus desktop+mobile screenshots, used to drive a VISUAL design-concept decision.

Part of "Prepare intake pack": after the scrape, before any prototype, the human sees three
real designs (not documents) and picks one. Pure stdlib + Playwright only.

CLI:    python3 concept_boards.py <client_dir>
Reads:  <client_dir>/02-intake/concepts/concepts.json   (authored by the intake-pack step)
Writes: 02-intake/concepts/site/index.html               (noindex root listing the boards)
        02-intake/concepts/site/concepts/<letter>/index.html   (one self-contained board each)
        02-intake/concepts/<letter>-<id>.png / -390.png        (desktop + mobile screenshots)
        02-intake/concepts/boards.json                         (manifest; deploy_url filled by caller)

Boards are TYPE-LED by default (honest when photography is weak); a supplied >=1600w image may
back the hero, >=600w images may fill cards — never upscaled. No JavaScript. noindex on every page.
Degrades gracefully if Playwright is missing (writes SCREENSHOTS-SKIPPED.txt, still exits 0).
"""
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def esc(s):
    return html.escape(str(s or ""))


def font_link(fonts):
    fams = []
    for key in ("display", "body", "mono"):
        fam = fonts.get(key)
        if fam:
            fams.append("family=" + fam.replace(" ", "+") + ":ital,wght@0,400;0,600;1,400")
    if not fams:
        return ""
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?{"&".join(fams)}&display=swap" rel="stylesheet">')


# Three layout attitudes so the boards never read as recolors of one template. Each returns a
# dict of CSS fragments keyed by region; chosen by the board's `layout` hint (fallback by index).
def layout_attitude(name):
    A = {
        # airy, centered, glasshouse — generous whitespace, light surfaces, hairline rules
        "conservatory": {
            "hero_align": "center", "hero_pad": "7rem 1.5rem", "hero_minh": "82vh",
            "title_size": "clamp(3rem,9vw,7rem)", "title_style": "font-weight:600;letter-spacing:-.02em;line-height:.95",
            "grid": "repeat(auto-fit,minmax(220px,1fr))", "card_radius": "3px",
            "card_border": "1px solid var(--surface)", "card_pad": "1.1rem 1.1rem 1.3rem",
            "band_pad": "4.5rem 1.5rem", "band_align": "center", "nav_border": "1px solid var(--surface)",
            "hero_extra": "", "card_shadow": "0 1px 0 var(--surface)",
        },
        # moody, left-aligned, field-guide — darker, framed, index-tab energy
        "field-guide": {
            "hero_align": "left", "hero_pad": "8rem 2rem", "hero_minh": "88vh",
            "title_size": "clamp(2.6rem,8vw,6rem)", "title_style": "font-weight:400;letter-spacing:-.01em;line-height:1.0",
            "grid": "repeat(auto-fit,minmax(240px,1fr))", "card_radius": "0",
            "card_border": "1px solid var(--primary)", "card_pad": "1.2rem",
            "band_pad": "5.5rem 2rem", "band_align": "left", "nav_border": "2px solid var(--primary)",
            "hero_extra": "border-left:6px solid var(--accent);padding-left:2.4rem", "card_shadow": "none",
        },
        # gallery-dark, immersive — near-black canvas, the type/photo supplies the colour
        "gallery": {
            "hero_align": "center", "hero_pad": "9rem 1.5rem", "hero_minh": "92vh",
            "title_size": "clamp(3.2rem,10vw,8rem)", "title_style": "font-weight:400;font-style:italic;letter-spacing:.005em;line-height:.92",
            "grid": "repeat(auto-fit,minmax(210px,1fr))", "card_radius": "0",
            "card_border": "1px solid #2a2c26", "card_pad": "1.3rem 1rem",
            "band_pad": "6rem 1.5rem", "band_align": "center", "nav_border": "1px solid #2a2c26",
            "hero_extra": "", "card_shadow": "none",
        },
    }
    return A.get(name, A["conservatory"])


def render_board(b, client_name):
    pal = b.get("palette", {})
    bg = pal.get("bg", "#ffffff"); surface = pal.get("surface", "#eeeeee")
    ink = pal.get("ink", "#161616"); primary = pal.get("primary", "#274"); accent = pal.get("accent", "#e0a23b")
    fonts = b.get("fonts", {})
    disp = fonts.get("display", "Georgia"); body = fonts.get("body", "system-ui"); mono = fonts.get("mono", "monospace")
    L = layout_attitude(b.get("layout", "conservatory"))
    nav = b.get("nav", [])
    kicker = b.get("hero_kicker", "")
    title = b.get("hero_title") or b.get("name", "")
    one = b.get("one_liner", "")
    band = b.get("band_text", "")
    sig = b.get("signature", "")
    products = b.get("products", [])

    # hero photo only if an honest >=1600w image was supplied for this board
    hero_bg = ""
    himg = b.get("hero_image")
    if himg and himg.get("path") and int(himg.get("w", 0)) >= 1600:
        hero_bg = f"background:linear-gradient(rgba(0,0,0,.32),rgba(0,0,0,.42)),url('{esc(himg['path'])}') center/cover"

    cards = ""
    for p in products:
        chip = (f'<span class="chip">{esc(p["chip"])}</span>' if p.get("chip") else "")
        price = (f'<span class="price">{esc(p["price"])}</span>' if p.get("price") else "")
        cards += (
            f'<article class="card"><div class="thumb">{chip}</div>'
            f'<h3>{esc(p.get("name",""))}</h3>'
            f'<p class="meta">{esc(p.get("meta",""))}</p>{price}</article>')

    hero_inner = (
        (f'<p class="kicker">{esc(kicker)}</p>' if kicker else '')
        + f'<h1 class="htitle">{esc(title)}</h1>'
        + (f'<p class="lede">{esc(one)}</p>' if one else ''))

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{esc(b.get('name',''))} — concept board — {esc(client_name)}</title>
{font_link(fonts)}
<style>
:root{{--bg:{bg};--surface:{surface};--ink:{ink};--primary:{primary};--accent:{accent};
--disp:'{disp}',Georgia,serif;--body:'{body}',system-ui,sans-serif;--mono:'{mono}',monospace}}
*{{box-sizing:border-box}}html,body{{margin:0}}
body{{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.55}}
.banner{{position:sticky;top:0;z-index:9;background:var(--ink);color:var(--bg);
font-family:var(--mono);font-size:.66rem;letter-spacing:.12em;text-transform:uppercase;
padding:.5rem .9rem;display:flex;gap:.8rem;align-items:baseline;flex-wrap:wrap}}
.banner b{{color:var(--accent)}}.banner .one{{opacity:.72;text-transform:none;letter-spacing:0;font-family:var(--body)}}
nav{{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;
padding:1rem 1.4rem;border-bottom:{L['nav_border']}}}
.wm{{font-family:var(--disp);font-size:1.5rem;font-weight:600;letter-spacing:.01em}}
.nav-links{{display:flex;gap:1.1rem;font-family:var(--mono);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;flex-wrap:wrap}}
.nav-links span{{color:var(--ink);opacity:.8}}
.hero{{min-height:{L['hero_minh']};padding:{L['hero_pad']};display:flex;flex-direction:column;
justify-content:center;text-align:{L['hero_align']};{hero_bg}}}
.hero-in{{{L['hero_extra']}}}
{('.hero,.hero .kicker,.hero .lede,.hero .htitle{color:#f6f4ee}' if hero_bg else '')}
.kicker{{font-family:var(--mono);font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);margin:0 0 1rem}}
.htitle{{font-family:var(--disp);font-size:{L['title_size']};{L['title_style']};margin:0}}
.lede{{font-family:var(--body);max-width:34rem;margin:1.4rem {'auto' if L['hero_align']=='center' else '0'} 0;font-size:1.05rem;opacity:.86}}
.grid{{display:grid;grid-template-columns:{L['grid']};gap:1rem;padding:3rem 1.4rem}}
.card{{border:{L['card_border']};border-radius:{L['card_radius']};padding:{L['card_pad']};
background:var(--bg);box-shadow:{L['card_shadow']}}}
.thumb{{aspect-ratio:4/3;background:var(--surface);border-radius:{L['card_radius']};
margin:-.2rem 0 .9rem;position:relative;display:flex;align-items:flex-start;justify-content:flex-end;padding:.5rem}}
.chip{{font-family:var(--mono);font-size:.58rem;letter-spacing:.08em;text-transform:uppercase;
background:var(--primary);color:var(--bg);padding:.22em .6em;border-radius:99px}}
.card h3{{font-family:var(--disp);font-style:italic;font-weight:400;font-size:1.25rem;margin:.1rem 0 .2rem}}
.meta{{font-family:var(--mono);font-size:.68rem;letter-spacing:.04em;color:var(--ink);opacity:.7;margin:0 0 .5rem}}
.price{{font-family:var(--body);font-weight:600}}
.band{{background:var(--primary);color:var(--bg);padding:{L['band_pad']};text-align:{L['band_align']}}}
.band p{{font-family:var(--disp);font-size:clamp(1.6rem,4vw,2.6rem);margin:0;max-width:30rem;
{'margin-left:auto;margin-right:auto' if L['band_align']=='center' else ''}}}
.band .sig{{font-family:var(--mono);font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;
color:var(--accent);display:block;margin-bottom:.8rem}}
footer{{padding:2.4rem 1.4rem;font-family:var(--mono);font-size:.7rem;letter-spacing:.1em;
text-transform:uppercase;color:var(--ink);opacity:.6;border-top:1px solid var(--surface)}}
</style></head><body>
<div class="banner"><b>Concept board — not the final build</b>
<span>{esc(b.get('name',''))}</span><span class="one">{esc(one)}</span></div>
<nav><span class="wm">{esc(client_name)}</span><div class="nav-links">{''.join(f'<span>{esc(n)}</span>' for n in nav)}</div></nav>
<header class="hero"><div class="hero-in">{hero_inner}</div></header>
<section class="grid">{cards}</section>
<section class="band">{('<span class="sig">Signature — '+esc(sig)+'</span>') if sig else ''}<p>{esc(band)}</p></section>
<footer>{esc(client_name)} · concept board · type-led where photography is pending</footer>
</body></html>"""


def render_root(client_name, boards):
    items = ""
    for b in boards:
        rec = ' &nbsp;★ recommended' if b.get("recommended") else ''
        items += (f'<li><a href="concepts/{esc(b["letter"])}/"><b>{esc(b.get("name",""))}</b>{rec}</a>'
                  f'<span>{esc(b.get("one_liner",""))}</span></li>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Concept boards — {esc(client_name)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1.2rem;line-height:1.5}}
h1{{font-size:1.5rem}}ul{{list-style:none;padding:0}}li{{border-top:1px solid #ddd;padding:1rem 0}}
a{{font-size:1.1rem;text-decoration:none;color:#1a5}}span{{display:block;color:#555;font-size:.9rem;margin-top:.2rem}}
.note{{color:#888;font-size:.8rem}}</style></head><body>
<h1>Concept boards — {esc(client_name)}</h1>
<p class="note">Three homepage impressions. Pick one in the studio dashboard. Each is a preview, not the final build. (noindex)</p>
<ul>{items}</ul></body></html>"""


def shoot(site_dir, concepts_dir, boards):
    """Desktop + mobile full-page screenshots of each board via Playwright. Never aborts the run."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        (concepts_dir / "SCREENSHOTS-SKIPPED.txt").write_text(
            f"Playwright unavailable ({e}). Boards HTML written; screenshots skipped.\n"
            "Install: python3 -m pip install playwright && python3 -m playwright install chromium\n")
        print("screenshots: skipped (playwright unavailable)")
        return False
    shot = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            for b in boards:
                url = (site_dir / "concepts" / b["letter"] / "index.html").resolve().as_uri()
                stem = f"{b['letter']}-{b['id']}"
                for suffix, vp in (("", {"width": 1440, "height": 900}),
                                   ("-390", {"width": 390, "height": 844})):
                    page = browser.new_page(viewport=vp, device_scale_factor=2)
                    try:
                        page.goto(url, wait_until="networkidle", timeout=20000)
                    except Exception:
                        page.goto(url, timeout=20000)
                    page.wait_for_timeout(450)
                    page.screenshot(path=str(concepts_dir / f"{stem}{suffix}.png"), full_page=True)
                    page.close()
                    shot += 1
            browser.close()
        print(f"screenshots: {shot} written")
        return True
    except Exception as e:
        (concepts_dir / "SCREENSHOTS-SKIPPED.txt").write_text(f"Screenshot pass failed: {e}\n")
        print(f"screenshots: failed ({e})")
        return False


def main():
    if len(sys.argv) < 2:
        print("usage: concept_boards.py <client_dir>"); sys.exit(2)
    client = Path(sys.argv[1]).resolve()
    concepts_dir = client / "02-intake" / "concepts"
    src = concepts_dir / "concepts.json"
    if not src.exists():
        print(f"no concepts.json at {src}"); sys.exit(1)
    data = json.loads(src.read_text())
    client_name = data.get("client_name") or data.get("client") or client.name
    boards = data.get("boards", [])
    if not boards:
        print("concepts.json has no boards"); sys.exit(1)

    site_dir = concepts_dir / "site"
    (site_dir / "concepts").mkdir(parents=True, exist_ok=True)
    for b in boards:
        bdir = site_dir / "concepts" / b["letter"]
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "index.html").write_text(render_board(b, client_name))
    (site_dir / "index.html").write_text(render_root(client_name, boards))
    print(f"boards: {len(boards)} written -> {site_dir}")

    shoot(site_dir, concepts_dir, boards)

    manifest = {"generated": now(), "deploy_project": data.get("deploy_project", ""),
                "deploy_url": "", "boards": []}
    for b in boards:
        stem = f"{b['letter']}-{b['id']}"
        manifest["boards"].append({
            "letter": b["letter"], "id": b["id"], "name": b.get("name", ""),
            "one_liner": b.get("one_liner", ""), "recommended": bool(b.get("recommended")),
            "path": f"concepts/{b['letter']}/",
            "thumb_desktop": f"{stem}.png", "thumb_mobile": f"{stem}-390.png"})
    (concepts_dir / "boards.json").write_text(json.dumps(manifest, indent=2))
    print(f"manifest: {concepts_dir/'boards.json'}")


if __name__ == "__main__":
    main()
