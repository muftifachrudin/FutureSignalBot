#!/usr/bin/env bash
# fsbot_manage.sh
# Manajemen FutureSignalBot: rotasi secrets, systemd hardening, health timer, firewall, git history rewrite.
# Subcommands:
#   server-rotate | server-clean-debug | server-watchdog | server-health | server-firewall | server-fail2ban | server-all
#   repo-rewrite | repo-verify | help
# Lihat README untuk penjelasan.
set -euo pipefail

# === Konfigurasi (edit sebelum server-rotate) ===
NEW_TELEGRAM_BOT_TOKEN="PASTE_TELEGRAM_TOKEN_BARU"
NEW_MEXC_API_KEY="PASTE_MEXC_API_KEY_BARU"
NEW_MEXC_SECRET_KEY="PASTE_MEXC_SECRET_BARU"
NEW_COINGLASS_API_KEY="PASTE_COINGLASS_KEY_BARU"
NEW_GEMINI_API_KEY="PASTE_GEMINI_KEY_BARU"

SERVICE_NAME="futuresignalbot.service"
ENV_FILE="/etc/futuresignalbot.env"
APP_DIR="/opt/futuresignalbot"
APP_ENV="${APP_DIR}/.env"
PY_BIN="${APP_DIR}/.venv/bin/python"

OLD_SECRET_PATTERNS=(
  "8440002430:AAG9urLP"
  "mx0vglsx0OoS8WBz9h"
  "be6e64c8c8d54d2abbe2c4f753dc1259"
  "7245ae4567bd4bd79f1f8e6ac2acd279"
  "AIzaSyBzbbasUhR29RfK3Ip4tDhDxA6RHTP2D28"
)

log(){ echo "[INFO] $*"; }
warn(){ echo "[WARN] $*" >&2; }
err(){ echo "[ERR ] $*" >&2; exit 1; }

need_root(){ [[ "$(id -u)" -eq 0 ]] || err "Perlu root/sudo"; }
confirm(){ read -r -p "$1 (y/N): " a; [[ ${a,,} == y || ${a,,} == yes ]]; }
check_service(){ systemctl status "$SERVICE_NAME" >/dev/null 2>&1 || err "Service $SERVICE_NAME tidak ada"; }

server_rotate(){
  need_root; check_service;
  [[ $NEW_TELEGRAM_BOT_TOKEN != PASTE_TELEGRAM_TOKEN_BARU ]] || err "Isi variabel NEW_* dulu";
  umask 077
  cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=$NEW_TELEGRAM_BOT_TOKEN
MEXC_API_KEY=$NEW_MEXC_API_KEY
MEXC_SECRET_KEY=$NEW_MEXC_SECRET_KEY
COINGLASS_API_KEY=$NEW_COINGLASS_API_KEY
GEMINI_API_KEY=$NEW_GEMINI_API_KEY
PYTHONUNBUFFERED=1
EOF
  chown root:fsbot "$ENV_FILE"; chmod 640 "$ENV_FILE"
  install -m 600 -o fsbot -g fsbot "$ENV_FILE" "$APP_ENV"
  systemctl restart "$SERVICE_NAME"; sleep 2
  systemctl --no-pager status "$SERVICE_NAME" | sed -n '1,12p'
  source "$APP_ENV" || true
  curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" || true; echo
}

server_clean_debug(){ need_root; check_service; UF="/etc/systemd/system/${SERVICE_NAME}"; [[ -f $UF ]] || err "Unit tidak ada"; grep -q 'ExecStartPre=.*DEBUG' "$UF" && sed -i '/ExecStartPre=.*DEBUG/d' "$UF" || log "Tidak ada debug"; systemctl daemon-reload; systemctl restart "$SERVICE_NAME"; }

server_watchdog(){ need_root; mkdir -p "/etc/systemd/system/${SERVICE_NAME}.d"; cat > "/etc/systemd/system/${SERVICE_NAME}.d/override.conf" <<EOF
[Service]
WatchdogSec=60
StartLimitIntervalSec=300
StartLimitBurst=5
EOF
systemctl daemon-reload; systemctl restart "$SERVICE_NAME"; }

server_health(){ need_root; cat > /usr/local/bin/fsbot-health.sh <<'EOF'
#!/usr/bin/env bash
set -e
[ -f /opt/futuresignalbot/.env ] && source /opt/futuresignalbot/.env
curl -s --max-time 8 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | grep -q '"ok":true' || systemctl restart futuresignalbot.service
EOF
chmod 700 /usr/local/bin/fsbot-health.sh
cat > /etc/systemd/system/fsbot-health.service <<'EOF'
[Unit]
Description=Health check FutureSignalBot
[Service]
Type=oneshot
ExecStart=/usr/bin/bash /usr/local/bin/fsbot-health.sh
EOF
cat > /etc/systemd/system/fsbot-health.timer <<'EOF'
[Unit]
Description=Run health check every 5 minutes
[Timer]
OnBootSec=2m
OnUnitActiveSec=5m
Unit=fsbot-health.service
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload; systemctl enable --now fsbot-health.timer; systemctl status fsbot-health.timer --no-pager | sed -n '1,10p'; }

server_firewall(){ need_root; if command -v ufw >/dev/null; then ufw allow OpenSSH || true; ufw --force enable; ufw status; else warn "UFW tidak terpasang"; fi }

server_fail2ban(){ need_root; command -v fail2ban-client >/dev/null || { apt update && apt install -y fail2ban; }; [[ -f /etc/fail2ban/jail.local ]] || cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime  = 1h
findtime = 10m
EOF
systemctl restart fail2ban; fail2ban-client status sshd || true; }

server_all(){ server_rotate; server_clean_debug || true; server_watchdog; server_health; server_firewall; log "server-all selesai"; }

repo_rewrite(){ [[ -d .git ]] || err "Jalankan di root repo"; command -v git-filter-repo >/dev/null || { pip install --user git-filter-repo; export PATH="$HOME/.local/bin:$PATH"; }; git ls-files .env >/dev/null 2>&1 && git rm --cached .env || true; : > replace_fsbot_secrets.txt; for p in "${OLD_SECRET_PATTERNS[@]}"; do [[ -n $p ]] && echo "$p==REMOVED_SECRET" >> replace_fsbot_secrets.txt; done; git filter-repo --force --path .env --invert-paths; git filter-repo --force --replace-text replace_fsbot_secrets.txt; confirm "Force push origin main?" && git push --force origin main || warn "Lewati push"; }

repo_verify(){ local fail=0; for p in "${OLD_SECRET_PATTERNS[@]}"; do [[ -z $p ]] && continue; if git grep -q "$p" || grep -R "$p" . >/dev/null 2>&1; then echo "FOUND: $p"; fail=1; fi; done; [[ $fail -eq 0 ]] && log "Tidak ada pola lama" || warn "Masih ada pola"; }

usage(){ cat <<EOF
Usage: $0 <subcommand>
Server: server-rotate | server-clean-debug | server-watchdog | server-health | server-firewall | server-fail2ban | server-all
Repo  : repo-rewrite | repo-verify
Misc  : help
EOF
}

cmd="${1:-help}"; shift || true
case "$cmd" in
  server-rotate) server_rotate "$@";;
  server-clean-debug) server_clean_debug "$@";;
  server-watchdog) server_watchdog "$@";;
  server-health) server_health "$@";;
  server-firewall) server_firewall "$@";;
  server-fail2ban) server_fail2ban "$@";;
  server-all) server_all "$@";;
  repo-rewrite) repo_rewrite "$@";;
  repo-verify) repo_verify "$@";;
  help|--help|-h) usage;;
  *) err "Subcommand tidak dikenali";;
esac
