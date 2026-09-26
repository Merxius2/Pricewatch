#!/usr/bin/env bash
set -euo pipefail

# Pull latest main and restart Pricewatch when the remote branch moved.
# Installed by deploy/install.sh as a systemd timer (pricewatch-update.timer).

INSTALL_DIR="${INSTALL_DIR:-/opt/pricewatch}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-pricewatch}"

log() { printf '[pricewatch-update] %s\n' "$*"; }

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  log "Run as root (systemd invokes this as root)"
  exit 1
fi

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  log "No git checkout at $INSTALL_DIR — run deploy/install.sh first"
  exit 1
fi

git -C "$INSTALL_DIR" fetch origin "$BRANCH"
local_rev="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
remote_rev="$(git -C "$INSTALL_DIR" rev-parse "origin/$BRANCH")"

if [[ "$local_rev" == "$remote_rev" ]]; then
  log "Already up to date ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"
  exit 0
fi

log "Updating $(git -C "$INSTALL_DIR" rev-parse --short "$local_rev") -> $(git -C "$INSTALL_DIR" rev-parse --short "$remote_rev")"
git -C "$INSTALL_DIR" checkout "$BRANCH"
git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"

if [[ ! -x "$INSTALL_DIR/.venv/bin/pip" ]]; then
  log "Missing venv — running full install"
  exec "$INSTALL_DIR/deploy/install.sh"
fi

"$INSTALL_DIR/.venv/bin/pip" install -q -e "$INSTALL_DIR"
systemctl restart "$SERVICE_NAME"
log "Deployed and restarted $SERVICE_NAME"
