#!/usr/bin/env bash
# Temporary PUBLIC access to the studio dashboard.
# Uses a Cloudflare "quick tunnel" (no account needed) -> https://<random>.trycloudflare.com
# The URL and tunnel die when you Ctrl+C — temporary by design.
set -u
export STUDIO_HOST=0.0.0.0
export STUDIO_PORT="${STUDIO_PORT:-8788}"
if [ -z "${STUDIO_TOKEN:-}" ]; then
  export STUDIO_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(9))')"
fi
echo "============================================================"
echo " Access token: $STUDIO_TOKEN"
echo " Open the public URL as:  <url>/?key=$STUDIO_TOKEN"
echo " Treat the token like a password — it gates scrape triggers."
echo "============================================================"
python3 studio.py &
SP=$!
trap 'kill $SP 2>/dev/null' EXIT
sleep 1
if command -v cloudflared >/dev/null 2>&1; then
  cloudflared tunnel --url "http://localhost:${STUDIO_PORT}"
else
  echo "cloudflared not installed."
  echo "  macOS:  brew install cloudflared"
  echo "  Linux:  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  echo "No-install alternative:  ssh -R 80:localhost:${STUDIO_PORT} nokey@localhost.run"
  wait $SP
fi
