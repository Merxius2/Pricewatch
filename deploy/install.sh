#!/usr/bin/env bash
set -euo pipefail

# Install Pricewatch on a Linux mini-PC (same host as Ollama + Good-search).
#
# Usage (on the mini-PC):
#   curl -fsSL https://raw.githubusercontent.com/Merxius2/Pricewatch/main/deploy/install.sh | bash
#
# Or with the Good-search MCP URL:
#   PRICEWATCH_GOOD_SEARCH_MCP_URL='https://host.ts.net/mcp/secret' bash deploy/install.sh
#
# Options:
#   INSTALL_DIR=/opt/pricewatch
#   REPO_URL=https://github.com/Merxius2/Pricewatch.git
#   BRANCH=main
#   RUN_USER=$USER          # run as current user instead of creating 'pricewatch'
#   SKIP_SYSTEMD=1          # only install files, do not enable systemd service
#   SKIP_AUTO_UPDATE=1      # do not enable the git pull + deploy timer

INSTALL_DIR="${INSTALL_DIR:-/opt/pricewatch}"
REPO_URL="${REPO_URL:-https://github.com/Merxius2/Pricewatch.git}"
BRANCH="${BRANCH:-main}"
RUN_USER="${RUN_USER:-pricewatch}"
SERVICE_NAME="pricewatch"

log() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "Run as root: sudo bash deploy/install.sh"
  fi
}

detect_good_search_mcp_url() {
  if [[ -n "${PRICEWATCH_GOOD_SEARCH_MCP_URL:-}" ]]; then
    echo "$PRICEWATCH_GOOD_SEARCH_MCP_URL"
    return
  fi

  local candidates=(
    "$HOME/Good-search-git/mcp/.funnel-url"
    "$HOME/Good-search-git/mcp/funnel.url"
    "$HOME/.config/good-search/mcp.url"
    "/etc/good-search/mcp.url"
  )

  for file in "${candidates[@]}"; do
    if [[ -f "$file" ]]; then
      tr -d '[:space:]' < "$file"
      return
    fi
  done

  # Claude / MCP config may contain the funnel URL
  local config_files=(
    "$HOME/.config/claude/claude_desktop_config.json"
    "$HOME/.cursor/mcp.json"
  )
  for file in "${config_files[@]}"; do
    if [[ -f "$file" ]] && command -v python3 >/dev/null; then
      local url
      url="$(python3 - "$file" <<'PY' 2>/dev/null || true
import json, re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
matches = re.findall(r"https://[^\s\"']+/mcp/[a-f0-9]+", text)
if not matches:
    try:
        matches = re.findall(r"https://[^\s\"']+/mcp/[a-f0-9]+", json.dumps(json.loads(text)))
    except json.JSONDecodeError:
        pass
if matches:
    print(matches[0])
PY
)"
      if [[ -n "$url" ]]; then
        echo "$url"
        return
      fi
    fi
  done
}

write_env_file() {
  local env_file="$1"
  local mcp_url="$2"

  if [[ -f "$env_file" ]]; then
    log "Keeping existing $env_file"
    if [[ -n "$mcp_url" ]] && ! grep -q '^PRICEWATCH_GOOD_SEARCH_MCP_URL=' "$env_file"; then
      echo "PRICEWATCH_GOOD_SEARCH_MCP_URL=$mcp_url" >> "$env_file"
    fi
    return
  fi

  cat > "$env_file" <<EOF
PRICEWATCH_HOST=0.0.0.0
PRICEWATCH_PORT=8080
PRICEWATCH_DATABASE_URL=sqlite:///./data/pricewatch.db
PRICEWATCH_OLLAMA_BASE_URL=http://localhost:11434
PRICEWATCH_OLLAMA_MODEL=llama3.2
PRICEWATCH_GOOD_SEARCH_MCP_URL=${mcp_url:-http://127.0.0.1:8765/mcp}
PRICEWATCH_GOOD_SEARCH_AUTO_DISCOVER=true
PRICEWATCH_GOOD_SEARCH_SCRAPE_TOOL=scrape
PRICEWATCH_GOOD_SEARCH_SEARCH_URL_TEMPLATE=https://html.duckduckgo.com/html/?q={query}
PRICEWATCH_GOOD_SEARCH_MAX_CHARS=20000
PRICEWATCH_GOOD_SEARCH_MAX_TIER=2
PRICEWATCH_GOOD_SEARCH_TIMEOUT_SECONDS=120
PRICEWATCH_CHECK_INTERVAL_MINUTES=60
EOF
}

install_prereqs() {
  log "Checking prerequisites"
  command -v git >/dev/null || die "git is required"
  command -v python3 >/dev/null || die "python3 is required"

  if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    die "Python 3.11+ is required"
  fi

  if ! command -v ollama >/dev/null; then
    warn "ollama not found in PATH — install Ollama before running price checks"
  elif ! curl -sf http://localhost:11434/api/tags >/dev/null; then
    warn "Ollama does not appear to be running on localhost:11434"
  fi
}

ensure_run_user() {
  if id "$RUN_USER" >/dev/null 2>&1; then
    return
  fi
  log "Creating system user $RUN_USER"
  useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$RUN_USER"
}

sync_repo() {
  log "Syncing Pricewatch to $INSTALL_DIR"
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
  else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
}

install_python_env() {
  log "Installing Python dependencies"
  python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR"
}

install_systemd_service() {
  if [[ "${SKIP_SYSTEMD:-0}" == "1" ]]; then
    warn "Skipping systemd setup (SKIP_SYSTEMD=1)"
    return
  fi

  log "Installing systemd service"
  sed "s|^User=.*|User=$RUN_USER|" "$INSTALL_DIR/deploy/pricewatch.service" > "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"
}

install_auto_update_timer() {
  if [[ "${SKIP_SYSTEMD:-0}" == "1" || "${SKIP_AUTO_UPDATE:-0}" == "1" ]]; then
    warn "Skipping auto-update timer (SKIP_SYSTEMD or SKIP_AUTO_UPDATE)"
    return
  fi

  log "Installing auto-update timer (checks main every 10 minutes)"
  chmod +x "$INSTALL_DIR/deploy/update.sh"
  cp "$INSTALL_DIR/deploy/pricewatch-update.service" /etc/systemd/system/
  cp "$INSTALL_DIR/deploy/pricewatch-update.timer" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now pricewatch-update.timer
}

print_summary() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  cat <<EOF

Pricewatch installed.

  Dashboard:  http://${ip:-localhost}:8080/
  Health:     http://${ip:-localhost}:8080/health
  Service:    systemctl status $SERVICE_NAME
  Logs:       journalctl -u $SERVICE_NAME -f
  Config:     $INSTALL_DIR/.env
  Auto-update: systemctl status pricewatch-update.timer

If Good-search is not connected, edit .env and set PRICEWATCH_GOOD_SEARCH_MCP_URL,
then run: sudo systemctl restart $SERVICE_NAME

Manual update: sudo bash $INSTALL_DIR/deploy/update.sh

EOF
}

main() {
  require_root
  install_prereqs
  ensure_run_user
  sync_repo

  local mcp_url
  mcp_url="$(detect_good_search_mcp_url || true)"
  if [[ -z "$mcp_url" ]]; then
    warn "Could not auto-detect Good-search MCP URL — edit $INSTALL_DIR/.env after install"
  else
    log "Detected Good-search MCP URL"
  fi

  write_env_file "$INSTALL_DIR/.env" "$mcp_url"
  install_python_env
  chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"
  install_systemd_service
  install_auto_update_timer
  print_summary
}

main "$@"
