#!/usr/bin/env bash
# =============================================================================
# Web Studio — server bootstrap for Ubuntu 22.04/24.04 LTS. IDEMPOTENT: safe to
# re-run; every step checks before acting. Run as root (or via sudo) ON THE VPS:
#     sudo REPO_URL=git@github.com:you/web-studio.git bash setup.sh
# Then finish the one-time interactive logins (claude, wrangler) as the studio
# user — see deploy/MIGRATION.md.
# =============================================================================
set -euo pipefail

STUDIO_USER="${STUDIO_USER:-studio}"
STUDIO_HOME="/home/${STUDIO_USER}"
STUDIO_DIR="${STUDIO_DIR:-${STUDIO_HOME}/web-studio}"
REPO_URL="${REPO_URL:-}"                 # set to your repo (ssh or https)
NODE_MAJOR="${NODE_MAJOR:-22}"           # Node LTS
ADMIN_SSH_KEY="${ADMIN_SSH_KEY:-}"       # optional: a public key to install for the studio user

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }

log "System update"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

log "Base packages"
apt-get install -y --no-install-recommends \
  git curl ca-certificates gnupg ufw python3 python3-pip python3-venv build-essential

log "Node ${NODE_MAJOR} LTS (NodeSource)"
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | grep -oE '[0-9]+' | head -1)" -lt "${NODE_MAJOR}" ]; then
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
  apt-get install -y nodejs
fi

log "ttyd (web terminal)"
if ! command -v ttyd >/dev/null 2>&1; then
  apt-get install -y ttyd || {
    # fallback to the static release if the apt package is unavailable
    curl -fsSL https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64 -o /usr/local/bin/ttyd
    chmod +x /usr/local/bin/ttyd
  }
fi

log "Create non-root user '${STUDIO_USER}'"
if ! id "${STUDIO_USER}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${STUDIO_USER}"
fi
if [ -n "${ADMIN_SSH_KEY}" ]; then
  install -d -m 700 -o "${STUDIO_USER}" -g "${STUDIO_USER}" "${STUDIO_HOME}/.ssh"
  echo "${ADMIN_SSH_KEY}" > "${STUDIO_HOME}/.ssh/authorized_keys"
  chmod 600 "${STUDIO_HOME}/.ssh/authorized_keys"
  chown "${STUDIO_USER}:${STUDIO_USER}" "${STUDIO_HOME}/.ssh/authorized_keys"
fi

log "Clone / update the studio repo"
if [ -n "${REPO_URL}" ]; then
  if [ -d "${STUDIO_DIR}/.git" ]; then
    sudo -u "${STUDIO_USER}" git -C "${STUDIO_DIR}" pull --ff-only || true
  else
    sudo -u "${STUDIO_USER}" git clone "${REPO_URL}" "${STUDIO_DIR}"
  fi
else
  echo "REPO_URL not set — skipping clone (copy the repo to ${STUDIO_DIR} manually)."
fi

log "Python deps (for the baseline skill scripts)"
sudo -u "${STUDIO_USER}" python3 -m pip install --user --upgrade requests beautifulsoup4

log "Global npm tools: wrangler + Claude Code CLI"
npm install -g wrangler @anthropic-ai/claude-code

log "Node deps for any client sites already in the repo"
if [ -d "${STUDIO_DIR}/clients" ]; then
  find "${STUDIO_DIR}/clients" -maxdepth 3 -name package.json -not -path '*/node_modules/*' -print0 \
    | while IFS= read -r -d '' pkg; do
        d="$(dirname "$pkg")"; log "npm install in ${d}"
        sudo -u "${STUDIO_USER}" npm install --prefix "$d" || true
      done
fi

log "Hardening: SSH keys only"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh || systemctl reload sshd || true

log "Firewall: only SSH inbound; all outbound allowed; dashboard port NEVER exposed"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
# NOTE: studio.py binds 127.0.0.1 only; the public path is the Cloudflare tunnel +
# Access (deploy/tunnel-setup.md). We deliberately do NOT 'ufw allow 8788'.
ufw --force enable

log "Install the systemd service"
if [ -f "${STUDIO_DIR}/deploy/studio.service" ]; then
  install -m 644 "${STUDIO_DIR}/deploy/studio.service" /etc/systemd/system/studio.service
  install -d -m 750 -o "${STUDIO_USER}" -g "${STUDIO_USER}" /etc/web-studio 2>/dev/null || true
  if [ ! -f /etc/web-studio/studio.env ]; then
    TOKEN="$(head -c 9 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 12)"
    cat > /etc/web-studio/studio.env <<EOF
STUDIO_HOST=127.0.0.1
STUDIO_PORT=8788
STUDIO_TOKEN=${TOKEN}
STUDIO_ENV=server
STUDIO_TTYD_URL=https://studio.example.com/term/
MAX_SCRAPES=3
EOF
    chmod 640 /etc/web-studio/studio.env
    echo "Generated /etc/web-studio/studio.env with STUDIO_TOKEN=${TOKEN} — edit STUDIO_TTYD_URL to your hostname."
  fi
  systemctl daemon-reload
  systemctl enable studio.service
  echo "Run 'systemctl start studio' after the one-time claude/wrangler logins."
fi

log "Done. Next: deploy/tunnel-setup.md (named tunnel + Access), then the one-time"
log "logins as ${STUDIO_USER}: 'claude' and 'wrangler login', then 'systemctl start studio'."
