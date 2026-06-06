#!/usr/bin/env python3
"""Web Studio dashboard v2 — concurrent pipelines, archiving, public-access ready.

Run locally:        python3 studio.py                  -> http://localhost:8788
Run public (temp):  ./tunnel.sh                        -> trycloudflare.com URL + token

Env config:
  STUDIO_HOST   bind address (default 127.0.0.1; tunnel.sh sets 0.0.0.0)
  STUDIO_PORT   default 8788
  STUDIO_TOKEN  access token; REQUIRED automatically when host isn't localhost.
                Open the dashboard as /?key=<token> once; a cookie keeps you in.
  MAX_SCRAPES   concurrent scrape limit (default 3); extra requests queue.

Lifecycle: new client -> scrape (concurrent, queued past the limit) -> Claude Code
assembles/finishes -> ARCHIVE button moves clients/<slug>/ to
archive/<slug>-<timestamp>/ (a fresh folder per finished project) and clears the row.
"""
import json, os, re, secrets, shutil, subprocess, sys, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
CLIENTS = ROOT / "clients"
ARCHIVE = ROOT / "archive"
BASELINE = ROOT / ".claude" / "skills" / "site-baseline" / "scripts" / "run_baseline.py"

HOST = os.environ.get("STUDIO_HOST", "127.0.0.1")
PORT = int(os.environ.get("STUDIO_PORT", "8788"))
MAX_SCRAPES = int(os.environ.get("MAX_SCRAPES", "3"))
TOKEN = os.environ.get("STUDIO_TOKEN", "")
if HOST not in ("127.0.0.1", "localhost") and not TOKEN:
    TOKEN = secrets.token_urlsafe(9)
    print(f"[studio] public bind without STUDIO_TOKEN — generated one: {TOKEN}")

SUBDIRS = ["00-source", "01-baseline", "02-intake/assets", "02-intake/specs",
           "02-intake/edits", "03-site", "04-cutover"]
LOCK = threading.Lock()
RUNNING = {}   # slug -> Popen
QUEUE = []     # [(slug, domain)]

NEXT = {
    "queued":           "Queued — waiting for a free scrape slot…",
    "created":          "Queued…",
    "scraping":         "Scraping in progress (3 methods)…",
    "error":            "Scrape error — see log; use Rerun.",
    "baseline-ready":   'In terminal:  claude  →  "Assemble prototype for {slug}"',
    "prototype":        "Prototype built — send the owner questionnaire.",
    "awaiting-owner":   "Waiting on owner — paste their answers below.",
    "answers-received": 'In terminal:  claude  →  "Finish {slug}"',
    "final":            'In terminal:  claude  →  "Run cutover prechecks for {slug}"',
    "cutover-checked":  "Launch-ready — follow 04-cutover/launch-runbook.md, then Archive.",
}

# ---------------- helpers ----------------
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
def slugify(s): return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-") or "client"

def read_status(d):
    try: return json.loads((d / "status.json").read_text())
    except Exception: return {"stage": "unknown", "log": []}

def write_status(d, st): (d / "status.json").write_text(json.dumps(st, indent=2))

def bump(d, stage=None, msg=None):
    st = read_status(d)
    if stage: st["stage"] = stage
    if msg: st.setdefault("log", []).append(f"{now()} {msg}")
    write_status(d, st)

def scaffold(name, domain):
    slug = slugify(name or domain.replace("https://", "").replace("http://", "").split("/")[0])
    cdir = CLIENTS / slug
    if cdir.exists():
        return slug, cdir, False
    for sd in SUBDIRS:
        (cdir / sd).mkdir(parents=True, exist_ok=True)
    write_status(cdir, {"name": name or slug, "domain": domain, "stage": "created",
                        "created": now(), "log": [f"{now()} scaffolded"]})
    return slug, cdir, True

def start_scrape(slug, domain):
    cdir = CLIENTS / slug
    bump(cdir, stage="scraping", msg="scrape started (crawl + mirror + render)")
    log = open(cdir / "00-source" / "scrape.log", "ab")
    RUNNING[slug] = subprocess.Popen(
        [sys.executable, str(BASELINE), domain, str(cdir)],
        stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))

def submit(slug, domain):
    with LOCK:
        if slug in RUNNING or any(s == slug for s, _ in QUEUE):
            return
        if len(RUNNING) < MAX_SCRAPES:
            start_scrape(slug, domain)
        else:
            bump(CLIENTS / slug, stage="queued",
                 msg=f"queued (limit {MAX_SCRAPES} concurrent scrapes)")
            QUEUE.append((slug, domain))

def worker():
    """Reap finished scrape processes and start queued ones."""
    while True:
        time.sleep(2)
        with LOCK:
            for slug, proc in list(RUNNING.items()):
                if proc.poll() is not None:
                    del RUNNING[slug]
            while QUEUE and len(RUNNING) < MAX_SCRAPES:
                slug, domain = QUEUE.pop(0)
                if (CLIENTS / slug).exists():
                    start_scrape(slug, domain)

def reap_orphans():
    """On startup: anything stuck in 'scraping' has no live process — mark for rerun."""
    if not CLIENTS.exists(): return
    for d in CLIENTS.iterdir():
        if d.is_dir() and read_status(d).get("stage") in ("scraping", "queued", "created"):
            bump(d, stage="error", msg="interrupted by studio restart — use Rerun")

def archive_client(slug):
    cdir = CLIENTS / slug
    if not cdir.exists(): return None
    with LOCK:
        if slug in RUNNING:
            RUNNING[slug].terminate(); del RUNNING[slug]
    ARCHIVE.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = ARCHIVE / f"{slug}-{ts}"
    st = read_status(cdir)
    st.setdefault("log", []).append(f"{now()} archived")
    st["archived"] = ts
    write_status(cdir, st)
    shutil.move(str(cdir), str(dest))
    return dest.name

def list_clients():
    out = []
    if not CLIENTS.exists(): return out
    for d in sorted(CLIENTS.iterdir()):
        if not d.is_dir() or d.name.startswith("."): continue
        st = read_status(d)
        stage = st.get("stage", "unknown")
        if stage == "prototype": stage = "awaiting-owner"
        out.append({"slug": d.name, "name": st.get("name", d.name),
                    "domain": st.get("domain", ""), "stage": stage,
                    "next": NEXT.get(stage, "—").format(slug=d.name),
                    "paste": stage == "awaiting-owner",
                    "rerun": stage == "error",
                    "done": stage in ("final", "cutover-checked"),
                    "log": st.get("log", [])[-3:]})
    return out

# ---------------- HTTP ----------------
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Web Studio</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Mono:wght@400;500&family=Public+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--ink:#0c1622;--panel:#122031;--panel2:#182a3f;--line:#2a3c52;--paper:#f4f1ea;
--amber:#ffb000;--amber2:#d98e00;--muted:#8fa1b5;
--d:"Barlow Condensed",sans-serif;--b:"Public Sans",sans-serif;--m:"IBM Plex Mono",monospace}
*{box-sizing:border-box}body{margin:0;background:var(--ink);color:var(--paper);font-family:var(--b);font-size:15px}
.wrap{max-width:60rem;margin:0 auto;padding:2.2rem 1.2rem}
h1{font-family:var(--d);font-size:2.4rem;text-transform:uppercase;margin:0}
.sub{font-family:var(--m);font-size:.66rem;letter-spacing:.22em;text-transform:uppercase;color:var(--amber);margin:.2rem 0 .4rem}
.stats{font-family:var(--m);font-size:.7rem;color:var(--muted);margin:0 0 1.8rem}
.card{background:var(--panel);border:1px solid var(--line);padding:1.2rem 1.4rem;margin:0 0 1rem}
.card h2{font-family:var(--d);font-size:1.3rem;text-transform:uppercase;margin:0 0 .7rem;color:var(--amber)}
form.new{display:flex;gap:.6rem;flex-wrap:wrap}
input,textarea{background:var(--ink);border:1px solid var(--line);color:var(--paper);
font-family:var(--m);font-size:.85rem;padding:.6rem .7rem;border-radius:2px}
input:focus,textarea:focus{outline:none;border-color:var(--amber)}
input.grow{flex:1;min-width:14rem}
button{background:var(--amber);border:1px solid var(--amber);color:var(--ink);
font-family:var(--d);font-weight:700;font-size:.95rem;text-transform:uppercase;letter-spacing:.04em;
padding:.5rem 1.1rem;cursor:pointer;border-radius:2px}
button:hover{background:transparent;color:var(--amber)}
button.ghost{background:transparent;color:var(--muted);border-color:var(--line);font-size:.8rem}
button.ghost:hover{color:var(--amber);border-color:var(--amber)}
button.done{background:#3a6b4f;border-color:#3a6b4f;color:#fff}
.row{border:1px solid var(--line);background:var(--panel);margin:0 0 .8rem;padding:1rem 1.2rem}
.row.fin{border-color:#3a6b4f}
.top{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;align-items:center}
.nm{font-family:var(--d);font-size:1.35rem;text-transform:uppercase}
.dom{font-family:var(--m);font-size:.72rem;color:var(--muted)}
.chip{font-family:var(--m);font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;
border:1px solid var(--amber2);color:var(--amber);padding:.25em .7em;white-space:nowrap}
.btns{display:flex;gap:.5rem;align-items:center}
.next{font-family:var(--m);font-size:.78rem;background:var(--panel2);
border-left:3px solid var(--amber);padding:.55rem .8rem;margin-top:.7rem}
.log{font-family:var(--m);font-size:.65rem;color:var(--muted);margin-top:.5rem;white-space:pre-wrap}
.paste{margin-top:.8rem;display:grid;gap:.5rem}.paste textarea{width:100%;min-height:7rem}
.empty{color:var(--muted);font-family:var(--m);font-size:.8rem}
</style></head><body><div class="wrap">
<h1>Web Studio</h1><p class="sub">Two human steps · everything else automated</p>
<p class="stats" id="stats"></p>
<div class="card"><h2>Step 1 — New client</h2>
<form class="new" onsubmit="return newClient(event)">
<input class="grow" name="domain" placeholder="https://example-client.com" required>
<input class="grow" name="name" placeholder="Client name (optional)">
<button>Start pipeline</button></form></div>
<div id="list"><p class="empty">Loading…</p></div>
</div><script>
async function api(path, body){
  const r = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)} : undefined);
  if(r.status===401){ document.body.innerHTML='<p style="font-family:monospace;color:#ffb000;padding:2rem">401 — reopen with ?key=&lt;token&gt;</p>'; throw 0; }
  return r.json();
}
async function load(){
  const d = await api('/api/clients');
  document.getElementById('stats').textContent =
    `active scrapes ${d.running}/${d.max} · queued ${d.queued} · archived projects ${d.archived}`;
  const el = document.getElementById('list');
  if(!d.clients.length){ el.innerHTML='<p class="empty">No active clients — start one above.</p>'; return; }
  el.innerHTML = d.clients.map(c=>`<div class="row${c.done?' fin':''}">
    <div class="top"><div><span class="nm">${c.name}</span> <span class="dom">${c.domain}</span></div>
    <div class="btns"><span class="chip">${c.stage}</span>
      ${c.rerun?`<button class="ghost" onclick="act('/rerun','${c.slug}')">Rerun</button>`:''}
      <button class="${c.done?'done':'ghost'}" onclick="if(confirm('Archive ${c.slug}? Moves it to archive/ and clears this row.'))act('/archive','${c.slug}')">Archive</button>
    </div></div>
    <div class="next">${c.next}</div>
    ${c.paste?`<form class="paste" onsubmit="return answers(event,'${c.slug}')">
      <textarea placeholder="Step 2 — paste the owner's questionnaire summary here…"></textarea>
      <button>Save owner answers</button></form>`:''}
    <div class="log">${c.log.join('\\n')}</div></div>`).join('');
}
async function newClient(e){ e.preventDefault();
  const f = e.target;
  await api('/new', {domain:f.domain.value, name:f.name.value}); f.reset(); load(); return false; }
async function answers(e,slug){ e.preventDefault();
  await api('/answers', {slug, t:e.target.querySelector('textarea').value}); load(); return false; }
async function act(p,slug){ await api(p,{slug}); load(); }
load(); setInterval(load, 4000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    # --- auth ---
    def authed(self):
        if not TOKEN: return True
        q = parse_qs(urlparse(self.path).query)
        if q.get("key", [""])[0] == TOKEN: return True
        cookies = self.headers.get("Cookie", "")
        return f"studio_key={TOKEN}" in cookies

    def _send(self, body, ctype="text/html", code=200, setcookie=False):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        if setcookie and TOKEN:
            self.send_header("Set-Cookie", f"studio_key={TOKEN}; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urlparse(self.path).path
        if not self.authed():
            return self._send("<p style='font-family:monospace;padding:2rem'>401 — open as /?key=&lt;your token&gt;</p>", code=401)
        if path == "/":
            self._send(PAGE, setcookie=True)
        elif path == "/api/clients":
            with LOCK:
                running, queued = len(RUNNING), len(QUEUE)
            archived = len(list(ARCHIVE.iterdir())) if ARCHIVE.exists() else 0
            self._send(json.dumps({"clients": list_clients(), "running": running,
                                   "max": MAX_SCRAPES, "queued": queued,
                                   "archived": archived}), "application/json")
        else:
            self._send("not found", code=404)

    def do_POST(self):
        if not self.authed():
            return self._send('{"error":"unauthorized"}', "application/json", 401)
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n).decode() or "{}")
        path = urlparse(self.path).path
        if path == "/new":
            domain = d.get("domain", "").strip()
            if domain:
                slug, cdir, fresh = scaffold(d.get("name", "").strip(), domain)
                if fresh:
                    submit(slug, domain)
        elif path == "/answers":
            cdir = CLIENTS / slugify(d.get("slug", ""))
            if cdir.exists() and d.get("t", "").strip():
                (cdir / "02-intake" / "owner-answers.txt").write_text(d["t"].strip())
                bump(cdir, stage="answers-received",
                     msg=f"owner answers received ({len(d['t'])} chars)")
        elif path == "/archive":
            archive_client(slugify(d.get("slug", "")))
        elif path == "/rerun":
            slug = slugify(d.get("slug", ""))
            cdir = CLIENTS / slug
            if cdir.exists():
                submit(slug, read_status(cdir).get("domain", ""))
        else:
            return self._send("not found", code=404)
        self._send("{}", "application/json")

if __name__ == "__main__":
    CLIENTS.mkdir(exist_ok=True)
    reap_orphans()
    threading.Thread(target=worker, daemon=True).start()
    scope = "PUBLIC (token required)" if HOST not in ("127.0.0.1", "localhost") else "local"
    print(f"Web Studio [{scope}] → http://{HOST}:{PORT}"
          + (f"/?key={TOKEN}" if TOKEN else "") + f"   · {MAX_SCRAPES} concurrent scrapes")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
