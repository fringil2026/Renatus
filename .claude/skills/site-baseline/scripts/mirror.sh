#!/usr/bin/env bash
# Method 3 — wget mirror: a raw archive + independent URL census.
# Hard-capped at MAX_FILES files OR MAX_SECONDS seconds, whichever first, logging which cap hit.
# Always BOUNDED — an unbounded mirror once orphaned a wget. The caps are env-overridable for the
# rehearsal COMPLETENESS pass (deliberate + logged), e.g.:
#   MIRROR_MAX_FILES=5000 MIRROR_MAX_SECONDS=2700 ./mirror.sh https://example.com <client_dir>
# Usage: ./mirror.sh https://example.com <client_dir>
set -u
DOMAIN="$1"; CLIENT="$2"
OUT="$CLIENT/00-source/mirror"
MAX_FILES="${MIRROR_MAX_FILES:-300}"      # default 300; rehearsal raises (still bounded)
MAX_SECONDS="${MIRROR_MAX_SECONDS:-300}"  # default 5 min; rehearsal raises (still bounded)
echo "mirror: caps = ${MAX_FILES} files / ${MAX_SECONDS}s"
mkdir -p "$OUT"
if ! command -v wget >/dev/null 2>&1; then
  echo "wget not installed — skipped (method 3)" | tee "$OUT/SKIPPED.txt"; exit 0
fi

wget --mirror --no-parent --adjust-extension --convert-links --quiet \
     --wait=0.5 --level=4 --tries=2 --timeout=15 \
     --user-agent="StudioBaseline/1.0" -P "$OUT" "$DOMAIN" &
WPID=$!

cap=""
start=$SECONDS
while kill -0 "$WPID" 2>/dev/null; do
  files=$(find "$OUT" -name '*.html' | wc -l | tr -d ' ')
  elapsed=$(( SECONDS - start ))
  if [ "$files" -ge "$MAX_FILES" ]; then cap="file cap (${MAX_FILES} files)"; break; fi
  if [ "$elapsed" -ge "$MAX_SECONDS" ]; then cap="time cap (${MAX_SECONDS}s)"; break; fi
  sleep 2
done

if [ -n "$cap" ]; then
  kill "$WPID" 2>/dev/null
  pkill -P "$WPID" 2>/dev/null   # any wget children
  wait "$WPID" 2>/dev/null
  echo "mirror: stopped early — $cap hit" | tee "$OUT/CAP-HIT.txt"
else
  wait "$WPID" 2>/dev/null
fi
echo "mirror: $(find "$OUT" -name '*.html' | wc -l | tr -d ' ') html files -> $OUT${cap:+  (capped: $cap)}"
