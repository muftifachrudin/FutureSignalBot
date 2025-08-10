#!/usr/bin/env bash
# Automated redeploy script for FutureSignalBot on Linux VM
# Usage (run as root or with sudo):
#   sudo bash tools/redeploy_fsbot.sh
# Optional flags:
#   --skip-backup       : skip env & watchlist backup
#   --no-test           : skip quick signal test
#   --branch <name>     : use a branch other than main
#   --fast              : skip pip install if requirements hash unchanged

set -euo pipefail

SERVICE="futuresignalbot.service"
APP_DIR="/opt/futuresignalbot"
ENV_FILE="/etc/futuresignalbot.env"
WATCHLIST_FILE="$APP_DIR/pairs_watchlist.json"
PYTHON_BIN="python3"
RUN_USER="fsbot"
BRANCH="main"
DO_BACKUP=1
DO_TEST=1
FAST=0

log(){ echo -e "[redeploy][$(date +%H:%M:%S)] $*"; }
warn(){ echo -e "[redeploy][WARN] $*" >&2; }
err(){ echo -e "[redeploy][ERROR] $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-backup) DO_BACKUP=0; shift ;;
    --no-test) DO_TEST=0; shift ;;
    --branch) BRANCH="${2:-main}"; shift 2 ;;
    --fast) FAST=1; shift ;;
    *) warn "Unknown flag $1"; shift ;;
  esac
done

[[ $EUID -ne 0 ]] && err "Must run as root (sudo)."

[[ -d $APP_DIR/.git ]] || err "Directory $APP_DIR not a git repo."

cd "$APP_DIR"

# Record current HEAD for rollback
OLD_COMMIT=$(git rev-parse --short HEAD || echo "unknown")

if (( DO_BACKUP )); then
  TS=$(date +%Y%m%d%H%M%S)
  if [[ -f $ENV_FILE ]]; then
    cp "$ENV_FILE" "${ENV_FILE}.bak.$TS" && log "Backup env -> ${ENV_FILE}.bak.$TS"
  else
    warn "Env file not found: $ENV_FILE"
  fi
  if [[ -f $WATCHLIST_FILE ]]; then
    cp "$WATCHLIST_FILE" "${WATCHLIST_FILE}.bak.$TS" && log "Backup watchlist -> ${WATCHLIST_FILE}.bak.$TS"
  fi
fi

log "Stopping service..."
systemctl stop "$SERVICE" || warn "Service stop returned non-zero"

log "Fetching branch $BRANCH..."
sudo -u "$RUN_USER" git fetch --all --prune
sudo -u "$RUN_USER" git checkout "$BRANCH"
sudo -u "$RUN_USER" git reset --hard "origin/$BRANCH"

REQ_HASH_FILE=".requirements.sha256"
NEW_HASH=$(sha256sum requirements.txt 2>/dev/null | awk '{print $1}' || echo "none")
OLD_HASH=$(cat "$REQ_HASH_FILE" 2>/dev/null || echo "none")

if (( FAST )) && [[ "$NEW_HASH" == "$OLD_HASH" ]]; then
  log "FAST mode: requirements hash unchanged, skip pip install"
else
  log "Installing / syncing Python dependencies..."
  sudo -u "$RUN_USER" $PYTHON_BIN -m pip install --no-cache-dir -r requirements.txt
  echo "$NEW_HASH" > "$REQ_HASH_FILE"
fi

if (( DO_TEST )); then
  log "Running quick signal test (non-fatal if fails)..."
  set +e
  sudo -u "$RUN_USER" $PYTHON_BIN scripts/quick_signal_test.py BTCUSDT >/tmp/fsbot_quick_test.log 2>&1
  TEST_RC=$?
  set -e
  if [[ $TEST_RC -ne 0 ]]; then
    warn "Quick test failed (exit $TEST_RC), see /tmp/fsbot_quick_test.log"
  else
    log "Quick test OK"
  fi
fi

log "Starting service..."
systemctl start "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || {
  warn "Service not active, attempting journal tail and rollback"
  journalctl -u "$SERVICE" -n 80 --no-pager
  warn "Rolling back to previous commit $OLD_COMMIT"
  sudo -u "$RUN_USER" git reset --hard "$OLD_COMMIT"
  systemctl start "$SERVICE" || err "Rollback start failed"
  exit 1
}

log "Service active: $(systemctl show -p MainPID --value "$SERVICE")"
log "Recent logs:"
journalctl -u "$SERVICE" -n 50 --no-pager || true

log "Redeploy complete."
exit 0
