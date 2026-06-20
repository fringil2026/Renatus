"""Run the whole engine+api test suite with one command, no test framework required.

    python3 tests/run_all.py

Discovers every ``tests/test_*.py``, runs each as a standalone script (each file has a self-contained
runner), and prints a per-suite + overall summary. Exit code is non-zero if any suite fails. The
opt-in live Agent-SDK probe (``tests/smoke_agent_sdk.py``) is intentionally excluded.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def main() -> int:
    suites = sorted(p for p in _HERE.glob("test_*.py"))
    if not suites:
        print("no test_*.py suites found")
        return 1

    total_pass = total = failed_suites = 0
    print(f"Running {len(suites)} suites\n" + "-" * 48)
    for suite in suites:
        res = subprocess.run(
            [sys.executable, str(suite)], capture_output=True, text=True, cwd=str(_HERE.parent)
        )
        summary = ""
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.endswith("passed") or "FAILED" in line:
                summary = line
        ok = res.returncode == 0
        # parse "X/Y passed"
        if "/" in summary and "passed" in summary:
            x, y = summary.split(" ", 1)[0].split("/")
            total_pass += int(x)
            total += int(y)
        if not ok:
            failed_suites += 1
        mark = "ok " if ok else "FAIL"
        print(f"  [{mark}] {suite.name:30} {summary}")
        if not ok and res.stderr.strip():
            print("        " + res.stderr.strip().splitlines()[-1])

    print("-" * 48)
    verdict = "ALL PASS" if failed_suites == 0 else f"{failed_suites} SUITE(S) FAILED"
    print(f"{total_pass}/{total} tests across {len(suites)} suites — {verdict}")
    return 1 if failed_suites else 0


if __name__ == "__main__":
    raise SystemExit(main())
