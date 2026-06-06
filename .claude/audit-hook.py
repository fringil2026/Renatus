#!/usr/bin/env python3
"""PostToolUse audit hook. Appends one line per tool call to .claude/audit/session.log:
ISO-8601 timestamp, tool name, and a one-line summary of the command or file touched.
Never raises — a logging hook must not break the tool call it observes."""
import json, sys, datetime, pathlib

def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    tool = d.get("tool_name", "?")
    ti = d.get("tool_input", {}) or {}
    summary = (
        ti.get("command")
        or ti.get("file_path")
        or ti.get("path")
        or ti.get("pattern")
        or ti.get("url")
        or ti.get("description")
        or ""
    )
    if not isinstance(summary, str):
        summary = str(summary)
    summary = " ".join(summary.split())[:200]
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    log = pathlib.Path(__file__).resolve().parent / "audit" / "session.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(f"{ts}\t{tool}\t{summary}\n")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
