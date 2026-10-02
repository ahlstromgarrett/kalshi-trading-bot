#!/bin/bash
# Kalshi watchdog -- runs every few minutes via launchd.
# Restarts the dashboard if its port isn't responding, and restarts the bot
# if it hasn't logged a heartbeat recently (Kalshi has markets open near
# around the clock, so unlike a single-exchange stock bot this doesn't gate
# on market hours). Uses `launchctl kickstart` so restarts stay inside
# launchd's own supervision instead of spawning untracked processes.

cd /Users/ahlstrom/Kalshi
BOT_LOG=logs/bot.log
WATCHDOG_LOG=logs/watchdog.log
UID_GUI="gui/$(id -u)"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') [watchdog] $1" >> "$WATCHDOG_LOG"
}

# Dashboard: is the port even up?
if ! nc -z -w2 127.0.0.1 8765 2>/dev/null; then
  log "dashboard not responding -- restarting"
  launchctl kickstart -k "$UID_GUI/com.kalshi.dashboard"
fi

# Bot: has it logged a heartbeat recently?
if [ ! -f "$BOT_LOG" ]; then
  log "no bot log file found -- restarting"
  launchctl kickstart -k "$UID_GUI/com.kalshi.bot"
  exit 0
fi

LAST_TS=$(tail -200 "$BOT_LOG" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}' | tail -1 | cut -d',' -f1)
if [ -z "$LAST_TS" ]; then
  log "no timestamped log lines found -- restarting"
  launchctl kickstart -k "$UID_GUI/com.kalshi.bot"
  exit 0
fi

LAST_EPOCH=$(date -j -f "%Y-%m-%d %H:%M:%S" "$LAST_TS" +%s 2>/dev/null)
NOW_EPOCH=$(date +%s)
if [ -n "$LAST_EPOCH" ]; then
  DIFF=$((NOW_EPOCH - LAST_EPOCH))
  # Bot polls every 30s and logs a heartbeat every pass -- 5 min of silence
  # means it's actually stuck/dead, not just between polls.
  if [ "$DIFF" -gt 300 ]; then
    log "no heartbeat in ${DIFF}s -- restarting"
    launchctl kickstart -k "$UID_GUI/com.kalshi.bot"
  fi
fi
