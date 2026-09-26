#!/usr/bin/env bash
set -euo pipefail

# Pull latest main and restart Pricewatch when the remote branch moved.
# Installed by deploy/install.sh as a systemd timer (pricewatch-update.timer).

INSTALL_DIR="${INSTALL_DIR:-/opt/pricewatch}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-pricewatch}"

log() { printf '[pricewatch-update] %s\n' "$*"; }

git_repo() {
  git -c "safe.directory=$INSTALL_DIR" -C "$INSTALL_DIR" "$@"
}

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  log "Run as root (systemd invokes this as root)"
  exit 1
fi

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  log "No git checkout at $INSTALL_DIR — run deploy/install.sh first"
  exit 1
fi

git_repo fetch origin "$BRANCH"
local_rev="$(git_repo rev-parse HEAD)"
remote_rev="$(git_repo rev-parse "origin/$BRANCH")"

if [[ "$local_rev" == "$remote_rev" ]]; then
  log "Already up to date ($(git_repo rev-parse --short HEAD))"
  exit 0
fi

log "Updating $(git_repo rev-parse --short "$local_rev") -> $(git_repo rev-parse --short "$remote_rev")"
git_repo checkout "$BRANCH"
git_repo reset --hard "origin/$BRANCH"

if [[ ! -x "$INSTALL_DIR/.venv/bin/pip" ]]; then
  log "Missing venv — running full install"
  exec "$INSTALL_DIR/deploy/install.sh"
fi

"$INSTALL_DIR/.venv/bin/pip" install -q -e "$INSTALL_DIR"

run_user="$(systemctl show "$SERVICE_NAME" -p User --value 2>/dev/null || true)"
if [[ -n "$run_user" && "$run_user" != "root" ]]; then
  chown -R "$run_user:$run_user" "$INSTALL_DIR"
fi

systemctl restart "$SERVICE_NAME"
log "Deployed and restarted $SERVICE_NAME"
