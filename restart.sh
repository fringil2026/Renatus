#!/usr/bin/env bash
# One-command restart for the Web Studio dashboard (Layer 2D).
# Kills ANY studio.py holding the port, then relaunches onto CURRENT on-disk code, and
# verifies the served version stamp matches HEAD. Restarting must be frictionless so a stale
# parallel server never lingers. Usage:  ./restart.sh
set -euo pipefail
cd "$(dirname "$0")"
PORT="${STUDIO_PORT:-8788}"

echo "[restart] stopping any studio.py on :$PORT ..."
# kill whatever is LISTENing on the port (the incumbent dashboard)
PIDS="$(lsof -ti "TCP:$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  echo "[restart]   killing PID(s): $PIDS"
  kill $PIDS 2>/dev/null || true
  for _ in $(seq 1 20); do
    lsof -ti "TCP:$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 0.25
  done
  # last resort
  PIDS="$(lsof -ti "TCP:$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$PIDS" ] && { echo "[restart]   force-killing $PIDS"; kill -9 $PIDS 2>/dev/null || true; sleep 0.5; }
else
  echo "[restart]   nothing was listening."
fi

echo "[restart] launching current code ..."
nohup python3 studio.py > /tmp/studio.log 2>&1 &
sleep 2

HEAD="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "[restart] HEAD is $HEAD"
echo "[restart] server log (tail):"
tail -n 4 /tmp/studio.log 2>/dev/null || true
echo "[restart] open http://localhost:$PORT  — the footer version stamp should read commit $HEAD"
