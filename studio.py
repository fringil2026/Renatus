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
           "02-intake/edits", "02-intake/secrets", "03-site", "04-cutover"]
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

# Status DESCRIPTIONS only — never a command to type. Every actionable stage carries a real
# button (see advance_action / full_build_action); the "Copy command" ⧉ link is the terminal
# escape hatch. No ".next" line ever instructs the human to run something in a terminal.
NEXT = {
    "queued":           "Queued — waiting for a free scrape slot…",
    "created":          "Queued…",
    "scraping":         "Scraping in progress (3 methods)…",
    "error":            "Scrape error — see the log, then use Rerun.",
    "baseline-ready":   "Baseline ready — pick a concept board, then Assemble (or run a Full build).",
    "prototype":        "Prototype built — send the owner questionnaire, or run a Full build from here.",
    "awaiting-owner":   "Prototype built — paste the owner's answers below when they arrive.",
    "answers-received": "Owner answers received — Finish to apply them.",
    "final":            "Final build complete — run the cutover prechecks.",
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
    """Reap finished scrape processes, start queued ones, and auto-prepare the intake pack
    the moment a client reaches baseline-ready."""
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
        # auto intake-pack: stage flipped to baseline-ready and no pack yet
        if CLIENTS.exists():
            for d in CLIENTS.iterdir():
                if not d.is_dir() or d.name.startswith("."):
                    continue
                if read_status(d).get("stage") != "baseline-ready":
                    continue
                if (d / "02-intake" / "redesign-plan.md").exists():
                    continue
                slug = d.name
                with TASK_LOCK:
                    if slug in TASKS:
                        continue
                    TASKS[slug] = {"kind": "intake pack", "label": "prepare intake pack", "started": now(), "tail": [], "proc": None}
                threading.Thread(target=run_advance,
                                 args=(slug, f"Prepare intake pack for {slug}", "intake pack", None),
                                 daemon=True).start()

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
    if stage == "prototype":   # P1 done; next is P2 — gated on BLOCKING deliverables AND a BINDING backend-config
        rel, unmet = phase_gate(CLIENTS / slug, 2)
        cfg = parse_backend_config(CLIENTS / slug)
        rehearsal = bool(cfg and cfg.get("mode") == "rehearsal")
        cmd = f"Implement Phase 2 of the spec in clients/{slug}/02-intake/specs/ per its BINDING backend-config"
        blockers = []
        if unmet and not rehearsal:   # rehearsal satisfies deliverables via studio test resources
            blockers.append("BLOCKING deliverables: " + "; ".join(f"{u['what']} ({u['id']})" for u in unmet))
        if not (cfg and cfg.get("status") == "BINDING"):
            blockers.append("no BINDING backend-config — use Configure backend")
        badge = "REHEARSAL" if rehearsal else ""
        if blockers:
            return {**mk("Implement Phase 2 (blocked)", cmd, enabled=False, tooltip=" · ".join(blockers)), "badge": badge}
        return {**mk("Implement Phase 2", cmd,
                     desc=("REHEARSAL — builds Phase 2 against studio test resources (Supabase/Stripe-test/Resend-test); every surface shows TEST MODE." if rehearsal
                           else "Builds Phase 2 per the binding backend-config; then verifies and publishes.")), "badge": badge}
    if stage == "answers-received":
        return mk(f"Finish {slug}", f"Finish {slug}",
                  desc="Applies the owner's answers, replaces DRAFT content, finalizes, builds, and publishes.")
    if stage == "final":
        return mk(f"Run cutover prechecks for {slug}", f"Run cutover prechecks for {slug}",
                  desc="Runs the launch checks and writes reports into 04-cutover/.")
    return None  # queued/scraping/created/error/awaiting-owner(no real action)/cutover-checked

def run_advance(slug, command, kind="advance", fail_flag="advance_failed"):
    """Run `claude -p <command>` from ROOT in the background (used by Advance + backend proposal).
    Start/finish lines go to status.json only when the claude subprocess is NOT running (avoids
    clobbering the file it owns); live snippets stream into the in-memory task tail on the row."""
    cdir = CLIENTS / slug
    bump(cdir, msg=f'{kind} started: claude -p "{command}"')   # safe: before spawn
    try:
        proc = subprocess.Popen([CLAUDE_BIN, "-p", command], cwd=str(ROOT),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        bump(cdir, msg=f"{kind} FAILED to start: {e}")
        with TASK_LOCK: TASKS.pop(slug, None)
        return
    with TASK_LOCK:
        TASKS[slug] = {"kind": kind, "label": command, "started": now(), "tail": [], "proc": proc}
    tail = TASKS[slug]["tail"]
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            tail.append(line)
            del tail[:-60]
    rc = proc.wait()
    if rc == 0:
        bump(cdir, msg=f"{kind} finished ok")          # safe: claude has exited
    else:
        st = read_status(cdir)
        if fail_flag: st[fail_flag] = True
        st.setdefault("log", []).append(f"{now()} {kind} FAILED (exit {rc}) — tail: " + " / ".join(tail[-5:])[:400])
        write_status(cdir, st)
    with TASK_LOCK: TASKS.pop(slug, None)

# ---------------- full build (one-click chained rehearsal build) ----------------
# Two variants share ONE underlying chain; entry point + step list differ by stage.
#   from-scratch    (baseline-ready, no prototype): scrape→assemble(auto-accept concept)→…→publish
#   from-prototype  (prototype & later): PRESERVE the built prototype; run only what's missing.
# studio.py owns the control surface (button, slug-typed confirm, precondition gate, the
# step artifact, the row step-log, and resume). The chain itself is executed by `claude -p`
# driving the runbook below; Claude updates 02-intake/full-build-progress.json after each step,
# so the build is resumable (re-running skips steps already marked done) and the row shows live
# progress. TEST banners + cutover-refusal are unchanged (enforced by the existing guarantees).
FULL_BUILD_STEPS = {
    "from-scratch": [
        ("precond",  "Precondition — TEST credentials present + tagged REHEARSAL"),
        ("rehearsal","Enter rehearsal mode (backend-config mode: rehearsal; TEST banners on)"),
        ("scrape",   "Complete-coverage re-scrape + full-catalog extraction (cover-paired, DRAFT facts)"),
        ("assemble", "Assemble prototype to the RECOMMENDED concept (auto-accepted) — parity floor, build, publish"),
        ("config",   "Propose + auto-bind backend config (DRAFT→BINDING) from the evidence"),
        ("phase2",   "Phase 2 — Supabase catalog/admin/content + RLS/audit on test resources"),
        ("phase3",   "Phase 3 — Stripe TEST checkout + orders webhook"),
        ("phase4",   "Phase 4 — Resend test domain: notify + comms loop"),
        ("publish",  "Final build + publish preview; refresh status.json"),
    ],
    "from-prototype": [
        ("precond",  "Precondition — TEST credentials present + tagged REHEARSAL"),
        ("rehearsal","Enter rehearsal mode (if not already)"),
        ("preserve", "Verify existing prototype intact — processed edits, chosen concept, design KEPT as built"),
        ("config",   "Backend config — auto-bind if none BINDING; if a BINDING config exists, USE it untouched"),
        ("phase2",   "Phase 2 — Supabase catalog/admin/content + RLS/audit on test resources"),
        ("phase3",   "Phase 3 — Stripe TEST checkout + orders webhook"),
        ("phase4",   "Phase 4 — Resend test domain: notify + comms loop"),
        ("publish",  "Final build + publish preview; refresh status.json"),
    ],
}

def test_creds_ready(cdir):
    """Precondition for a full REHEARSAL build: a secrets/.env with at least the rehearsal
    Supabase test creds, tagged # REHEARSAL. Secrets are git-ignored, read-only here."""
    f = cdir / "02-intake" / "secrets" / ".env"
    if not f.exists():
        return False
    txt = f.read_text()
    return ("SUPABASE_URL" in txt) and ("# REHEARSAL" in txt or "#REHEARSAL" in txt)

def fb_progress_path(cdir): return cdir / "02-intake" / "full-build-progress.json"

def read_full_build(cdir):
    f = fb_progress_path(cdir)
    if not f.exists(): return None
    try: return json.loads(f.read_text())
    except Exception: return None

def init_full_build(cdir, variant):
    steps = [{"id": k, "title": t, "status": "pending", "note": "", "at": ""}
             for k, t in FULL_BUILD_STEPS.get(variant, [])]
    prog = {"variant": variant, "started": now(), "updated": now(), "blocked_on": "", "steps": steps}
    fb_progress_path(cdir).write_text(json.dumps(prog, indent=2))
    return prog

# ---------------- creativity model: STANDARD / PUSH FURTHER / OVERHAUL(=creative) ----------------
# ONE flag (design_mode), TWO entry points (build-start + the boards Overhaul button), TWO input
# modes (claude / brief). "creative mode" and "the overhaul button" are the SAME capability.
def set_design_mode(cdir, mode, input_mode=""):
    st = read_status(cdir); st["design_mode"] = mode
    if input_mode:
        st["overhaul_input"] = input_mode
    write_status(cdir, st)

def creative_clause(input_mode):
    src = ("Claude develops the creative direction itself."
           if input_mode != "brief" else
           "Read 02-intake/overhaul-brief.md as the STARTING POINT — take inspiration, not imitation; "
           "NEVER copy the reference's trade dress (logo, exact palette, signature layout, distinctive "
           "UI). Mode-B originality guardrail.")
    return ("DESIGN MODE = CREATIVE (the Overhaul — the maximal swing): reimagine FROM SCRATCH with full "
            "creative craft = BOTH (1) disciplined graphic richness (editorial art direction dialled up: "
            "oversized type as artwork, full-bleed colour interludes, layered composition) AND (2) smooth "
            "modern interactivity — section-based scroll narrative, scroll-reveal animations "
            "(IntersectionObserver + CSS, no heavy library), hover category tiles as the 'shop by' entry, "
            "slide-out drawers (cart/wishlist/filters/mobile-nav, transforms, no reloads), a condensing "
            "sticky header + smooth anchored nav, and ONE signature motion moment. Motion SERVES "
            f"navigation not decoration. {src} INVARIANTS HOLD UNCHANGED: the parity floor (every "
            "CARRY-OVER feature) stays; every studio + archetype Hard rule stays; prefers-reduced-motion "
            "honoured absolutely + keyboard/screen-reader paths unaffected; the swing is EXPRESSION-ONLY "
            "(layout / type / colour / motion / interactivity / graphics), never facts, features, or "
            "guardrails; photography stays resolution-limited (smoothness from motion + spacing + graphics, "
            "never upscaled photos). Pass the full Design QA Gate — including whether the navigation/motion "
            "layer lands — and name the brand moment. Full spec: ECOMMERCE-GUIDELINES §5.9.")

def overhaul_runbook(slug, input_mode):
    return (f"OVERHAUL (creative reimagining) for {slug}. Assemble — or re-assemble — the prototype per "
            f"Command 1, but in creative mode. {creative_clause(input_mode)} On any human-judgment fork, "
            f"open a decision (resume_job set) and STOP. PUBLISH-ALWAYS at the end; report what changed "
            f"and confirm the three invariants held.")

OVERHAUL_BRIEF_TEMPLATE = """# Overhaul brief — {slug}

A STARTING POINT for the creative overhaul. Claude takes INSPIRATION from this, never imitation —
your reference's trade dress (logo, exact palette, signature layout, distinctive UI) is never copied.

## Direction / references
<links, adjectives, a mood, sites you admire — what feeling should it evoke?>

## Must-keep
<anything specific to preserve. The parity floor + facts are already protected automatically.>

## Avoid
<what to steer away from>
"""

def full_build_runbook(slug, variant, design_mode="standard"):
    """The chain instruction handed to `claude -p`. Self-describing + resumable via the progress
    file. Authored to make every recommended decision automatically ONLY for from-scratch."""
    creative = (" " + creative_clause(read_status(CLIENTS / slug).get("overhaul_input", "claude"))
                if design_mode == "creative" else "")
    auto = ("This is FROM-SCRATCH: make every recommended decision automatically — if the "
            "'Choose the design concept' decision is still OPEN, resolve it to the RECOMMENDED "
            "option (Board B, the 'confident' board; record that the full build auto-accepted it) "
            "and do NOT wait. 'Push further' is a human lever; the full build never escalates on its own."
            if variant == "from-scratch" else
            "This is FROM-PROTOTYPE: PRESERVE the existing prototype EXACTLY — keep every processed "
            "edit, the chosen concept, and all design decisions. Run ONLY the steps that are missing. "
            "If a BINDING backend-config already exists, USE it untouched — never overwrite confirmed decisions.")
    return (
        f"FULL BUILD ({variant}) for {slug}. Drive the chain in "
        f"clients/{slug}/02-intake/full-build-progress.json. Read it first; for each step whose "
        f"status is not 'done', set it to 'active' (write the file), do the work, then set it to "
        f"'done' with a one-line note + UTC timestamp and write the file again — so the build is "
        f"resumable and the dashboard shows live progress. {auto} "
        f"Step 'precond': confirm clients/{slug}/02-intake/secrets/.env has rehearsal TEST creds "
        f"tagged '# REHEARSAL'; if missing, mark the step 'blocked', set blocked_on, OPEN a decision "
        f"in the inbox, and STOP. Build to ECOMMERCE-GUIDELINES.md + BACKEND.md + the BINDING "
        f"backend-config; honor the parity floor and every Hard rule; keep TEST MODE banners on every "
        f"surface; cutover stays refused while any # REHEARSAL credential is in use. On ANY fork that "
        f"needs the human's judgment, do NOT guess — open a decision (02-intake/decisions/NNN-OPEN-*.yaml) "
        f"with resume_job set so resolving it resumes this build, leave the step 'active', and STOP. "
        f"Each completed step still obeys PUBLISH-ALWAYS. When all steps are done, report what was built."
        + creative)

def full_build_action(slug, st):
    """Stage-gated full-build button (mutually exclusive variants). Returns
    {variant,label,enabled,tooltip,desc,resumable,steps} or None."""
    stage = st.get("stage", "")
    cdir = CLIENTS / slug
    if stage == "baseline-ready":
        variant = "from-scratch"
    elif stage in ("prototype", "awaiting-owner", "answers-received", "final"):
        variant = "from-prototype"
    else:
        return None   # queued/created/scraping/error/cutover-checked — no full build
    prog = read_full_build(cdir)
    resumable = bool(prog and prog.get("variant") == variant
                     and any(s["status"] != "done" for s in prog.get("steps", [])))
    done_all = bool(prog and prog.get("variant") == variant
                    and prog.get("steps") and all(s["status"] == "done" for s in prog["steps"]))
    if variant == "from-scratch":
        label = "Resume full build" if resumable else "Full build — from scratch"
        desc = ("Runs the COMPLETE chain automatically and makes every recommended decision for you: "
                "rehearsal mode → complete-coverage scrape + full catalog → assemble the recommended "
                "concept → auto-bind backend config → Phases 2–4 on TEST credentials → publish. "
                "Concept boards are generated and recorded, but the chain does not wait for your pick.")
    else:
        label = "Resume full build" if resumable else "Full build — from this prototype"
        desc = ("KEEPS the prototype exactly as built — all processed edits, the chosen concept, and "
                "design decisions stand. Runs only what's missing: rehearsal mode → backend config "
                "(auto-bind if none is BINDING; an existing BINDING config is used untouched) → "
                "Phases 2–4 on TEST credentials → publish.")
    enabled, tooltip = True, ""
    if slug in TASKS:
        enabled, tooltip = False, "a Claude task is already running for this client"
    elif done_all:
        enabled, tooltip = False, "full build already complete for this prototype"
    elif not test_creds_ready(cdir):
        enabled = False
        tooltip = ("needs rehearsal TEST credentials in 02-intake/secrets/.env "
                   "(Supabase/Stripe-test/Resend, each tagged # REHEARSAL) before a rehearsal build")
    return {"variant": variant, "label": label, "enabled": enabled, "tooltip": tooltip,
            "desc": desc, "resumable": resumable,
            "steps": prog.get("steps", []) if prog and prog.get("variant") == variant else []}

def read_concept_boards(cdir):
    """02-intake/concepts/boards.json -> list of board dicts for the visual decision + Documents."""
    f = cdir / "02-intake" / "concepts" / "boards.json"
    if not f.exists(): return None
    try: m = json.loads(f.read_text())
    except Exception: return None
    base = (m.get("deploy_url") or "").rstrip("/")
    for b in m.get("boards", []):
        b["url"] = f"{base}/{b.get('path','').lstrip('/')}" if base else ""
    return m

def push_further_runbook(slug, letter):
    """The 'Push further' chain: an experimental Board <letter> BEYOND the current bold board."""
    return (
        f"PUSH FURTHER — generate experimental concept Board {letter.upper()} for {slug}, going BEYOND "
        f"the current bold board (C). Permission granted to break conservative commerce conventions: "
        f"asymmetry, oversized type as the ENTIRE hero, an unconventional navigation metaphor, one "
        f"theatrical interactive moment. STILL obey the HARD rules: NO upscaled imagery (type-led where "
        f"photography is weak), reduced-motion honored, catalogue parity reachable, accessible contrast, "
        f"explicit language, ZERO banned generic patterns. Steps: (1) append a board to "
        f"clients/{slug}/02-intake/concepts/concepts.json with letter '{letter}', a fresh id, "
        f"tier 'experimental', recommended false, a DISTINCT type_attitude + structural_idea, palette, "
        f"fonts, nav, hero copy, band, and representative type-led products (never fabricate real client "
        f"facts); (2) run `python3 .claude/skills/site-baseline/scripts/concept_boards.py clients/{slug}`; "
        f"(3) deploy `wrangler pages deploy clients/{slug}/02-intake/concepts/site --project-name "
        f"ws-{slug} --commit-dirty=true` and write the deployed base into boards.json deploy_url; "
        f"(4) APPEND one option to the OPEN concept decision YAML in "
        f"clients/{slug}/02-intake/decisions/ — id=new board id, label "
        f"'{letter.upper()} — <name> (experimental)', one-line consequence, tag: experimental, "
        f"board_url, thumb=<letter>-<id>.png. Do NOT touch existing options or the recommendation "
        f"(wow is a human lever; the recommendation stays Board B). Report the new board URL.")

def has_binding_spec(cdir):
    specs = cdir / "02-intake" / "specs"
    if not specs.exists(): return False
    for f in specs.glob("*.md"):
        head = f.read_text()[:600]
        if re.search(r"^\s*status:\s*BINDING", head, re.M) and "spec-id:" in head:
            return True
    return False

def parse_backend_config(cdir):
    """Minimal parser for the controlled 02-intake/backend-config.yaml we generate. Returns
    {config_id, version, status, modules:[{key,tier,on,reason}]} or None."""
    f = cdir / "02-intake" / "backend-config.yaml"
    if not f.exists(): return None
    cfg = {"config_id": "", "version": "", "status": "", "mode": "", "modules": []}
    cur = None
    for ln in f.read_text().splitlines():
        s = ln.strip()
        m = re.match(r"^(config-id|version|status|mode|client|generated):\s*(.+)$", s)
        if m and not ln.startswith(" " * 2 + "-") and cur is None and not s.startswith("- "):
            k = m.group(1); v = m.group(2).strip().strip('"')
            if k == "config-id": cfg["config_id"] = v
            elif k in ("version", "status", "mode"): cfg[k] = v
            continue
        if s.startswith("- key:"):
            cur = {"key": s.split("key:", 1)[1].strip().strip('"'), "tier": "", "on": True, "reason": ""}
            cfg["modules"].append(cur)
        elif cur is not None and s.startswith("tier:"):
            cur["tier"] = s.split("tier:", 1)[1].strip().strip('"')
        elif cur is not None and s.startswith("on:"):
            cur["on"] = s.split("on:", 1)[1].strip().lower() in ("true", "yes", "on")
        elif cur is not None and s.startswith("reason:"):
            cur["reason"] = s.split("reason:", 1)[1].strip().strip('"')
    return cfg

def set_rehearsal(cdir, on):
    """Toggle `mode: rehearsal` in backend-config.yaml via a line edit (preserves modules/comments)."""
    f = cdir / "02-intake" / "backend-config.yaml"
    if not f.exists():
        return False
    lines = [l for l in f.read_text().splitlines() if not l.strip().startswith("mode:")]
    if on:
        out = []
        for l in lines:
            out.append(l)
            if l.strip().startswith("status:"):
                out.append("mode: rehearsal")
        lines = out
    f.write_text("\n".join(lines) + "\n")
    return True

def write_backend_config(cdir, cfg):
    L = [f'config-id: {cfg["config_id"]}', f'version: {cfg["version"]}',
         f'status: {cfg["status"]}', f'client: {cdir.name}', f'generated: {now()}', "modules:"]
    for m in cfg["modules"]:
        L += [f'  - key: {m["key"]}', f'    tier: {m["tier"]}',
              f'    on: {"true" if m["on"] else "false"}', f'    reason: "{m["reason"]}"']
    (cdir / "02-intake" / "backend-config.yaml").write_text("\n".join(L) + "\n")

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

# ---------------- decisions inbox (filename-is-state, mirrors edits) ----------------
def decisions_dir(scope):
    return (ROOT / ".claude" / "decisions") if scope == STUDIO_KEY else (CLIENTS / scope / "02-intake" / "decisions")

def parse_decision(path):
    d = {"question": "", "recommendation": "", "reason": "", "resume_job": "",
         "chosen": "", "chosen_at": "", "context": [], "options": []}
    section, cur = None, None
    for raw in path.read_text().splitlines():
        if not raw.strip():
            continue
        s = raw.strip(); indent = len(raw) - len(raw.lstrip())
        if indent == 0 and s in ("context:", "options:"):
            section = s[:-1]; cur = None; continue
        if indent == 0:
            m = re.match(r'^(question|recommendation|reason|resume_job|chosen|chosen_at):\s*(.*)$', s)
            if m:
                d[m.group(1)] = m.group(2).strip().strip('"'); section = None; cur = None; continue
        if section == "context" and s.startswith("- "):
            d["context"].append(s[2:].strip().strip('"')); continue
        if section == "options":
            if s.startswith("- "):
                cur = {"id": "", "label": "", "consequence": "", "next": "", "board_url": "", "thumb": "", "tag": ""}
                d["options"].append(cur); s = s[2:].strip()
            mm = re.match(r'^(id|label|consequence|next|board_url|thumb|tag):\s*(.*)$', s)
            if mm and cur is not None:
                cur[mm.group(1)] = mm.group(2).strip().strip('"')
    return d

def list_open_decisions():
    out = []
    scopes = [STUDIO_KEY] + ([d.name for d in CLIENTS.iterdir() if d.is_dir() and not d.name.startswith(".")] if CLIENTS.exists() else [])
    for scope in scopes:
        dd = decisions_dir(scope)
        if not dd.exists():
            continue
        for f in sorted(dd.glob("*-OPEN-*.yaml")):
            dec = parse_decision(f)
            dec.update({"scope": scope, "file": f.name})
            boards = [o for o in dec["options"] if o.get("thumb")]
            dec["is_boards"] = bool(boards)
            dec["board_count"] = len(boards)
            # "Push further" escalates Board D then E — cap at two escalations (a,b,c + d + e = 5)
            dec["can_escalate"] = dec["is_boards"] and len(boards) < 5 and scope != STUDIO_KEY
            dec["busy"] = scope in TASKS
            out.append(dec)
    return out

def open_decision_count(slug):
    dd = decisions_dir(slug)
    return len(list(dd.glob("*-OPEN-*.yaml"))) if dd.exists() else 0

def resolve_decision(scope, fname, choice):
    dd = decisions_dir(scope)
    src = dd / fname
    if not src.exists() or "-OPEN-" not in fname:
        return False, "decision not found / already resolved"
    dec = parse_decision(src)
    if choice not in [o["id"] for o in dec["options"]]:
        return False, "unknown option"
    text = src.read_text().rstrip() + f'\nchosen: {choice}\nchosen_at: "{now()}"\n'
    dest = dd / fname.replace("-OPEN-", "-RESOLVED-")
    dest.write_text(text)
    src.unlink()
    where = "studio" if scope == STUDIO_KEY else scope
    if scope != STUDIO_KEY:
        bump(CLIENTS / scope, msg=f"decision resolved [{fname}] -> {choice}")
    # resume a blocked job if the decision carried one
    if dec.get("resume_job") and scope != STUDIO_KEY:
        with TASK_LOCK:
            if scope not in TASKS:
                TASKS[scope] = {"kind": "resumed", "label": dec["resume_job"], "started": now(), "tail": [], "proc": None}
                threading.Thread(target=run_advance, args=(scope, dec["resume_job"], "resumed job", None), daemon=True).start()
    return True, dest.name

# ---------------- incidents (diagnose-then-fix; mirrors decisions/edits) ----------------
def incidents_dir(scope):
    return (ROOT / ".claude" / "incidents") if scope == STUDIO_KEY else (CLIENTS / scope / "02-intake" / "incidents")

def open_incident_count(slug):
    dd = incidents_dir(slug)
    return len(list(dd.glob("*-OPEN-*.md"))) if dd.exists() else 0

def _incident_symptom(path):
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except Exception:
        return ""
    for i, l in enumerate(lines):
        if l.strip().upper().startswith("## SYMPTOM"):
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    return lines[j].strip()[:140]
    return ""

def list_open_incidents():
    out = []
    scopes = [STUDIO_KEY] + ([d.name for d in CLIENTS.iterdir() if d.is_dir() and not d.name.startswith(".")] if CLIENTS.exists() else [])
    for scope in scopes:
        dd = incidents_dir(scope)
        if not dd.exists():
            continue
        for f in sorted(dd.glob("*-OPEN-*.md")):
            out.append({"scope": scope, "file": f.name, "symptom": _incident_symptom(f), "busy": scope in TASKS})
    return out

def create_incident(scope, symptom):
    symptom = (symptom or "").strip()
    if not symptom:
        return False, "empty symptom"
    dd = incidents_dir(scope); dd.mkdir(parents=True, exist_ok=True)
    n = len(list(dd.glob("*.md"))) + 1
    short = re.sub(r"[^a-z0-9]+", "-", symptom.lower()).strip("-")[:32] or "issue"
    sid = "STUDIO" if scope == STUDIO_KEY else scope.upper()
    tmpl = ROOT / "templates" / "incident-template.md"
    body = tmpl.read_text() if tmpl.exists() else "## SYMPTOM\n\n## DIAGNOSTIC\n\n## ROOT CAUSE\n\n## FIX PLAN\n\n## VERIFICATION\n\n## RESOLUTION\n"
    body = (body.replace("WS-INC-<SLUG-OR-STUDIO>-NNN", f"WS-INC-{sid}-{n:03d}")
                .replace("<slug | studio>", "studio" if scope == STUDIO_KEY else scope)
                .replace("<YYYY-MM-DD>", now()[:10])
                .replace("<The human's words VERBATIM> — where observed: <URL / screen / command>.",
                         f"{symptom} — where observed: (reported via dashboard)."))
    f = dd / f"{n:03d}-OPEN-{short}.md"
    f.write_text(body)
    # enqueue the headless diagnostic (client scope; mirrors the decisions resume pattern)
    if scope != STUDIO_KEY:
        bump(CLIENTS / scope, msg=f"incident OPENED: {f.name} — diagnostic enqueued")
        with TASK_LOCK:
            if scope not in TASKS:
                cmd = f"Diagnose incident {n:03d} for {scope}"
                TASKS[scope] = {"kind": "incident diagnostic", "label": cmd, "started": now(), "tail": [], "proc": None}
                threading.Thread(target=run_advance, args=(scope, cmd, "incident diagnostic", None), daemon=True).start()
    return True, f.name

# ---------------- reports (every finding becomes a visible artifact) ----------------
def reports_dir(scope):
    return (ROOT / ".claude" / "reports") if scope == STUDIO_KEY else (CLIENTS / scope / "02-intake" / "reports")

def _report_summary(path):
    try:
        for l in path.read_text(errors="ignore").splitlines():
            s = l.strip()
            if s and not s.startswith("---"):
                return s.lstrip("# ").strip()[:120]
    except Exception:
        pass
    return ""

def list_reports(scope):
    dd = reports_dir(scope)
    if not dd.exists():
        return []
    out = []
    for f in sorted(dd.glob("*.md"), reverse=True):  # newest first (timestamp-prefixed names sort)
        m = re.match(r'(\d{4}-\d{2}-\d{2}-\d{4})-(.+)\.md$', f.name)
        out.append({"file": f.name, "ts": (m.group(1) if m else ""),
                    "kind": (m.group(2).replace("-", " ") if m else f.stem), "summary": _report_summary(f)})
    return out

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
                    "full_build": full_build_action(d.name, st),
                    "concepts": (read_concept_boards(d) or {}).get("boards", []),
                    "can_configure": st.get("stage") == "prototype" and has_binding_spec(d),
                    "backend_cfg": (lambda c: {"status": c["status"], "version": c["version"], "mode": c.get("mode", "")} if c else None)(parse_backend_config(d)),
                    "busy": d.name in TASKS,
                    "decisions_open": open_decision_count(d.name),
                    "incidents_open": open_incident_count(d.name),
                    "reports": list_reports(d.name),
                    "design_mode": read_status(d).get("design_mode", "standard"),
                    "documents": [n for n in ("redesign-plan.md", "deliverables-request.md",
                                              "production-roadmap.md", "backend-config.yaml")
                                  if (d / "02-intake" / n).exists()],
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
.rehbadge{font-family:var(--m);font-size:.56rem;letter-spacing:.12em;background:#7a4dff;color:#fff;padding:.15em .5em;border-radius:2px}
.needbadge{font-family:var(--m);font-size:.58rem;letter-spacing:.1em;background:#c0392b;color:#fff;padding:.18em .55em;border-radius:2px}
.incbadge{font-family:var(--m);font-size:.58rem;letter-spacing:.1em;background:#b8740a;color:#fff;padding:.18em .55em;border-radius:2px}
.ndot{color:#c0392b;font-size:.7rem;vertical-align:middle}
.needstrip{border:1px solid #c0392b;background:#1a0f0f;margin:0 0 1.4rem;padding:1rem 1.1rem}
.needstrip.incstrip{border-color:#b8740a;background:#181206}
.incstrip .needhead{color:#e6a44a}
.report{display:flex;gap:.5rem;margin:.5rem 0 .2rem}
.report input{flex:1;background:var(--ink,#181818);color:var(--paper,#eee);border:1px solid var(--line,#444);padding:.35em .6em;font-family:var(--b);font-size:.78rem}
.report input:focus{outline:none;border-color:#b8740a}
.shreport{display:flex;gap:.5rem;margin:.6rem 0 0;max-width:46rem}
.shreport input{flex:1;background:#181818;color:#eee;border:1px solid #444;padding:.35em .6em;font-family:var(--b);font-size:.78rem}
.needhead{font-family:var(--d);text-transform:uppercase;color:#ff6b5e;letter-spacing:.04em;margin-bottom:.7rem}
.deccard{border-top:1px solid #3a2222;padding:.8rem 0}
.decq{font-size:.95rem}.decscope{font-family:var(--m);font-size:.6rem;color:var(--muted);border:1px solid var(--line);padding:.05em .4em;margin-left:.4rem}
.decctx{font-family:var(--m);font-size:.68rem;color:var(--muted);margin:.4rem 0;padding-left:1.1rem}
.decopts{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.5rem}
.decopt{background:transparent;color:var(--paper);border:1px solid var(--line);font-family:var(--b);font-weight:400;font-size:.8rem;text-transform:none}
.decopt:hover{border-color:var(--amber);color:var(--amber)}
.decrec{background:var(--amber);color:var(--ink);border:1px solid var(--amber);font-family:var(--b);font-weight:600;font-size:.8rem;text-transform:none}
.decreason{font-family:var(--m);font-size:.64rem;color:var(--muted);margin-top:.4rem}
.docs{margin-top:.6rem;font-family:var(--m);font-size:.7rem;display:flex;gap:.4rem;align-items:center;flex-wrap:wrap}
.docbtn{background:transparent;color:var(--amber);border:1px solid var(--line);font-family:var(--m);font-size:.66rem;text-transform:none;padding:.15em .5em}
.docbtn:hover{border-color:var(--amber)}
.docbox{max-width:48rem;max-height:86vh;display:flex;flex-direction:column}
.docbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:.8rem}
.docmd{overflow:auto;font-size:.85rem;line-height:1.5}
.docmd h1,.docmd h2,.docmd h3{font-family:var(--d);color:var(--amber);text-transform:uppercase;margin:1rem 0 .4rem}
.docmd h1{font-size:1.3rem}.docmd h2{font-size:1.1rem}.docmd h3{font-size:.95rem}
.docmd code{font-family:var(--m);background:var(--ink);padding:.05em .3em}
.docmd table{border-collapse:collapse;width:100%;font-size:.72rem;margin:.5rem 0}
.docmd td,.docmd th{border:1px solid var(--line);padding:.3rem .4rem;text-align:left}
.docmd ul{padding-left:1.2rem}.docmd hr{border:0;border-top:1px solid var(--line);margin:.8rem 0}
.docmd a{color:var(--amber)}
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
.cfgbox{max-width:42rem;max-height:84vh;overflow:auto}
.tiergrp{margin:.8rem 0}.tiergrp h4{font-family:var(--m);font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;color:var(--amber);margin:.4rem 0}
.citem{display:flex;gap:.5rem;align-items:flex-start;font-size:.78rem;padding:.3rem 0;border-bottom:1px solid var(--line)}
.citem .lk{color:#7fd18f}.citem .rsn{color:var(--muted);font-family:var(--m);font-size:.66rem}
.cfgdef summary{cursor:pointer;color:var(--muted);font-family:var(--m);font-size:.72rem}
button.adv.fb{border-color:#7a4dff;color:#b79cff}
button.adv.fb:hover:not([disabled]){background:#7a4dff;color:#fff}
button.adv.fb[disabled]{color:var(--muted);border-color:var(--line);opacity:.6}
.fbsteps{margin-top:.6rem;border:1px solid #3a2f5e;background:#140e22;padding:.6rem .8rem;font-family:var(--m);font-size:.66rem}
.fbhead{color:#b79cff;letter-spacing:.08em;text-transform:uppercase;margin-bottom:.45rem}
.fbstep{padding:.12rem 0;color:var(--muted)}
.fbstep.done{color:#7fd18f}.fbstep.active{color:#ffd479}.fbstep.blocked{color:#ff8a8a}
.fbstep .fbg{display:inline-block;width:1.1em}.fbn{color:var(--muted);font-style:italic}
.decboards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.9rem;margin-top:.6rem}
.bcard{border:1px solid var(--line);background:var(--panel2);padding:.5rem}
.bcard.rec{border-color:var(--amber)}
.bthumblink{display:block;position:relative}
.bthumb{width:100%;height:auto;display:block;border:1px solid var(--line);background:#000;min-height:6rem}
.brec{position:absolute;top:.4rem;left:.4rem;background:var(--amber);color:var(--ink);font-family:var(--m);font-size:.56rem;letter-spacing:.08em;text-transform:uppercase;padding:.15em .5em}
.bname{font-family:var(--d);text-transform:uppercase;font-size:1rem;margin:.5rem 0 .2rem}
.bone{font-family:var(--m);font-size:.64rem;color:var(--muted);line-height:1.4}
.brow{display:flex;justify-content:space-between;align-items:center;margin-top:.5rem;gap:.5rem}
.blink{color:var(--amber);font-family:var(--m);font-size:.66rem;text-decoration:none}
.bchoose{background:var(--amber);color:var(--ink);border:1px solid var(--amber);font-family:var(--b);font-weight:600;font-size:.74rem;text-transform:none;padding:.3em .8em}
.bchoose:hover{background:transparent;color:var(--amber)}
.bcard.exp{border-color:#ff7a3d}
.bexp{position:absolute;top:.4rem;left:.4rem;background:#ff7a3d;color:#1a0d06;font-family:var(--m);font-size:.56rem;letter-spacing:.06em;text-transform:uppercase;padding:.15em .5em;font-weight:600}
.pushrow{margin-top:.8rem;display:flex;gap:.7rem;align-items:center;flex-wrap:wrap}
.pushbtn{background:#ff7a3d;color:#1a0d06;border:1px solid #ff7a3d;font-family:var(--d);font-weight:700;text-transform:uppercase;letter-spacing:.04em;font-size:.82rem;padding:.4em 1em}
.pushbtn:hover:not([disabled]){background:transparent;color:#ff7a3d}
.pushbtn[disabled]{opacity:.5;cursor:not-allowed}
.ovbtn{background:#7a4dff;color:#fff;border:1px solid #7a4dff;font-family:var(--d);font-weight:700;text-transform:uppercase;letter-spacing:.04em;font-size:.82rem;padding:.4em 1em;margin-left:.5em}
.ovbtn:hover:not([disabled]){background:transparent;color:#9b78ff}
.ovbtn[disabled]{opacity:.5;cursor:not-allowed}
.cvbadge{font-family:var(--m);font-size:.56rem;letter-spacing:.12em;background:#7a4dff;color:#fff;padding:.15em .5em;border-radius:2px}
.pushnote{font-family:var(--m);font-size:.64rem;color:var(--muted)}
</style></head><body><div class="wrap">
<h1>Web Studio</h1><p class="sub">Two human steps · everything else automated</p>
<form class="shreport" onsubmit="return reportProblem(event,'__studio__')" title="Studio-level problem (dashboard, pipeline, a script)">
  <input type="text" placeholder="Report a studio problem — dashboard/pipeline/script (becomes a .claude/incidents/ incident)" required>
  <button class="ghost">Report ⚑</button>
</form>
<div id="studioreports" class="docs"></div>
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
<div id="needs"></div>
<div id="list"><p class="empty">Loading…</p></div>
</div>
<div id="modal" class="modal" style="display:none"><div class="modalbox">
  <h3 id="m-title"></h3>
  <p id="m-desc" class="m-desc"></p>
  <p id="m-cmd" class="m-cmd"></p>
  <div id="m-unmet" class="m-unmet"></div>
  <label class="m-lab">Type the client slug to confirm: <b id="m-slug"></b></label>
  <input id="m-input" placeholder="slug" autocomplete="off">
  <label id="m-creative" class="m-lab" style="display:none"><input type="checkbox" id="m-creative-cb"> 🎨 Creative overhaul — the maximal swing (graphic-heavy reimagining; parity + facts + Hard rules preserved)</label>
  <div class="m-btns"><button id="m-run">Run</button><button class="ghost" onclick="closeModal()">Cancel</button></div>
</div></div>
<div id="docmodal" class="modal" style="display:none"><div class="modalbox docbox">
  <div class="docbar"><b id="doc-title"></b><button class="ghost" onclick="document.getElementById('docmodal').style.display='none'">Close</button></div>
  <div id="doc-body" class="docmd"></div>
</div></div>
<div id="ovmodal" class="modal" style="display:none"><div class="modalbox">
  <h3>🎨 Overhaul — the creative maximal swing</h3>
  <p class="m-desc">Full creative-mode craft + a from-scratch reimagining (graphic-heavy, disciplined
    richness). The parity floor, every client fact, and every Hard rule are preserved — the swing is
    EXPRESSION-ONLY. This is the SAME capability as choosing Creative at build start. Pick how to start:</p>
  <div class="m-btns" style="flex-direction:column;gap:.6rem;align-items:stretch">
    <button onclick="doOverhaul('claude')">Claude develops it</button>
    <button onclick="doOverhaul('brief')">I provide a starting point (overhaul-brief.md)</button>
    <button class="ghost" onclick="document.getElementById('ovmodal').style.display='none'">Cancel</button>
  </div>
</div></div>
<div id="rehexit" class="modal" style="display:none"><div class="modalbox">
  <h3>Exit rehearsal — the swap checklist</h3>
  <p class="m-desc">Leaving rehearsal means moving off studio test resources onto the client's real
    accounts. Check each off as you complete it — this is the un-rehearsal ritual. Schema, code, and
    content do NOT change.</p>
  <div id="rehlist"></div>
  <label class="m-lab">Then type the client slug to confirm: <b id="reh-slug"></b></label>
  <input id="reh-input" placeholder="slug" autocomplete="off">
  <div class="m-btns"><button id="reh-run" disabled>Exit rehearsal</button><button class="ghost" onclick="document.getElementById('rehexit').style.display='none'">Cancel</button></div>
</div></div>
<div id="cfgmodal" class="modal" style="display:none"><div class="modalbox cfgbox">
  <h3 id="cfg-title"></h3>
  <p class="m-desc">REQUIRED + EVIDENCED are locked on (never less than your evidence). Toggle only the JUDGMENT items; DEFERRED are opt-in.</p>
  <div id="cfg-body"></div>
  <label class="m-lab">Type the client slug to make this config BINDING: <b id="cfg-slug"></b></label>
  <input id="cfg-input" placeholder="slug" autocomplete="off">
  <div class="m-btns"><button id="cfg-run">Confirm → BINDING</button><button class="ghost" onclick="document.getElementById('cfgmodal').style.display='none'">Cancel</button></div>
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
async function configBackend(slug){
  const c=findC(slug);
  if(!c.backend_cfg){ const r=await api('/api/backend-config/propose',{slug});
    if(r.error) alert(r.error); else { alert('Proposing backend config — watch the row log; the panel opens once the draft lands.'); load(); } return; }
  openCfg(slug);
}
async function openCfg(slug){
  const r=await api('/api/backend-config?slug='+encodeURIComponent(slug));
  if(!r.config){ alert('No config yet — still proposing?'); return; }
  const cfg=r.config, groups={REQUIRED:[],EVIDENCED:[],JUDGMENT:[],DEFERRED:[]};
  cfg.modules.forEach(m=>(groups[m.tier]||(groups.JUDGMENT)).push(m));
  const locked=(m)=>`<div class="citem"><span class="lk">🔒 on</span><div><b>${esc(m.key)}</b> <span class="rsn">${esc(m.reason)}</span></div></div>`;
  const toggle=(m)=>`<div class="citem"><input type="checkbox" data-ck="${esc(m.key)}" ${m.on?'checked':''}><div><b>${esc(m.key)}</b> <span class="rsn">${esc(m.reason)}</span></div></div>`;
  let html='';
  if(groups.REQUIRED.length) html+=`<div class="tiergrp"><h4>Required — locked on</h4>${groups.REQUIRED.map(locked).join('')}</div>`;
  if(groups.EVIDENCED.length) html+=`<div class="tiergrp"><h4>Evidenced — locked on</h4>${groups.EVIDENCED.map(locked).join('')}</div>`;
  if(groups.JUDGMENT.length) html+=`<div class="tiergrp"><h4>Judgment — your call</h4>${groups.JUDGMENT.map(toggle).join('')}</div>`;
  if(groups.DEFERRED.length) html+=`<div class="tiergrp"><details class="cfgdef"><summary>Deferred — opt in (${groups.DEFERRED.length})</summary>${groups.DEFERRED.map(toggle).join('')}</details></div>`;
  document.getElementById('cfg-title').textContent='Backend config — '+slug+' ('+cfg.status+' v'+cfg.version+')';
  document.getElementById('cfg-body').innerHTML=html;
  document.getElementById('cfg-slug').textContent=slug;
  const inp=document.getElementById('cfg-input'); inp.value='';
  document.getElementById('cfg-run').onclick=async()=>{
    const overrides={}; document.querySelectorAll('#cfg-body input[data-ck]').forEach(x=>overrides[x.dataset.ck]=x.checked);
    const rr=await api('/api/backend-config/confirm',{slug,confirm:inp.value.trim(),overrides});
    if(rr.error) alert('Cannot confirm: '+rr.error); else { document.getElementById('cfgmodal').style.display='none'; load(); }
  };
  document.getElementById('cfgmodal').style.display='flex'; inp.focus();
}
async function sendChat(e,key){ e.preventDefault();
  const t=document.getElementById('cin-'+key); const msg=t.value.trim(); if(!msg) return false;
  const r=await api('/api/chat',{slug:key,message:msg});
  if(r.error){ alert('Chat: '+r.error); return false; }
  t.value=''; chatDraft[key]=''; renderChat(key); return false; }
function cpCmd(slug){ const c=findC(slug); if(c&&c.advance) cp('claude -p "'+c.advance.command+'"'); }
function closeModal(){ document.getElementById('modal').style.display='none'; }
function enterReh(slug){
  document.getElementById('m-title').textContent='Enter rehearsal mode';
  document.getElementById('m-desc').textContent="Phases 2–4 build against studio TEST resources (test Supabase/Stripe/Resend) and every surface shows a TEST MODE banner. Cutover stays blocked until you swap to the client's real accounts.";
  document.getElementById('m-cmd').textContent=''; document.getElementById('m-unmet').textContent='';
  document.getElementById('m-creative').style.display='none';
  document.getElementById('m-slug').textContent=slug;
  const inp=document.getElementById('m-input'); inp.value='';
  document.getElementById('m-run').onclick=async()=>{ const r=await api('/api/rehearsal',{slug,action:'enter',confirm:inp.value.trim()}); if(r.error) alert(r.error); else { closeModal(); load(); } };
  document.getElementById('modal').style.display='flex'; inp.focus();
}
const SWAP=["SUPABASE_URL + service key → client's own project","STRIPE_SECRET_KEY → client's LIVE key","RESEND_API_KEY → client's account","Resend FROM domain → client's verified domain (reply-to their inbox)","Stripe webhook endpoint → production URL + new signing secret","Remove every #REHEARSAL tag from secrets/.env"];
function exitReh(slug){
  const list=document.getElementById('rehlist');
  list.innerHTML=SWAP.map(s=>`<label class="citem"><input type="checkbox" class="swap"> ${esc(s)}</label>`).join('');
  document.getElementById('reh-slug').textContent=slug;
  const inp=document.getElementById('reh-input'); inp.value='';
  const run=document.getElementById('reh-run');
  const refresh=()=>{ const all=[...list.querySelectorAll('.swap')].every(x=>x.checked); run.disabled=!(all && inp.value.trim()===slug); };
  list.querySelectorAll('.swap').forEach(x=>x.addEventListener('change',refresh));
  inp.oninput=refresh; refresh();
  run.onclick=async()=>{ const r=await api('/api/rehearsal',{slug,action:'exit',confirm:inp.value.trim()}); if(r.error) alert(r.error); else { document.getElementById('rehexit').style.display='none'; load(); } };
  document.getElementById('rehexit').style.display='flex';
}
function openAdvance(slug){
  const c=findC(slug); if(!c||!c.advance||!c.advance.enabled) return;
  document.getElementById('m-title').textContent=c.advance.label;
  document.getElementById('m-desc').textContent=c.advance.desc||'';
  document.getElementById('m-cmd').textContent='claude -p "'+c.advance.command+'"';
  document.getElementById('m-unmet').textContent=c.advance.tooltip||'';
  document.getElementById('m-creative').style.display='none';
  document.getElementById('m-slug').textContent=slug;
  const inp=document.getElementById('m-input'); inp.value='';
  document.getElementById('m-run').onclick=async()=>{
    const r=await api('/api/advance',{slug,confirm:inp.value.trim()});
    if(r.error){ alert('Cannot run: '+r.error); } else { closeModal(); load(); }
  };
  document.getElementById('modal').style.display='flex'; inp.focus();
}
function openFullBuild(slug){
  const c=findC(slug); if(!c||!c.full_build||!c.full_build.enabled) return;
  document.getElementById('m-title').textContent=(c.full_build.resumable?'Resume full build':c.full_build.label)+' — '+slug;
  document.getElementById('m-desc').textContent=c.full_build.desc||'';
  document.getElementById('m-cmd').textContent = c.full_build.variant==='from-scratch'
    ? 'FROM SCRATCH — auto-runs the whole chain and makes every RECOMMENDED decision for you (concept + backend config). Boards are still generated and recorded. TEST-mode rehearsal build; cutover stays blocked until you swap to the client\\'s real accounts.'
    : 'FROM THIS PROTOTYPE — KEEPS everything already built (processed edits, chosen concept, design). An existing BINDING backend-config is used untouched. Runs only what is missing. TEST-mode rehearsal build; cutover stays blocked until you swap to real accounts.';
  document.getElementById('m-unmet').textContent = c.full_build.resumable ? 'Resumes from the last completed step (see the row).' : '';
  document.getElementById('m-slug').textContent=slug;
  const inp=document.getElementById('m-input'); inp.value='';
  const mc=document.getElementById('m-creative'), cb=document.getElementById('m-creative-cb');
  mc.style.display='block'; cb.checked = (c.design_mode==='creative');
  document.getElementById('m-run').onclick=async()=>{
    const r=await api('/api/full-build',{slug,confirm:inp.value.trim(),design_mode:cb.checked?'creative':'standard'});
    if(r.error){ alert('Cannot start: '+r.error); } else { closeModal(); load(); }
  };
  document.getElementById('modal').style.display='flex'; inp.focus();
}
async function load(){
  saveDrafts();
  const d = await api('/api/clients'); DATA = d;
  document.getElementById('stats').textContent =
    `active scrapes ${d.running}/${d.max} · queued ${d.queued} · archived projects ${d.archived}`;
  renderNeeds(d.decisions||[], d.incidents||[]);
  const sr=document.getElementById('studioreports');
  if(sr) sr.innerHTML=(d.studio_reports&&d.studio_reports.length)?`<span class="mono-label">studio reports${newDot('__studio__',d.studio_reports)}</span> `+d.studio_reports.slice(0,8).map(r=>`<button class="docbtn" onclick="openReport('__studio__','${r.file}','${d.studio_reports[0].file}')" title="${esc(r.summary)}">${esc(r.kind)} · ${r.ts}</button>`).join(' '):'';
  const el = document.getElementById('list');
  if(!d.clients.length){ el.innerHTML='<p class="empty">No active clients — start one above.</p>'; return; }
  el.innerHTML = d.clients.map(c=>`<div class="row${c.done?' fin':''}">
    <div class="top"><div><span class="nm">${c.name}</span> <span class="dom">${c.domain}</span></div>
    <div class="btns"><span class="chip">${c.stage}</span>
      ${c.decisions_open?`<span class="needbadge">${c.decisions_open} decision${c.decisions_open>1?'s':''}</span>`:''}
      ${c.incidents_open?`<span class="incbadge">${c.incidents_open} incident${c.incidents_open>1?'s':''}</span>`:''}
      ${c.design_mode==='creative'?'<span class="cvbadge">CREATIVE</span>':''}
      ${c.busy?'<span class="run">● running…</span>':''}
      ${c.advance?`<button class="adv" ${c.advance.enabled?'':'disabled'} title="${(c.advance.tooltip||c.advance.desc||'').replace(/"/g,'&quot;')}" onclick="openAdvance('${c.slug}')">${c.advance.label}</button>${c.advance.badge?`<span class="rehbadge">${c.advance.badge}</span>`:''}<span class="copy" title="Copy terminal command" onclick="cpCmd('${c.slug}')">⧉</span>`:''}
      ${c.full_build?`<button class="adv fb" ${c.full_build.enabled?'':'disabled'} title="${(c.full_build.tooltip||c.full_build.desc||'').replace(/"/g,'&quot;')}" onclick="openFullBuild('${c.slug}')">${c.full_build.resumable?'⟳ ':'⚡ '}${c.full_build.label}</button>`:''}
      ${c.can_configure?`<button class="ghost" onclick="configBackend('${c.slug}')">Configure backend${c.backend_cfg?` · ${c.backend_cfg.status} v${c.backend_cfg.version}`:''}</button>`:''}
      ${c.backend_cfg?(c.backend_cfg.mode==='rehearsal'?`<span class="rehbadge">REHEARSAL</span><button class="ghost" onclick="exitReh('${c.slug}')">Exit rehearsal</button>`:`<button class="ghost" onclick="enterReh('${c.slug}')">Enter rehearsal mode</button>`):''}
      ${d.server?(d.ttyd_url?`<a class="ghost" href="${d.ttyd_url}" target="_blank" rel="noopener">Open session ↗</a>`:''):`<button class="ghost" onclick="api('/open',{slug:'${c.slug}'})">Claude: ${c.name}</button>`}
      ${c.rerun?`<button class="ghost" onclick="act('/rerun','${c.slug}')">Rerun</button>`:''}
      <button class="${c.done?'done':'ghost'}" onclick="if(confirm('Archive ${c.slug}? Moves it to archive/ and clears this row.'))act('/archive','${c.slug}')">Archive</button>
    </div></div>
    <div class="next">${c.next}</div>
    ${c.busy&&c.task_tail.length?`<div class="tasktail">${c.task_tail.map(t=>t.replace(/[<>]/g,'')).join('\\n')}</div>`:''}
    ${c.full_build&&c.full_build.steps&&c.full_build.steps.length?`<div class="fbsteps"><div class="fbhead">⚡ Full build · ${c.full_build.variant} · ${c.full_build.resumable?'in progress (resumable)':'complete'}</div>${c.full_build.steps.map(s=>`<div class="fbstep ${s.status}"><span class="fbg">${s.status==='done'?'✓':s.status==='active'?'●':s.status==='blocked'?'⚠':'○'}</span> <span class="fbt">${esc(s.title)}</span>${s.note?` <span class="fbn">— ${esc(s.note)}</span>`:''}</div>`).join('')}</div>`:''}
    ${c.advance_failed&&!c.busy?`<div class="prev"><span class="stale">⚠ advance failed — see log</span></div>`:''}
    ${c.production_url?`<div class="prev"><a class="live" href="${c.production_url}" target="_blank" rel="noopener">Live ↗</a> <span class="copy" title="Copy URL" onclick="cp('${c.production_url}')">⧉</span> <span class="purl">${c.production_url}</span></div>`:''}
    ${c.preview_url?`<div class="prev"><a class="pvw" href="${c.preview_url}" target="_blank" rel="noopener">Preview ↗</a> <span class="copy" title="Copy URL" onclick="cp('${c.preview_url}')">⧉</span> <span class="pdate">${c.preview_rel||c.preview_at}</span>${c.preview_stale?' <span class="stale">⚠ last deploy failed</span>':(c.preview_behind?' <span class="stale">⚠ preview behind latest edits</span>':'')}</div>`:''}
    ${c.documents&&c.documents.length?`<div class="docs"><span class="mono-label">documents</span> ${c.documents.map(n=>`<button class="docbtn" onclick="openDoc('${c.slug}','${n}')">${n}</button>`).join(' ')}</div>`:''}
    ${c.concepts&&c.concepts.length?`<div class="docs"><span class="mono-label">concept boards</span> ${c.concepts.map(b=>`<a class="docbtn" href="${b.url||'#'}" target="_blank" rel="noopener" title="${esc(b.one_liner)}">${b.recommended?'★ ':''}${esc(b.name)} ↗</a><a class="docbtn" href="/api/concept-thumb?slug=${c.slug}&name=${esc(b.thumb_desktop)}" target="_blank" rel="noopener" title="desktop screenshot">🖼 png</a>`).join(' ')}</div>`:''}
    ${c.reports&&c.reports.length?`<div class="docs"><span class="mono-label">reports${newDot(c.slug,c.reports)}</span> ${c.reports.slice(0,8).map(r=>`<button class="docbtn" onclick="openReport('${c.slug}','${r.file}','${c.reports[0].file}')" title="${esc(r.summary)}">${esc(r.kind)} · ${r.ts}</button>`).join(' ')}</div>`:''}
    <form class="report" onsubmit="return reportProblem(event,'${c.slug}')">
      <input type="text" placeholder="Report a problem — what's broken? (becomes an incident, then a diagnostic)" required>
      <button class="ghost">Report ⚑</button>
    </form>
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
function renderNeeds(decs, incs){
  incs = incs||[];
  const box=document.getElementById('needs');
  if(!decs.length && !incs.length){ box.innerHTML=''; return; }
  const incsHTML = !incs.length ? '' : `<div class="needstrip incstrip"><div class="needhead">⚑ Reported problems · ${incs.length}</div>`+incs.map(it=>`<div class="deccard"><div class="decq">${esc(it.symptom||it.file)} <span class="decscope">${it.scope==='__studio__'?'studio':esc(it.scope)}</span></div><div class="decreason">incident ${esc(it.file)} — ${it.busy?'diagnosing…':'open · diagnostic queued'}</div></div>`).join('')+`</div>`;
  const decsHTML = !decs.length ? '' : `<div class="needstrip"><div class="needhead">⬤ Needs your call · ${decs.length}</div>`+
    decs.map(dn=>{
      const isBoards = dn.options.some(o=>o.thumb);   // visual concept-board decision
      const pushRow = isBoards ? `<div class="pushrow">${
          dn.can_escalate
            ? `<button class="pushbtn" ${dn.busy?'disabled':''} onclick="pushFurther('${dn.scope}')" title="Generate an experimental Board ${'ABCDE'[dn.board_count]||'D'} beyond the bold board — generative, no confirm">🔥 Push further</button><span class="pushnote">not landing? generate an experimental board (${dn.board_count}/5)</span>`
            : `<span class="pushnote">Two escalations reached (Board E exists) — the fix is a conversation now, not another board.</span>`
        }<button class="ovbtn" ${dn.busy?'disabled':''} onclick="openOverhaul('${dn.scope}')" title="The maximal swing: full creative-mode craft + a from-scratch reimagining. Same as choosing Creative at build start.">🎨 Overhaul (creative)</button>${dn.busy?'<span class="run">● generating…</span>':''}</div>` : '';
      const opts = isBoards
        ? `<div class="decboards">${dn.options.map(o=>`
            <div class="bcard ${o.id===dn.recommendation?'rec':''} ${o.tag==='experimental'?'exp':''}">
              <a class="bthumblink" href="${o.board_url||'#'}" target="_blank" rel="noopener" title="Open the live board ↗">
                <img class="bthumb" loading="lazy" src="/api/concept-thumb?slug=${encodeURIComponent(dn.scope)}&name=${encodeURIComponent(o.thumb)}" alt="${esc(o.label||o.id)} board">
                ${o.id===dn.recommendation?'<span class="brec">★ recommended</span>':o.tag==='experimental'?'<span class="bexp">🔥 experimental</span>':''}</a>
              <div class="bname">${esc(o.label||o.id)}</div>
              <div class="bone">${esc(o.consequence)}</div>
              <div class="brow"><a class="blink" href="${o.board_url||'#'}" target="_blank" rel="noopener">Open board ↗</a>
                <button class="bchoose" onclick="resolveDec('${dn.scope}','${dn.file}','${o.id}')">Choose this</button></div>
            </div>`).join('')}</div>${pushRow}`
        : `<div class="decopts">${dn.options.map(o=>`<button class="${o.id===dn.recommendation?'decrec':'decopt'}" onclick="resolveDec('${dn.scope}','${dn.file}','${o.id}')" title="${esc(o.consequence)}">${o.id===dn.recommendation?'★ ':''}${esc(o.label||o.id)}</button>`).join('')}</div>`;
      return `<div class="deccard">
      <div class="decq">${esc(dn.question)} <span class="decscope">${dn.scope==='__studio__'?'studio':esc(dn.scope)}</span></div>
      ${dn.context.length?`<ul class="decctx">${dn.context.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:''}
      ${opts}
      ${dn.reason?`<div class="decreason">recommendation: ${esc(dn.reason)}</div>`:''}
    </div>`;}).join('')+`</div>`;
  box.innerHTML = decsHTML + incsHTML;
}
async function resolveDec(scope,file,choice){
  const r=await api('/api/decisions/resolve',{scope,file,choice});
  if(r.error) alert('Could not resolve: '+r.error); else load();
}
async function reportProblem(e, scope){
  e.preventDefault();
  const inp=e.target.querySelector('input'); const symptom=(inp.value||'').trim();
  if(!symptom) return false;
  const r=await api('/api/incident',{scope,symptom});
  if(r.error){ alert('Could not file: '+r.error); }
  else { inp.value=''; alert('Incident '+r.incident+' filed — diagnostic running. It will diagnose before any fix.'); load(); }
  return false;
}
function newDot(slug, reports){ try{ return (reports.length && localStorage.getItem('rseen_'+slug)!==reports[0].file) ? ' <span class="ndot" title="new reports since you last looked">●</span>' : ''; }catch(e){ return ''; } }
function openReport(slug, file, newest){ try{ localStorage.setItem('rseen_'+slug, newest); }catch(e){} openDoc(slug, 'reports/'+file); }
async function pushFurther(scope){
  const r=await api('/api/push-further',{slug:scope});
  if(r.error){ alert('Push further: '+r.error); }
  else { alert('Generating an experimental board — watch the row log; the new option joins this card when it lands.'); load(); }
}
let OV_SCOPE='';
function openOverhaul(scope){ OV_SCOPE=scope; document.getElementById('ovmodal').style.display='flex'; }
async function doOverhaul(input_mode){
  document.getElementById('ovmodal').style.display='none';
  const r=await api('/api/overhaul',{slug:OV_SCOPE,input_mode});
  if(r.error){ alert('Overhaul: '+r.error); return; }
  if(r.await_brief){ alert('Created 02-intake/overhaul-brief.md — fill it with your direction, then click Overhaul → "I provide a starting point" again to build.'); }
  else { alert('Creative overhaul started ('+input_mode+') — watch the row log. Parity floor + facts + Hard rules are preserved; the swing is expression-only.'); }
  load();
}
function md2html(src){
  const ec=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const inl=s=>ec(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
  const L=src.split('\\n'); let h=''; let i=0;
  while(i<L.length){ let l=L[i];
    let m=l.match(/^\s*(#{1,3})\s+(.*)/); if(m){ h+=`<h${m[1].length}>${inl(m[2])}</h${m[1].length}>`; i++; continue; }
    if(/^\s*---\s*$/.test(l)){ h+='<hr>'; i++; continue; }
    if(/^\s*\|.*\|\s*$/.test(l)){ const rows=[]; while(i<L.length&&/^\s*\|.*\|\s*$/.test(L[i])){ rows.push(L[i]); i++; }
      const cells=r=>r.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
      let t='<table>'; rows.forEach((r,ri)=>{ if(ri===1&&/^[\s:|-]+$/.test(r)) return; const tg=ri===0?'th':'td'; t+='<tr>'+cells(r).map(c=>`<${tg}>${inl(c)}</${tg}>`).join('')+'</tr>'; }); h+=t+'</table>'; continue; }
    if(/^\s*[-*]\s+/.test(l)){ let t='<ul>'; while(i<L.length&&/^\s*[-*]\s+/.test(L[i])){ t+='<li>'+inl(L[i].replace(/^\s*[-*]\s+/,''))+'</li>'; i++; } h+=t+'</ul>'; continue; }
    if(l.trim()===''){ i++; continue; }
    let p=l; i++; while(i<L.length&&L[i].trim()!==''&&!/^\s*(#{1,3}\s|[-*]\s|\||---)/.test(L[i])){ p+=' '+L[i]; i++; } h+='<p>'+inl(p)+'</p>';
  } return h;
}
async function openDoc(slug,name){
  const txt=await (await fetch('/api/doc?slug='+encodeURIComponent(slug)+'&name='+encodeURIComponent(name))).text();
  document.getElementById('doc-title').textContent=slug+' / '+name;
  document.getElementById('doc-body').innerHTML= name.endsWith('.yaml')
    ? '<pre style="white-space:pre-wrap;font-family:var(--m);font-size:.72rem">'+txt.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</pre>'
    : md2html(txt);
  document.getElementById('docmodal').style.display='flex';
}
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
                                   "ttyd_url": TTYD_URL, "decisions": list_open_decisions(),
                                   "incidents": list_open_incidents(),
                                   "studio_reports": list_reports(STUDIO_KEY)}), "application/json")
        elif path == "/api/chat":
            q = parse_qs(urlparse(self.path).query)
            slug = q.get("slug", [""])[0]
            key = STUDIO_KEY if slug in ("", "studio") else slugify(slug)
            self._send(json.dumps({"messages": read_chat(key), "running": key in TASKS}),
                       "application/json")
        elif path == "/api/backend-config":
            slug = slugify(parse_qs(urlparse(self.path).query).get("slug", [""])[0])
            self._send(json.dumps({"config": parse_backend_config(CLIENTS / slug),
                                   "running": slug in TASKS}), "application/json")
        elif path == "/api/decisions":
            self._send(json.dumps({"decisions": list_open_decisions()}), "application/json")
        elif path == "/api/doc":
            q = parse_qs(urlparse(self.path).query)
            rawslug = q.get("slug", [""])[0]; name = q.get("name", [""])[0]
            allowed = {"redesign-plan.md", "deliverables-request.md", "production-roadmap.md", "backend-config.yaml"}
            is_report = name.startswith("reports/") and name.endswith(".md") and ".." not in name
            if rawslug in ("__studio__", "studio"):   # studio-level reports
                f = ROOT / ".claude" / "reports" / Path(name).name
                if not (is_report and f.exists()):
                    return self._send("not found", code=404)
                return self._send(f.read_text(), "text/plain")
            slug = slugify(rawslug)
            f = CLIENTS / slug / "02-intake" / name
            if not ((name in allowed or is_report) and f.exists()):
                return self._send("not found", code=404)
            self._send(f.read_text(), "text/plain")
        elif path == "/api/concept-thumb":
            q = parse_qs(urlparse(self.path).query)
            slug = slugify(q.get("slug", [""])[0]); name = Path(q.get("name", [""])[0]).name
            f = CLIENTS / slug / "02-intake" / "concepts" / name
            if not name.endswith(".png") or not f.exists():
                return self._send("not found", code=404)
            b = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
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
        elif path == "/api/full-build":
            slug = slugify(d.get("slug", ""))
            cdir = CLIENTS / slug
            if not cdir.exists():
                return self._send(json.dumps({"error": "no such client"}), "application/json", 404)
            fb = full_build_action(slug, read_status(cdir))   # revalidate server-side (stage-gated)
            if not fb or not fb.get("enabled"):
                return self._send(json.dumps({"error": fb.get("tooltip") if fb else "no full build available at this stage"}), "application/json", 400)
            if d.get("confirm", "") != slug:
                return self._send(json.dumps({"error": "type the slug exactly to confirm"}), "application/json", 400)
            if not test_creds_ready(cdir):   # precondition gate (defense in depth)
                return self._send(json.dumps({"error": "rehearsal TEST credentials missing in 02-intake/secrets/.env"}), "application/json", 400)
            variant = fb["variant"]
            dmode = "creative" if d.get("design_mode") == "creative" else "standard"
            set_design_mode(cdir, dmode)      # build-start entry point for creative/overhaul
            if not fb.get("resumable"):       # fresh run: lay down the step artifact; resume keeps it
                init_full_build(cdir, variant)
            with TASK_LOCK:
                if slug in TASKS:
                    return self._send(json.dumps({"error": "a Claude task is already running for this client"}), "application/json", 409)
                TASKS[slug] = {"kind": "full build", "label": f"full build ({variant})", "started": now(), "tail": [], "proc": None}
            bump(cdir, msg=f"FULL BUILD {'resumed' if fb.get('resumable') else 'started'} ({variant})")
            threading.Thread(target=run_advance,
                             args=(slug, full_build_runbook(slug, variant, dmode), "full build", "full_build_failed"),
                             daemon=True).start()
            return self._send(json.dumps({"ok": True, "variant": variant, "design_mode": dmode}), "application/json")
        elif path == "/api/overhaul":
            # Boards entry point for creative/overhaul (the SAME design_mode:creative as build-start).
            slug = slugify(d.get("slug", "")); cdir = CLIENTS / slug
            if not cdir.exists():
                return self._send(json.dumps({"error": "no such client"}), "application/json", 404)
            input_mode = "brief" if d.get("input_mode") == "brief" else "claude"
            set_design_mode(cdir, "creative", input_mode)
            brief = cdir / "02-intake" / "overhaul-brief.md"
            if input_mode == "brief" and not brief.exists():
                brief.write_text(OVERHAUL_BRIEF_TEMPLATE.format(slug=slug))
                bump(cdir, msg="OVERHAUL armed (creative, brief mode) — awaiting 02-intake/overhaul-brief.md")
                return self._send(json.dumps({"ok": True, "await_brief": True, "created": True,
                                              "msg": "Fill 02-intake/overhaul-brief.md, then run Overhaul again to build."}), "application/json")
            with TASK_LOCK:
                if slug in TASKS:
                    return self._send(json.dumps({"error": "a Claude task is already running for this client"}), "application/json", 409)
                TASKS[slug] = {"kind": "overhaul", "label": f"creative overhaul ({input_mode})", "started": now(), "tail": [], "proc": None}
            bump(cdir, msg=f"OVERHAUL started (creative, {input_mode})")
            threading.Thread(target=run_advance,
                             args=(slug, overhaul_runbook(slug, input_mode), "overhaul", "overhaul_failed"),
                             daemon=True).start()
            return self._send(json.dumps({"ok": True, "design_mode": "creative", "input_mode": input_mode}), "application/json")
        elif path == "/api/push-further":
            # The "🔥 Push further" wow lever — generative (no slug confirm). Produces Board D, then E.
            slug = slugify(d.get("slug", ""))
            cdir = CLIENTS / slug
            if not cdir.exists():
                return self._send(json.dumps({"error": "no such client"}), "application/json", 404)
            dd = decisions_dir(slug)
            open_board_dec = any(o.get("thumb") for f in (dd.glob("*-OPEN-*.yaml") if dd.exists() else [])
                                 for o in parse_decision(f)["options"])
            if not open_board_dec:
                return self._send(json.dumps({"error": "no open concept-board decision to escalate"}), "application/json", 400)
            m = read_concept_boards(cdir) or {}
            count = len(m.get("boards", []))
            if count >= 5:   # a,b,c + d + e — two escalations is the cap
                return self._send(json.dumps({"error": "two escalations reached (Board E exists) — the fix is a conversation now, not another board; open a decision note instead"}), "application/json", 400)
            letter = "abcde"[count]   # 3 -> d, 4 -> e
            with TASK_LOCK:
                if slug in TASKS:
                    return self._send(json.dumps({"error": "a Claude task is already running for this client"}), "application/json", 409)
                TASKS[slug] = {"kind": "push further", "label": f"Board {letter.upper()} (experimental)", "started": now(), "tail": [], "proc": None}
            bump(cdir, msg=f"PUSH FURTHER — generating experimental Board {letter.upper()}")
            threading.Thread(target=run_advance,
                             args=(slug, push_further_runbook(slug, letter), "push further", "push_further_failed"),
                             daemon=True).start()
            return self._send(json.dumps({"ok": True, "letter": letter}), "application/json")
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
        elif path == "/api/backend-config/propose":
            slug = slugify(d.get("slug", ""))
            cdir = CLIENTS / slug
            if not cdir.exists():
                return self._send(json.dumps({"error": "no such client"}), "application/json", 404)
            if not has_binding_spec(cdir):
                return self._send(json.dumps({"error": "needs a BINDING spec first"}), "application/json", 400)
            if parse_backend_config(cdir):
                return self._send(json.dumps({"ok": True, "note": "config already exists"}), "application/json")
            with TASK_LOCK:
                if slug in TASKS:
                    return self._send(json.dumps({"error": "a Claude task is already running for this client"}), "application/json", 409)
                TASKS[slug] = {"kind": "backend proposal", "label": "propose backend config", "started": now(), "tail": [], "proc": None}
            threading.Thread(target=run_advance,
                             args=(slug, f"Propose backend config for {slug}", "backend proposal", None),
                             daemon=True).start()
            return self._send(json.dumps({"ok": True}), "application/json")
        elif path == "/api/backend-config/confirm":
            slug = slugify(d.get("slug", ""))
            cdir = CLIENTS / slug
            cfg = parse_backend_config(cdir)
            if not cfg:
                return self._send(json.dumps({"error": "no draft config to confirm"}), "application/json", 404)
            if d.get("confirm", "") != slug:
                return self._send(json.dumps({"error": "type the slug exactly to confirm"}), "application/json", 400)
            overrides = d.get("overrides", {}) or {}   # {key: bool} for JUDGMENT/DEFERRED only
            for m in cfg["modules"]:
                if m["tier"] in ("REQUIRED", "EVIDENCED"):
                    m["on"] = True                       # safety/evidence never toggled off
                elif m["key"] in overrides:
                    m["on"] = bool(overrides[m["key"]])
            try: cfg["version"] = str(int(cfg.get("version") or "0") + 1)
            except ValueError: cfg["version"] = "1"
            cfg["status"] = "BINDING"
            write_backend_config(cdir, cfg)
            on = sum(1 for m in cfg["modules"] if m["on"])
            bump(cdir, msg=f"backend-config CONFIRMED -> BINDING v{cfg['version']} ({on}/{len(cfg['modules'])} modules ON)")
            return self._send(json.dumps({"ok": True, "version": cfg["version"]}), "application/json")
        elif path == "/api/decisions/resolve":
            scope = d.get("scope", ""); scope = STUDIO_KEY if scope in ("", "studio", STUDIO_KEY) else slugify(scope)
            ok, msg = resolve_decision(scope, d.get("file", ""), d.get("choice", ""))
            return self._send(json.dumps({"ok": ok, "error": None if ok else msg, "resolved": msg if ok else None}), "application/json", 200 if ok else 400)
        elif path == "/api/incident":
            scope = d.get("scope", ""); scope = STUDIO_KEY if scope in ("", "studio", STUDIO_KEY) else slugify(scope)
            ok, msg = create_incident(scope, d.get("symptom", ""))
            return self._send(json.dumps({"ok": ok, "error": None if ok else msg, "incident": msg if ok else None}), "application/json", 200 if ok else 400)
        elif path == "/api/rehearsal":
            slug = slugify(d.get("slug", "")); cdir = CLIENTS / slug
            action = d.get("action", "")
            if d.get("confirm", "") != slug:
                return self._send(json.dumps({"error": "type the slug exactly to confirm"}), "application/json", 400)
            if not parse_backend_config(cdir):
                return self._send(json.dumps({"error": "configure the backend first"}), "application/json", 400)
            if action == "enter":
                set_rehearsal(cdir, True)
                bump(cdir, msg="ENTERED rehearsal mode (studio test resources; TEST banners; cutover blocked)")
            elif action == "exit":
                set_rehearsal(cdir, False)
                bump(cdir, msg="EXITED rehearsal mode (swap checklist completed — now on real accounts)")
            else:
                return self._send(json.dumps({"error": "action must be enter or exit"}), "application/json", 400)
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
