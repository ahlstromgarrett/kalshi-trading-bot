#!/bin/bash
# Kalshi watchdog -- Linux/systemd port of watchdog.sh, fired every 2 minutes
# by kalshi-watchdog.timer. Restarts the dashboard if its port isn't
# responding, and restarts the bot if it hasn't logged a heartbeat recently.
# Runs as root (via systemd) so it can call systemctl on the other units.

cd /opt/kalshi
BOT_LOG=logs/bot.log
WATCHDOG_LOG=logs/watchdog.log

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') [watchdog] $1" >> "$WATCHDOG_LOG"
}

# Dashboard: is the port even up?
if ! nc -z -w2 127.0.0.1 8765 2>/dev/null; then
  log "dashboard not responding -- restarting"
  systemctl restart kalshi-dashboard.service
fi

# Bot: has it logged a heartbeat recently?
if [ ! -f "$BOT_LOG" ]; then
  log "no bot log file found -- restarting"
  systemctl restart kalshi-bot.service
  exit 0
fi

LAST_TS=$(tail -200 "$BOT_LOG" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}' | tail -1 | cut -d',' -f1)
if [ -z "$LAST_TS" ]; then
  log "no timestamped log lines found -- restarting"
  systemctl restart kalshi-bot.service
  exit 0
fi

LAST_EPOCH=$(date -d "$LAST_TS" +%s 2>/dev/null)
NOW_EPOCH=$(date +%s)
if [ -n "$LAST_EPOCH" ]; then
  DIFF=$((NOW_EPOCH - LAST_EPOCH))
  # Bot polls every 30s and logs a heartbeat every pass -- 5 min of silence
  # means it's actually stuck/dead, not just between polls.
  if [ "$DIFF" -gt 300 ]; then
    log "no heartbeat in ${DIFF}s -- restarting"
    systemctl restart kalshi-bot.service
  fi
fi
