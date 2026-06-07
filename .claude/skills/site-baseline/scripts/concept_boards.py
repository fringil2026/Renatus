#!/usr/bin/env python3
"""Concept boards — static HTML homepage mockups (one per art-direction concept) spanning a
DELIBERATE creativity spectrum, plus desktop+mobile screenshots, to drive a VISUAL design-concept
decision.

Part of "Prepare intake pack": after the scrape, before any prototype, the human sees real designs
(not documents) and picks one. Pure stdlib + Playwright only.

THE SPECTRUM (binding — see CLAUDE.md Command 9 / ECOMMERCE-GUIDELINES §5.8):
  A · classic      — the safe, conversion-proven expression a cautious owner says yes to.
  B · confident    — the studio's recommendation: distinctive, editorial, clearly designed.
  C · bold         — pushes the concept hard: unconventional grid, dramatic type, a structural idea.
  D/E · experimental — only via "Push further": beyond bold; breaks conservative conventions.
The three base boards must DIFFER STRUCTURALLY — layout archetype AND typographic attitude AND one
structural idea each. Three palettes on one layout is a generation FAILURE (the divergence test below
exits non-zero). Every board still obeys the ground rules: honest imagery (type-led when photography
is weak), accessibility, explicit language, parity-compatible, reduced-motion honored.

CLI:    python3 concept_boards.py <client_dir>
Reads:  <client_dir>/02-intake/concepts/concepts.json
Writes: 02-intake/concepts/site/index.html, .../site/concepts/<letter>/index.html,
        02-intake/concepts/<letter>-<id>.png / -390.png, 02-intake/concepts/boards.json
"""
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TIER_LAYOUT = {"classic": "classic", "confident": "editorial", "bold": "dramatic",
               "experimental": "experimental"}
TIER_LABEL = {"classic": "CLASSIC · the safe choice", "confident": "CONFIDENT · our recommendation",
              "bold": "BOLD · pushes the concept", "experimental": "EXPERIMENTAL · beyond bold"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def esc(s):
    return html.escape(str(s or ""))


def font_link(fonts):
    fams = []
    for key in ("display", "body", "mono"):
        fam = fonts.get(key)
        if fam:
            fams.append("family=" + fam.replace(" ", "+") + ":ital,wght@0,400;0,600;0,700;1,400")
    if not fams:
        return ""
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?{"&".join(fams)}&display=swap" rel="stylesheet">')


# Each archetype is a STRUCTURALLY distinct theme (nav placement, hero composition, grid behaviour,
# band) — not a recolour. The base CSS holds shared semantics (so every board stays accessible +
# parity-complete); the archetype CSS does the restructuring.
def archetype_css(name):
    A = {
        # CLASSIC — conventional + symmetric: centered stacked nav, centered moderate hero with a
        # clear CTA, even product grid. The conversion-proven safe expression.
        "classic": """
nav{flex-direction:column;align-items:center;gap:.55rem;padding:1.5rem;border-bottom:1px solid var(--surface);text-align:center}
.nav-links{justify-content:center}
.hero{min-height:68vh;padding:5rem 1.5rem;text-align:center;align-items:center}
.htitle{font-size:clamp(2.4rem,6vw,4.4rem);font-weight:600;letter-spacing:-.01em}
.lede{margin:1.3rem auto 0}
.cta{display:inline-block;margin-top:1.7rem;background:var(--primary);color:var(--bg);font-family:var(--mono);
font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;padding:.75rem 1.7rem;border-radius:3px}
.grid{grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}
.card{border:1px solid var(--surface);border-radius:4px}
.band{text-align:center;padding:4.5rem 1.5rem}
""",
        # EDITORIAL — confident asymmetry: wordmark-left nav, a two-column hero with a called-out
        # signature legend, and a 6-col grid whose first two cards are featured (2-up) then 3-up.
        "editorial": """
nav{justify-content:space-between;align-items:baseline;padding:1.2rem 1.6rem;border-bottom:2px solid var(--ink)}
.hero{min-height:84vh;padding:5.5rem 1.6rem;display:grid;grid-template-columns:1.5fr .85fr;gap:2.4rem;align-items:center;text-align:left}
.htitle{font-size:clamp(3rem,8vw,6.6rem);font-weight:600;letter-spacing:-.02em}
.lede{margin:1.4rem 0 0}
.hero-aside{align-self:end;border-left:3px solid var(--accent);padding-left:1.1rem;font-family:var(--mono);
font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--primary);line-height:1.7}
.grid{grid-template-columns:repeat(6,1fr);gap:1rem}
.card{grid-column:span 2}
.card:nth-child(1),.card:nth-child(2){grid-column:span 3}
.card:nth-child(1) .htitle{font-size:2rem}
.band{text-align:left;padding:5.5rem 1.6rem}
@media(max-width:680px){.hero{grid-template-columns:1fr}.grid{grid-template-columns:1fr 1fr}.card,.card:nth-child(1),.card:nth-child(2){grid-column:span 1}}
""",
        # DRAMATIC — bold: sparse nav, viewport-filling oversized type anchored to the baseline, and a
        # STAGGERED/offset product grid (even cards drop down). High drama, still browsable.
        "dramatic": """
nav{justify-content:space-between;align-items:center;padding:1.3rem 1.5rem;border-bottom:1px solid var(--surface)}
.nav-links{gap:1.4rem;opacity:.85}
.hero{min-height:92vh;padding:2rem 1.3rem 4rem;display:flex;align-items:flex-end}
.htitle{font-size:clamp(4rem,16vw,11rem);font-weight:700;line-height:.84;letter-spacing:-.03em}
.kicker{margin-bottom:1.4rem}
.lede{max-width:30rem}
.grid{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.1rem;align-items:start}
.card{border:1px solid var(--surface)}
.card:nth-child(even){margin-top:3.6rem}
.card:nth-child(3n){margin-top:1.8rem}
.band{text-align:center;padding:6rem 1.5rem}
.band p{font-size:clamp(2rem,6vw,3.6rem)}
""",
        # EXPERIMENTAL — beyond bold: an unconventional NUMBERED-INDEX nav metaphor (stacked display
        # links), the headline AS the entire hero (extreme scale, a clip-path reveal gated by
        # reduced-motion), and a BROKEN collage grid (rotated/offset spans). Theatrical but honest.
        "experimental": """
nav{flex-direction:column;align-items:flex-start;gap:.35rem;padding:1.3rem 1.4rem;border-bottom:none}
.wm{font-size:1.1rem;opacity:.65;letter-spacing:.02em}
.nav-links{flex-direction:column;gap:.05rem;counter-reset:navc;text-transform:none;letter-spacing:0}
.nav-links span{counter-increment:navc;font-family:var(--disp);font-size:clamp(1.3rem,3vw,2rem);line-height:1.05}
.nav-links span::before{content:"0" counter(navc) "  ";font-family:var(--mono);font-size:.66rem;color:var(--accent);vertical-align:.35em}
.hero{min-height:96vh;padding:0 1rem;display:flex;align-items:center;justify-content:center;overflow:hidden}
.hero-in{width:100%}
.kicker{text-align:center}
.htitle{font-size:clamp(4rem,23vw,17rem);font-weight:700;line-height:.78;letter-spacing:-.04em;text-align:center;
animation:cb-reveal 1.05s cubic-bezier(.2,.7,.2,1) forwards}
.lede{margin:1.6rem auto 0;text-align:center}
@keyframes cb-reveal{from{clip-path:inset(0 100% 0 0);opacity:.15}to{clip-path:inset(0 0 0 0);opacity:1}}
.grid{grid-template-columns:repeat(12,1fr);gap:1rem;padding-top:4rem;padding-bottom:4rem}
.card{grid-column:span 4;transition:transform .25s ease}
.card:nth-child(1){grid-column:2/span 5;transform:rotate(-1.6deg)}
.card:nth-child(2){grid-column:8/span 4;margin-top:5rem}
.card:nth-child(3){grid-column:1/span 4;margin-top:-2rem}
.card:nth-child(4){grid-column:6/span 6}
.card:hover{transform:scale(1.04) rotate(0deg)}
.band{text-align:left;padding:6rem 1.4rem}
.band p{font-size:clamp(2.2rem,7vw,4.4rem)}
@media(prefers-reduced-motion:reduce){.htitle{animation:none}.card{transition:none}}
@media(max-width:680px){.grid{grid-template-columns:1fr}.card,.card:nth-child(1),.card:nth-child(2),.card:nth-child(3),.card:nth-child(4){grid-column:span 1;margin-top:0;transform:none}}
""",
    }
    return A.get(name, A["editorial"])


def render_board(b, client_name):
    pal = b.get("palette", {})
    bg = pal.get("bg", "#ffffff"); surface = pal.get("surface", "#eeeeee")
    ink = pal.get("ink", "#161616"); primary = pal.get("primary", "#274"); accent = pal.get("accent", "#e0a23b")
    fonts = b.get("fonts", {})
    disp = fonts.get("display", "Georgia"); body = fonts.get("body", "system-ui"); mono = fonts.get("mono", "monospace")
    tier = b.get("tier", "confident")
    layout = b.get("layout") or TIER_LAYOUT.get(tier, "editorial")
    nav = b.get("nav", [])
    kicker = b.get("hero_kicker", "")
    title = b.get("hero_title") or b.get("name", "")
    one = b.get("one_liner", "")
    band = b.get("band_text", "")
    sig = b.get("signature", "") or b.get("structural_idea", "")
    products = b.get("products", [])
    is_classic = (layout == "classic")
    is_editorial = (layout == "editorial")

    hero_bg = ""
    himg = b.get("hero_image")
    if himg and himg.get("path") and int(himg.get("w", 0)) >= 1600:
        hero_bg = f"background:linear-gradient(rgba(0,0,0,.34),rgba(0,0,0,.46)),url('{esc(himg['path'])}') center/cover"

    cards = ""
    for p in products:
        chip = (f'<span class="chip">{esc(p["chip"])}</span>' if p.get("chip") else "")
        price = (f'<span class="price">{esc(p["price"])}</span>' if p.get("price") else "")
        cards += (f'<article class="card"><div class="thumb">{chip}</div>'
                  f'<h3>{esc(p.get("name",""))}</h3><p class="meta">{esc(p.get("meta",""))}</p>{price}</article>')

    cta = ('<a class="cta" href="#catalog">Browse the catalogue</a>' if is_classic else "")
    aside = (f'<aside class="hero-aside">{esc(sig)}</aside>' if (is_editorial and sig) else "")
    hero_inner = ((f'<p class="kicker">{esc(kicker)}</p>' if kicker else '')
                  + f'<h1 class="htitle">{esc(title)}</h1>'
                  + (f'<p class="lede">{esc(one)}</p>' if one else '') + cta)

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{esc(b.get('name',''))} — concept board ({tier}) — {esc(client_name)}</title>
{font_link(fonts)}
<style>
:root{{--bg:{bg};--surface:{surface};--ink:{ink};--primary:{primary};--accent:{accent};
--disp:'{disp}',Georgia,serif;--body:'{body}',system-ui,sans-serif;--mono:'{mono}',monospace}}
*{{box-sizing:border-box}}html,body{{margin:0}}
body{{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.55}}
.banner{{position:sticky;top:0;z-index:9;background:var(--ink);color:var(--bg);
font-family:var(--mono);font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;
padding:.5rem .9rem;display:flex;gap:.8rem;align-items:baseline;flex-wrap:wrap}}
.banner b{{color:var(--accent)}}.banner .tier{{color:var(--bg);opacity:.85}}
.banner .one{{opacity:.66;text-transform:none;letter-spacing:0;font-family:var(--body)}}
nav{{display:flex;gap:1rem;flex-wrap:wrap}}
.wm{{font-family:var(--disp);font-size:1.5rem;font-weight:700;letter-spacing:.01em}}
.nav-links{{display:flex;gap:1.1rem;font-family:var(--mono);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;flex-wrap:wrap}}
.nav-links span{{color:var(--ink);opacity:.82}}
.hero{{display:flex;flex-direction:column;justify-content:center;{hero_bg}}}
{('.hero,.hero .kicker,.hero .lede,.hero .htitle{color:#f6f4ee}' if hero_bg else '')}
.kicker{{font-family:var(--mono);font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);margin:0 0 1rem}}
.htitle{{font-family:var(--disp);margin:0}}
.lede{{font-family:var(--body);max-width:34rem;font-size:1.05rem;opacity:.86}}
.grid{{display:grid;gap:1rem;padding:3rem 1.4rem}}
.card{{padding:1.1rem 1.1rem 1.3rem;background:var(--bg)}}
.thumb{{aspect-ratio:4/3;background:var(--surface);margin:-.2rem 0 .9rem;position:relative;display:flex;align-items:flex-start;justify-content:flex-end;padding:.5rem}}
.chip{{font-family:var(--mono);font-size:.58rem;letter-spacing:.08em;text-transform:uppercase;background:var(--primary);color:var(--bg);padding:.22em .6em;border-radius:99px;align-self:flex-start}}
.card h3{{font-family:var(--disp);font-style:italic;font-weight:400;font-size:1.25rem;margin:.1rem 0 .2rem}}
.meta{{font-family:var(--mono);font-size:.68rem;letter-spacing:.04em;color:var(--ink);opacity:.7;margin:0 0 .5rem}}
.price{{font-family:var(--body);font-weight:600}}
.band{{background:var(--primary);color:var(--bg)}}
.band p{{font-family:var(--disp);font-size:clamp(1.6rem,4vw,2.6rem);margin:0;max-width:32rem}}
.band .sig{{font-family:var(--mono);font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);display:block;margin-bottom:.8rem}}
footer{{padding:2.4rem 1.4rem;font-family:var(--mono);font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink);opacity:.6;border-top:1px solid var(--surface)}}
{archetype_css(layout)}
</style></head><body>
<div class="banner"><b>Concept board — not the final build</b>
<span class="tier">{esc(TIER_LABEL.get(tier, tier.upper()))}</span>
<span>{esc(b.get('name',''))}</span><span class="one">{esc(one)}</span></div>
<nav><span class="wm">{esc(client_name)}</span><div class="nav-links">{''.join(f'<span>{esc(n)}</span>' for n in nav)}</div></nav>
<header class="hero"><div class="hero-in">{hero_inner}{aside}</div></header>
<section class="grid" id="catalog">{cards}</section>
<section class="band">{('<span class="sig">'+('Structural idea — ' if tier in ('bold','experimental') else 'Signature — ')+esc(sig)+'</span>') if sig else ''}<p>{esc(band)}</p></section>
<footer>{esc(client_name)} · concept board · {esc(tier)} · type-led where photography is pending</footer>
</body></html>"""


def render_root(client_name, boards):
    items = ""
    for b in boards:
        rec = ' &nbsp;★ recommended' if b.get("recommended") else ''
        items += (f'<li><a href="concepts/{esc(b["letter"])}/"><b>{esc(b.get("name",""))}</b> '
                  f'<em>({esc(b.get("tier","")) })</em>{rec}</a>'
                  f'<span>{esc(b.get("one_liner",""))}</span></li>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Concept boards — {esc(client_name)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:42rem;margin:3rem auto;padding:0 1.2rem;line-height:1.5}}
h1{{font-size:1.5rem}}ul{{list-style:none;padding:0}}li{{border-top:1px solid #ddd;padding:1rem 0}}
a{{font-size:1.1rem;text-decoration:none;color:#1a5}}em{{color:#888;font-style:normal;font-size:.8rem}}
span{{display:block;color:#555;font-size:.9rem;margin-top:.2rem}}.note{{color:#888;font-size:.8rem}}</style></head><body>
<h1>Concept boards — {esc(client_name)}</h1>
<p class="note">Classic → Confident → Bold (→ experimental). Homepage impressions; pick one in the studio dashboard. Each is a preview, not the final build. (noindex)</p>
<ul>{items}</ul></body></html>"""


def divergence_check(boards):
    """BINDING: the base (non-experimental) boards must differ in layout archetype AND typographic
    attitude AND structural idea. Returns (ok, problems[])."""
    base = [b for b in boards if b.get("tier") != "experimental"]
    problems = []
    if len(base) < 3:
        problems.append(f"need >=3 base boards spanning the spectrum; found {len(base)}")
    tiers = [b.get("tier", "") for b in base]
    for need in ("classic", "confident", "bold"):
        if need not in tiers:
            problems.append(f"missing spectrum tier: {need}")
    if sum(1 for b in base if b.get("recommended")) != 1:
        problems.append("exactly one base board must be recommended (the 'confident' one)")
    for field, label in (("layout", "layout archetype"), ("type_attitude", "typographic attitude"),
                         ("structural_idea", "structural idea")):
        vals = [(b.get(field) or TIER_LAYOUT.get(b.get("tier", ""), "") if field == "layout" else b.get(field) or "")
                for b in base]
        vals = [v for v in vals]
        if len(set(v.strip().lower() for v in vals)) < len(base):
            problems.append(f"boards do not all differ in {label}: {vals} — three palettes on one layout is a FAILURE")
    return (not problems), problems


def shoot(site_dir, concepts_dir, boards):
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
                    page.wait_for_timeout(700)   # let the experimental reveal settle to its end state
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
    for b in boards:                       # default layout from tier when not explicit
        b.setdefault("layout", TIER_LAYOUT.get(b.get("tier", "confident"), "editorial"))

    site_dir = concepts_dir / "site"
    (site_dir / "concepts").mkdir(parents=True, exist_ok=True)
    for b in boards:
        bdir = site_dir / "concepts" / b["letter"]
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "index.html").write_text(render_board(b, client_name))
    (site_dir / "index.html").write_text(render_root(client_name, boards))
    print(f"boards: {len(boards)} written ({', '.join(b['letter']+':'+b.get('tier','?') for b in boards)}) -> {site_dir}")

    ok, problems = divergence_check(boards)
    print("divergence test: " + ("PASS — boards differ in layout, type attitude, and structural idea" if ok
                                  else "FAIL\n  - " + "\n  - ".join(problems)))

    shoot(site_dir, concepts_dir, boards)

    manifest = {"generated": now(), "deploy_project": data.get("deploy_project", ""),
                "deploy_url": "", "divergence_pass": ok, "boards": []}
    for b in boards:
        stem = f"{b['letter']}-{b['id']}"
        manifest["boards"].append({
            "letter": b["letter"], "id": b["id"], "name": b.get("name", ""),
            "tier": b.get("tier", ""), "experimental": b.get("tier") == "experimental",
            "one_liner": b.get("one_liner", ""), "recommended": bool(b.get("recommended")),
            "path": f"concepts/{b['letter']}/",
            "thumb_desktop": f"{stem}.png", "thumb_mobile": f"{stem}-390.png"})
    (concepts_dir / "boards.json").write_text(json.dumps(manifest, indent=2))
    print(f"manifest: {concepts_dir/'boards.json'}")
    if not ok:
        sys.exit(2)   # signal regeneration is required


if __name__ == "__main__":
    main()
