#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-status}"

personas=(
  "luna:2m"
  "yuki:2m"
  "serena:6m"
  "rina:10m"
  "mira:14m"
)

action_on() {
  for item in "${personas[@]}"; do
    persona="${item%%:*}"
    every="${item##*:}"
    ./scripts/openclaw_cron_setup.sh "$persona" "$every" "Asia/Hong_Kong"
  done
  echo "✅ Cron ON: all persona jobs installed"
}

action_off() {
  for item in "${personas[@]}"; do
    persona="${item%%:*}"
    ./scripts/openclaw_cron_remove.sh "$persona"
  done
  echo "⏸️ Cron OFF: all persona jobs removed"
}

action_status() {
  ./scripts/openclaw_cron_status.sh
}

case "$MODE" in
  on)
    action_on
    ;;
  off)
    action_off
    ;;
  status)
    action_status
    ;;
  *)
    echo "Usage: ./scripts/openclaw_cron_power.sh [on|off|status]"
    exit 1
    ;;
esac
