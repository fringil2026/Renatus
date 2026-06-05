#!/usr/bin/env bash
# Method 3 — wget mirror: a raw archive + independent URL census.
# Usage: ./mirror.sh https://example.com <client_dir>
set -u
DOMAIN="$1"; CLIENT="$2"
OUT="$CLIENT/00-source/mirror"
mkdir -p "$OUT"
if ! command -v wget >/dev/null 2>&1; then
  echo "wget not installed — skipped (method 3)" | tee "$OUT/SKIPPED.txt"; exit 0
fi
wget --mirror --no-parent --adjust-extension --convert-links --quiet \
     --wait=0.5 --level=4 --tries=2 --timeout=15 \
     --user-agent="StudioBaseline/1.0" -P "$OUT" "$DOMAIN" || true
echo "mirror: $(find "$OUT" -name '*.html' | wc -l | tr -d ' ') html files -> $OUT"
