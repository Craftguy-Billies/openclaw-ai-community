#!/usr/bin/env zsh
set -euo pipefail

PLIST_SRC="/Users/billiez/Downloads/openclaw/deploy/com.billiez.aiinstagram.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.billiez.aiinstagram.plist"

if [[ ! -f "$PLIST_SRC" ]]; then
  echo "Missing $PLIST_SRC"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
launchctl unload "$PLIST_DST" >/dev/null 2>&1 || true
launchctl load "$PLIST_DST"

echo "Installed and started: com.billiez.aiinstagram"
echo "Check status: launchctl list | grep com.billiez.aiinstagram"
echo "Logs: /tmp/aiinstagram.stdout.log and /tmp/aiinstagram.stderr.log"
