#!/usr/bin/env bash
# =============================================================================
# Web Studio nightly backup of clients/ and archive/ to object storage.
#
# WHY restic (not a plain nightly tar): restic gives encrypted, deduplicated,
# incremental snapshots with built-in retention/prune and a one-command restore.
# For a folder of mostly-unchanging client projects + large mirror archives, a
# full tar every night would balloon storage; restic only stores the deltas.
# (If you truly want a portable tar instead, see the TAR ALTERNATIVE at the bottom.)
#
# Backend is parameterized for Backblaze B2 or S3 via /etc/web-studio/backup.env.
# Install: sudo apt install restic   (or: restic self-update)
# =============================================================================
set -euo pipefail

ENV_FILE="${BACKUP_ENV:-/etc/web-studio/backup.env}"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

STUDIO_DIR="${STUDIO_DIR:-/home/studio/web-studio}"
LOG="${BACKUP_LOG:-/var/log/web-studio-backup.log}"

ts() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }
say() { echo "$(ts) $*" | tee -a "$LOG"; }

# Required env (set in $ENV_FILE):
#   RESTIC_REPOSITORY        e.g.  b2:my-bucket:web-studio   OR  s3:s3.us-west-002.backblazeb2.com/my-bucket
#   RESTIC_PASSWORD_FILE     path to a file holding the repo encryption passphrase (chmod 600)
#   For B2 native:  B2_ACCOUNT_ID, B2_ACCOUNT_KEY
#   For S3 (incl. B2's S3 API / AWS): AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY in $ENV_FILE}"
: "${RESTIC_PASSWORD_FILE:?set RESTIC_PASSWORD_FILE in $ENV_FILE}"

# First-ever run: initialize the repo if it doesn't exist yet (idempotent).
restic snapshots >/dev/null 2>&1 || { say "initializing restic repo"; restic init; }

say "backup start: clients/ + archive/"
restic backup \
  --tag web-studio --tag nightly \
  --exclude='**/node_modules' --exclude='**/dist' --exclude='**/.astro' \
  "${STUDIO_DIR}/clients" "${STUDIO_DIR}/archive" 2>&1 | tee -a "$LOG"

say "retention prune"
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune 2>&1 | tee -a "$LOG"

say "integrity quick-check"
restic check --read-data-subset=5% 2>&1 | tee -a "$LOG" || say "WARN: restic check reported issues"

say "backup done"

# ---------------------------------------------------------------------------
# CRON: install with `sudo crontab -u studio -e` and add this line (02:30 nightly):
#   30 2 * * *  /home/studio/web-studio/deploy/backup.sh >> /var/log/web-studio-backup.log 2>&1
#
# RESTORE (documented):
#   restic snapshots                      # list snapshots, copy the ID you want
#   restic restore <SNAPSHOT_ID> --target /home/studio/restore   # restores clients/ + archive/
#   # then move the restored folders back into the repo, or point a fresh checkout at them.
#   restic restore latest --target /tmp/r --include /home/studio/web-studio/clients/andy-s-orchids
#                                         # restore a single client
#
# TAR ALTERNATIVE (if you insist on a plain portable archive instead of restic):
#   tar --exclude='*/node_modules' --exclude='*/dist' -czf \
#     "/tmp/web-studio-$(date -u +%F).tgz" -C "$STUDIO_DIR" clients archive
#   rclone copy "/tmp/web-studio-$(date -u +%F).tgz" b2:my-bucket/web-studio/    # needs rclone configured
# ---------------------------------------------------------------------------
