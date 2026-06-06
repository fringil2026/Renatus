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
# Environment: a Mac dev box opens a real Terminal via osascript; a Linux server
# exposes a web terminal (ttyd) behind the same tunnel/Access. Set STUDIO_ENV=server
# and STUDIO_TTYD_URL on the VPS (see deploy/).
import platform
IS_SERVER = os.environ.get("STUDIO_ENV", "").lower() == "server" or platform.system() != "Darwin"
TTYD_URL = os.environ.get("STUDIO_TTYD_URL", "")
if HOST not in ("127.0.0.1", "localhost") and not TOKEN:
    TOKEN = secrets.token_urlsafe(9)
    print(f"[studio] public bind without STUDIO_TOKEN — generated one: {TOKEN}")

SUBDIRS = ["00-source", "01-baseline", "02-intake/assets", "02-intake/specs",
           "02-intake/edits", "03-site", "04-cutover"]
LOCK = threading.Lock()
RUNNING = {}   # slug -> Popen   (scrape jobs)
QUEUE = []     # [(slug, domain)]

# Background Claude jobs (advance + chat). ONE Claude task per key at a time; key = slug,
# or "__studio__" for the unscoped studio chat. claude -p runs from ROOT under the existing
# settings.local.json allowlist — no bypass flags (out-of-allowlist commands fail visibly).
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
STUDIO_KEY = "__studio__"
TASKS = {}            # key -> {kind, label, started, tail[], proc}
TASK_LOCK = threading.Lock()

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

def parse_ts(s):
    try: return datetime.strptime(s, "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception: return None

def rel_time(s):
    t = parse_ts(s)
    if not t: return ""
    secs = (datetime.now(timezone.utc) - t).total_seconds()
    for div, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if secs >= div: return f"{int(secs // div)}{unit} ago"
    return "just now"

def site_newer_than(cdir, iso):
    """True if any 03-site source file is newer than the given preview timestamp. 03-site is
    git-ignored so there are no commits to compare — file mtime is the practical equivalent."""
    t = parse_ts(iso)
    if not t: return False
    site = cdir / "03-site"
    if not site.exists(): return False
    newest = 0.0
    for name in ("src", "public", "tokens.json", "astro.config.mjs"):
        p = site / name
        if p.is_file():
            newest = max(newest, p.stat().st_mtime)
        elif p.is_dir():
            for dp, _, fs in os.walk(p):
                for f in fs:
                    try: newest = max(newest, (Path(dp) / f).stat().st_mtime)
                    except OSError: pass
    return newest > t.timestamp()

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

def deliverables_blocking(cdir):
    """Parse 02-intake/deliverables-request.md for BLOCKING rows -> [{id, phase, status, what}]."""
    f = cdir / "02-intake" / "deliverables-request.md"
    rows, seen = [], set()
    if not f.exists(): return rows
    for ln in f.read_text().splitlines():
        if "BLOCKING" not in ln: continue
        m = re.search(r"\bD-2(?:\.\d+){1,2}\b", ln)
        if not m or m.group(0) in seen: continue
        did = m.group(0); seen.add(did)
        ph = re.search(r"\(P(\d)\)", ln)
        stt = re.search(r"\b(NEEDED|REQUESTED|RECEIVED|VERIFIED)\b", ln)
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rows.append({"id": did, "phase": int(ph.group(1)) if ph else None,
                     "status": stt.group(1) if stt else "NEEDED",
                     "what": (cells[1][:60] if len(cells) > 1 else did)})
    return rows

def phase_gate(cdir, n):
    """(relevant BLOCKING rows for phase n, unmet ones not RECEIVED/VERIFIED)."""
    rel = [r for r in deliverables_blocking(cdir) if r["phase"] == n]
    unmet = [r for r in rel if r["status"] not in ("RECEIVED", "VERIFIED")]
    return rel, unmet

def advance_action(slug, st):
    """Server-side stage->next-action map. Returns {label, command, enabled, tooltip, desc} or None."""
    stage = st.get("stage", "")
    busy = slug in TASKS
    def mk(label, command, enabled=True, tooltip="", desc=""):
        if busy:
            enabled, tooltip = False, "a Claude task is already running for this client"
        return {"label": label, "command": command, "enabled": enabled, "tooltip": tooltip, "desc": desc}
    if stage == "baseline-ready":
        return mk(f"Assemble prototype for {slug}", f"Assemble prototype for {slug}",
                  desc="Reads the baseline, copies the archetype into 03-site, drafts content, builds, and publishes the preview.")
    if stage == "prototype":   # P1 done; next is P2, gated on its BLOCKING deliverables
        rel, unmet = phase_gate(CLIENTS / slug, 2)
        cmd = f"Implement Phase 2 of the spec in clients/{slug}/02-intake/specs/"
        if unmet:
            return mk("Implement Phase 2 (blocked)", cmd, enabled=False,
                      tooltip="Unmet BLOCKING deliverables: " + "; ".join(f"{u['what']} ({u['id']})" for u in unmet))
        return mk("Implement Phase 2", cmd, desc="Builds the next spec phase; then verifies and publishes.")
    if stage == "answers-received":
        return mk(f"Finish {slug}", f"Finish {slug}",
                  desc="Applies the owner's answers, replaces DRAFT content, finalizes, builds, and publishes.")
    if stage == "final":
        return mk(f"Run cutover prechecks for {slug}", f"Run cutover prechecks for {slug}",
                  desc="Runs the launch checks and writes reports into 04-cutover/.")
    return None  # queued/scraping/created/error/awaiting-owner(no real action)/cutover-checked

def run_advance(slug, command):
    """Run `claude -p <command>` from ROOT in the background. Start/finish lines go to status.json
    (written only when the claude subprocess is NOT running, to avoid clobbering the file it owns);
    live snippets stream into the in-memory task tail shown on the dashboard."""
    cdir = CLIENTS / slug
    bump(cdir, msg=f'advance started: claude -p "{command}"')   # safe: before spawn
    try:
        proc = subprocess.Popen([CLAUDE_BIN, "-p", command], cwd=str(ROOT),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        bump(cdir, msg=f"advance FAILED to start: {e}")
        with TASK_LOCK: TASKS.pop(slug, None)
        return
    with TASK_LOCK:
        TASKS[slug] = {"kind": "advance", "label": command, "started": now(), "tail": [], "proc": proc}
    tail = TASKS[slug]["tail"]
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            tail.append(line)
            del tail[:-60]
    rc = proc.wait()
    if rc == 0:
        bump(cdir, msg="advance finished ok")          # safe: claude has exited
    else:
        st = read_status(cdir)
        st["advance_failed"] = True
        st.setdefault("log", []).append(f"{now()} advance FAILED (exit {rc}) — tail: " + " / ".join(tail[-5:])[:400])
        write_status(cdir, st)
    with TASK_LOCK: TASKS.pop(slug, None)

def chat_paths(key):
    """(transcript jsonl, session-id file) for a chat key (slug, or STUDIO_KEY)."""
    if key == STUDIO_KEY:
        return ROOT / ".claude" / ".studio-chat.jsonl", ROOT / ".claude" / ".studio-session"
    cdir = CLIENTS / key
    return cdir / ".claude-chat.jsonl", cdir / ".claude-session"

def append_chat(key, entry):
    f, _ = chat_paths(key)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a") as fh:
        fh.write(json.dumps(entry) + "\n")

def read_chat(key):
    f, _ = chat_paths(key)
    if not f.exists(): return []
    out = []
    for ln in f.read_text().splitlines():
        try: out.append(json.loads(ln))
        except Exception: pass
    return out

def run_chat(key, message):
    """Background `claude -p` chat turn. stream-json is used (superset of json) so tool actions
    can be summarized; session_id is captured to .claude-session and --resume keeps continuity."""
    scoped = None if key == STUDIO_KEY else key
    _, sess_file = chat_paths(key)
    preamble = "" if scoped is None else (
        f"[Dashboard message for client {scoped} — work only within clients/{scoped}/ "
        f"unless explicitly told otherwise]\n")
    sess = sess_file.read_text().strip() if sess_file.exists() else ""
    cmd = [CLAUDE_BIN, "-p", preamble + message, "--output-format", "stream-json", "--verbose"]
    if sess:
        cmd += ["--resume", sess]
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except Exception as e:
        append_chat(key, {"role": "error", "text": f"failed to start claude: {e}", "at": now()})
        with TASK_LOCK: TASKS.pop(key, None)
        return
    with TASK_LOCK:
        TASKS[key] = {"kind": "chat", "label": message[:60], "started": now(), "tail": [], "proc": proc}
    reply, tools, new_sess = [], [], ""
    for line in proc.stdout:
        line = line.strip()
        if not line: continue
        try: ev = json.loads(line)
        except Exception: continue
        t = ev.get("type")
        if ev.get("session_id"): new_sess = ev["session_id"]
        if t == "assistant":
            for blk in ev.get("message", {}).get("content", []):
                if blk.get("type") == "text" and blk.get("text", "").strip():
                    reply.append(blk["text"])
                elif blk.get("type") == "tool_use":
                    inp = blk.get("input", {}) or {}
                    d = inp.get("file_path") or inp.get("command") or inp.get("path") or inp.get("pattern") or ""
                    tools.append(f"{blk.get('name')}: {str(d)[:80]}".strip())
        elif t == "result" and ev.get("result") and not reply:
            reply.append(ev["result"])
    rc = proc.wait()
    err = (proc.stderr.read() or "")[-600:] if proc.stderr else ""
    if new_sess:
        sess_file.write_text(new_sess)
    if rc == 0:
        append_chat(key, {"role": "assistant", "text": ("\n".join(reply)[:6000] or "(no text reply)"),
                          "tools": tools[:30], "at": now()})
    else:
        append_chat(key, {"role": "error", "text": f"claude exited {rc}\n{err}".strip(),
                          "tools": tools[:30], "at": now()})
    with TASK_LOCK: TASKS.pop(key, None)

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
                    "preview_url": st.get("preview_url", ""),
                    "production_url": st.get("production_url", ""),
                    "preview_stale": st.get("preview_stale", False),
                    "preview_at": st.get("preview_published_at", ""),
                    "preview_rel": rel_time(st.get("preview_published_at", "")),
                    "preview_behind": bool(st.get("preview_url")) and site_newer_than(d, st.get("preview_published_at", "")),
                    "advance_failed": st.get("advance_failed", False),
                    "advance": advance_action(d.name, st),
                    "busy": d.name in TASKS,
                    "task_tail": TASKS.get(d.name, {}).get("tail", [])[-6:] if d.name in TASKS else [],
                    "log": st.get("log", [])[-4:]})
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
.prev{font-family:var(--m);font-size:.7rem;margin-top:.5rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.prev a{color:var(--amber);text-decoration:none}
.prev a.pvw{border:1px solid var(--amber2);padding:.1em .55em}
.prev a.live{background:#3a6b4f;color:#fff;border:1px solid #3a6b4f;padding:.12em .6em;font-weight:600}
.prev .pdate,.prev .purl{color:var(--muted)}
.prev .copy{cursor:pointer;color:var(--muted)}.prev .copy:hover{color:var(--amber)}
.prev .stale{color:#ff5d5d;font-weight:600}
.paste{margin-top:.8rem;display:grid;gap:.5rem}.paste textarea{width:100%;min-height:7rem}
.drop{margin-top:.7rem;display:flex;gap:.7rem;align-items:center;flex-wrap:wrap;font-family:var(--m);font-size:.7rem;color:var(--muted)}
.drop input[type=file]{font-size:.7rem;max-width:16rem}
.drop label{display:flex;gap:.25rem;align-items:center;cursor:pointer}
.empty{color:var(--muted);font-family:var(--m);font-size:.8rem}
button.adv{background:transparent;color:var(--amber);border-color:var(--amber2);font-size:.82rem}
button.adv:hover:not([disabled]){background:var(--amber);color:var(--ink)}
button.adv[disabled]{color:var(--muted);border-color:var(--line);cursor:not-allowed;opacity:.6}
.run{font-family:var(--m);font-size:.66rem;color:#7fd18f}
.tasktail{font-family:var(--m);font-size:.62rem;color:#7fd18f;background:#0a1a10;border-left:3px solid #3a6b4f;
padding:.5rem .7rem;margin-top:.5rem;white-space:pre-wrap;max-height:9rem;overflow:auto}
.modal{position:fixed;inset:0;background:rgba(4,9,14,.78);display:flex;align-items:center;justify-content:center;z-index:50}
.modalbox{background:var(--panel);border:1px solid var(--amber2);padding:1.6rem;max-width:34rem;width:92%}
.modalbox h3{font-family:var(--d);text-transform:uppercase;color:var(--amber);margin:0 0 .6rem}
.m-desc{font-size:.85rem}.m-cmd{font-family:var(--m);font-size:.72rem;background:var(--ink);padding:.5rem .7rem;border:1px solid var(--line);word-break:break-word}
.m-unmet{font-family:var(--m);font-size:.7rem;color:#ff8a8a}
.m-lab{display:block;font-family:var(--m);font-size:.72rem;color:var(--muted);margin:.8rem 0 .3rem}
#m-input{width:100%}.m-btns{display:flex;gap:.6rem;margin-top:1rem}
.chatpanel{margin-top:.7rem;border:1px solid var(--line);background:var(--panel2);padding:.7rem}
.chatlog{max-height:18rem;overflow:auto;display:flex;flex-direction:column;gap:.5rem;margin-bottom:.6rem}
.msg{font-size:.8rem;padding:.45rem .6rem;border-radius:3px;white-space:pre-wrap;word-break:break-word}
.msg.user{background:#13283c;border-left:3px solid var(--amber)}
.msg.assistant{background:#0e1f17;border-left:3px solid #3a6b4f}
.msg.error{background:#2a1414;border-left:3px solid #ff5d5d;color:#ffb3b3}
.msg .who{font-family:var(--m);font-size:.58rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);display:block;margin-bottom:.2rem}
.msg .tools{font-family:var(--m);font-size:.6rem;color:#7fae8f;margin-top:.35rem}
.chatform{display:flex;gap:.5rem}.chatform textarea{flex:1;min-height:3.2rem}
.chatform button{align-self:flex-end}
.chatrun{font-family:var(--m);font-size:.62rem;color:#7fd18f;margin-bottom:.4rem}
</style></head><body><div class="wrap">
<h1>Web Studio</h1><p class="sub">Two human steps · everything else automated</p>
<p class="stats" id="stats"></p>
<div class="card"><h2>Step 1 — New client</h2>
<form class="new" onsubmit="return newClient(event)">
<input class="grow" name="domain" placeholder="https://example-client.com" required>
<input class="grow" name="name" placeholder="Client name (optional)">
<button>Start pipeline</button></form>
<div style="margin-top:.9rem">
  <button class="ghost" onclick="openSession('studio')">Claude: Studio (terminal)</button>
  <button class="ghost" onclick="toggleChat('studio')">Studio chat ▾</button>
</div>
<div id="chat-studio" class="chatpanel" style="display:none">
  <div class="chatlog" id="chatlog-studio"></div>
  <form class="chatform" onsubmit="return sendChat(event,'studio')">
    <textarea id="cin-studio" placeholder="Message Claude (studio-wide, unscoped)…" required></textarea>
    <button>Send</button></form>
</div></div>
<div id="list"><p class="empty">Loading…</p></div>
</div>
<div id="modal" class="modal" style="display:none"><div class="modalbox">
  <h3 id="m-title"></h3>
  <p id="m-desc" class="m-desc"></p>
  <p id="m-cmd" class="m-cmd"></p>
  <div id="m-unmet" class="m-unmet"></div>
  <label class="m-lab">Type the client slug to confirm: <b id="m-slug"></b></label>
  <input id="m-input" placeholder="slug" autocomplete="off">
  <div class="m-btns"><button id="m-run">Run</button><button class="ghost" onclick="closeModal()">Cancel</button></div>
</div></div>
<script>
async function api(path, body){
  const r = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)} : undefined);
  if(r.status===401){ document.body.innerHTML='<p style="font-family:monospace;color:#ffb000;padding:2rem">401 — reopen with ?key=&lt;token&gt;</p>'; throw 0; }
  return r.json();
}
let DATA = {clients:[]};
const chatOpen = new Set();      // chat keys currently expanded
const chatDraft = {};            // key -> unsent textarea text (preserved across refreshes)
function esc(s){ return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function findC(slug){ return DATA.clients.find(x=>x.slug===slug); }
async function openSession(key){ await api('/open',{slug:key==='studio'?'':key, studio:key==='studio'}); }
function saveDrafts(){ chatOpen.forEach(k=>{ const t=document.getElementById('cin-'+k); if(t) chatDraft[k]=t.value; }); }
function restoreChats(){ chatOpen.forEach(k=>{ const p=document.getElementById('chat-'+k); if(p){ p.style.display='block';
  const t=document.getElementById('cin-'+k); if(t&&chatDraft[k]!==undefined) t.value=chatDraft[k]; renderChat(k);} }); }
function toggleChat(key){ const p=document.getElementById('chat-'+key); if(!p) return;
  if(chatOpen.has(key)){ chatOpen.delete(key); p.style.display='none'; }
  else { chatOpen.add(key); p.style.display='block'; renderChat(key); } }
async function renderChat(key){
  const log=document.getElementById('chatlog-'+key); if(!log) return;
  const r=await api('/api/chat?slug='+encodeURIComponent(key));
  log.innerHTML=(r.running?'<div class="chatrun">● Claude is working…</div>':'')
    + r.messages.map(m=>`<div class="msg ${m.role}"><span class="who">${m.role}</span>${esc(m.text)}`
      +((m.tools&&m.tools.length)?`<div class="tools">↳ ${m.tools.map(esc).join('<br>↳ ')}</div>`:'')+`</div>`).join('');
  log.scrollTop=log.scrollHeight;
}
async function sendChat(e,key){ e.preventDefault();
  const t=document.getElementById('cin-'+key); const msg=t.value.trim(); if(!msg) return false;
  const r=await api('/api/chat',{slug:key,message:msg});
  if(r.error){ alert('Chat: '+r.error); return false; }
  t.value=''; chatDraft[key]=''; renderChat(key); return false; }
function cpCmd(slug){ const c=findC(slug); if(c&&c.advance) cp('claude -p "'+c.advance.command+'"'); }
function closeModal(){ document.getElementById('modal').style.display='none'; }
function openAdvance(slug){
  const c=findC(slug); if(!c||!c.advance||!c.advance.enabled) return;
  document.getElementById('m-title').textContent=c.advance.label;
  document.getElementById('m-desc').textContent=c.advance.desc||'';
  document.getElementById('m-cmd').textContent='claude -p "'+c.advance.command+'"';
  document.getElementById('m-unmet').textContent=c.advance.tooltip||'';
  document.getElementById('m-slug').textContent=slug;
  const inp=document.getElementById('m-input'); inp.value='';
  document.getElementById('m-run').onclick=async()=>{
    const r=await api('/api/advance',{slug,confirm:inp.value.trim()});
    if(r.error){ alert('Cannot run: '+r.error); } else { closeModal(); load(); }
  };
  document.getElementById('modal').style.display='flex'; inp.focus();
}
async function load(){
  saveDrafts();
  const d = await api('/api/clients'); DATA = d;
  document.getElementById('stats').textContent =
    `active scrapes ${d.running}/${d.max} · queued ${d.queued} · archived projects ${d.archived}`;
  const el = document.getElementById('list');
  if(!d.clients.length){ el.innerHTML='<p class="empty">No active clients — start one above.</p>'; return; }
  el.innerHTML = d.clients.map(c=>`<div class="row${c.done?' fin':''}">
    <div class="top"><div><span class="nm">${c.name}</span> <span class="dom">${c.domain}</span></div>
    <div class="btns"><span class="chip">${c.stage}</span>
      ${c.busy?'<span class="run">● running…</span>':''}
      ${c.advance?`<button class="adv" ${c.advance.enabled?'':'disabled'} title="${(c.advance.tooltip||c.advance.desc||'').replace(/"/g,'&quot;')}" onclick="openAdvance('${c.slug}')">${c.advance.label}</button><span class="copy" title="Copy terminal command" onclick="cpCmd('${c.slug}')">⧉</span>`:''}
      ${d.server?(d.ttyd_url?`<a class="ghost" href="${d.ttyd_url}" target="_blank" rel="noopener">Open session ↗</a>`:''):`<button class="ghost" onclick="api('/open',{slug:'${c.slug}'})">Claude: ${c.name}</button>`}
      ${c.rerun?`<button class="ghost" onclick="act('/rerun','${c.slug}')">Rerun</button>`:''}
      <button class="${c.done?'done':'ghost'}" onclick="if(confirm('Archive ${c.slug}? Moves it to archive/ and clears this row.'))act('/archive','${c.slug}')">Archive</button>
    </div></div>
    <div class="next">${c.next}</div>
    ${c.busy&&c.task_tail.length?`<div class="tasktail">${c.task_tail.map(t=>t.replace(/[<>]/g,'')).join('\\n')}</div>`:''}
    ${c.advance_failed&&!c.busy?`<div class="prev"><span class="stale">⚠ advance failed — see log</span></div>`:''}
    ${c.production_url?`<div class="prev"><a class="live" href="${c.production_url}" target="_blank" rel="noopener">Live ↗</a> <span class="copy" title="Copy URL" onclick="cp('${c.production_url}')">⧉</span> <span class="purl">${c.production_url}</span></div>`:''}
    ${c.preview_url?`<div class="prev"><a class="pvw" href="${c.preview_url}" target="_blank" rel="noopener">Preview ↗</a> <span class="copy" title="Copy URL" onclick="cp('${c.preview_url}')">⧉</span> <span class="pdate">${c.preview_rel||c.preview_at}</span>${c.preview_stale?' <span class="stale">⚠ last deploy failed</span>':(c.preview_behind?' <span class="stale">⚠ preview behind latest edits</span>':'')}</div>`:''}
    <form class="drop" onsubmit="return up(event,'${c.slug}')">
      <input type="file" accept=".md" required>
      <label><input type="radio" name="dest-${c.slug}" value="specs" checked> specs</label>
      <label><input type="radio" name="dest-${c.slug}" value="edits"> edits</label>
      <button class="ghost">Upload .md</button>
      <button type="button" class="ghost" onclick="toggleChat('${c.slug}')">Chat ▾</button>
    </form>
    <div id="chat-${c.slug}" class="chatpanel" style="display:none">
      <div class="chatlog" id="chatlog-${c.slug}"></div>
      <form class="chatform" onsubmit="return sendChat(event,'${c.slug}')">
        <textarea id="cin-${c.slug}" placeholder="Message Claude about ${c.name} (scoped to clients/${c.slug}/)…" required></textarea>
        <button>Send</button></form>
    </div>
    ${c.paste?`<form class="paste" onsubmit="return answers(event,'${c.slug}')">
      <textarea placeholder="Step 2 — paste the owner's questionnaire summary here…"></textarea>
      <button>Save owner answers</button></form>`:''}
    <div class="log">${c.log.join('\\n')}</div></div>`).join('');
  restoreChats();
}
async function newClient(e){ e.preventDefault();
  const f = e.target;
  await api('/new', {domain:f.domain.value, name:f.name.value}); f.reset(); load(); return false; }
async function answers(e,slug){ e.preventDefault();
  await api('/answers', {slug, t:e.target.querySelector('textarea').value}); load(); return false; }
async function act(p,slug){ await api(p,{slug}); load(); }
function cp(t){ navigator.clipboard&&navigator.clipboard.writeText(t); }
async function up(e,slug){ e.preventDefault();
  const f=e.target, file=f.querySelector('input[type=file]').files[0];
  if(!file) return false;
  if(!file.name.toLowerCase().endsWith('.md')){ alert('Only .md files'); return false; }
  const dest=f.querySelector('input[name="dest-'+slug+'"]:checked').value;
  const content=await file.text();
  const r=await api('/api/upload',{slug,dest,filename:file.name,content});
  if(r.error) alert('Upload failed: '+r.error); else { f.reset(); load(); }
  return false; }
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
                                   "archived": archived, "server": IS_SERVER,
                                   "ttyd_url": TTYD_URL}), "application/json")
        elif path == "/api/chat":
            q = parse_qs(urlparse(self.path).query)
            slug = q.get("slug", [""])[0]
            key = STUDIO_KEY if slug in ("", "studio") else slugify(slug)
            self._send(json.dumps({"messages": read_chat(key), "running": key in TASKS}),
                       "application/json")
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
        elif path == "/api/upload":
            slug = slugify(d.get("slug", ""))
            dest = d.get("dest", "")
            fname = Path(d.get("filename", "")).name  # strip any path components
            content = d.get("content", "")
            cdir = CLIENTS / slug
            if not cdir.exists():
                return self._send(json.dumps({"error": "no such client"}), "application/json", 404)
            if dest not in ("specs", "edits"):
                return self._send(json.dumps({"error": "dest must be specs or edits"}), "application/json", 400)
            if not fname.lower().endswith(".md") or fname.startswith("."):
                return self._send(json.dumps({"error": "only .md files allowed"}), "application/json", 400)
            target = cdir / "02-intake" / dest / fname
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            bump(cdir, msg=f"uploaded {dest}/{fname} ({len(content)} chars) via dashboard")
            return self._send(json.dumps({"ok": True, "path": f"02-intake/{dest}/{fname}"}), "application/json")
        elif path == "/api/advance":
            slug = slugify(d.get("slug", ""))
            cdir = CLIENTS / slug
            if not cdir.exists():
                return self._send(json.dumps({"error": "no such client"}), "application/json", 404)
            act = advance_action(slug, read_status(cdir))   # revalidate server-side
            if not act or not act.get("enabled"):
                return self._send(json.dumps({"error": act.get("tooltip") if act else "nothing to advance"}), "application/json", 400)
            if d.get("confirm", "") != slug:
                return self._send(json.dumps({"error": "type the slug exactly to confirm"}), "application/json", 400)
            with TASK_LOCK:
                if slug in TASKS:
                    return self._send(json.dumps({"error": "a Claude task is already running for this client"}), "application/json", 409)
                TASKS[slug] = {"kind": "advance", "label": act["command"], "started": now(), "tail": [], "proc": None}
            threading.Thread(target=run_advance, args=(slug, act["command"]), daemon=True).start()
            return self._send(json.dumps({"ok": True}), "application/json")
        elif path == "/api/chat":
            slug = d.get("slug", "")
            key = STUDIO_KEY if slug in ("", "studio") else slugify(slug)
            msg = (d.get("message", "") or "").strip()
            if key != STUDIO_KEY and not (CLIENTS / key).exists():
                return self._send(json.dumps({"error": "no such client"}), "application/json", 404)
            if not msg:
                return self._send(json.dumps({"error": "empty message"}), "application/json", 400)
            with TASK_LOCK:
                if key in TASKS:
                    return self._send(json.dumps({"error": "a Claude task is already running here"}), "application/json", 409)
                TASKS[key] = {"kind": "chat", "label": msg[:60], "started": now(), "tail": [], "proc": None}
            append_chat(key, {"role": "user", "text": msg, "at": now()})
            threading.Thread(target=run_chat, args=(key, msg), daemon=True).start()
            return self._send(json.dumps({"ok": True}), "application/json")
        elif path == "/archive":
            archive_client(slugify(d.get("slug", "")))
        elif path == "/rerun":
            slug = slugify(d.get("slug", ""))
            cdir = CLIENTS / slug
            if cdir.exists():
                submit(slug, read_status(cdir).get("domain", ""))
        elif path == "/open":
            # macOS-local until cloud migration: open a Terminal running Claude Code from ROOT.
            # Studio = unscoped; per-client = a scoped briefing prompt. (On a server the UI links
            # to ttyd instead and never calls this.)
            if not IS_SERVER:
                if d.get("studio") or not d.get("slug"):
                    inner = f"cd {ROOT} && claude"
                else:
                    slug = slugify(d.get("slug", ""))
                    prompt = (f"Working on client {slug} — stay within clients/{slug}/ unless I say "
                              f"otherwise. Summarize its stage, pending edits, and BLOCKING "
                              f"deliverables, then await instruction.")
                    inner = f"cd {ROOT} && claude '{prompt}'"
                osa = f'tell application "Terminal" to do script "{inner}"'
                try:
                    subprocess.Popen(["osascript", "-e", osa, "-e",
                                      'tell application "Terminal" to activate'])
                except Exception as e:
                    return self._send(json.dumps({"error": str(e)}), "application/json", 500)
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
