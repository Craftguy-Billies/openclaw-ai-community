#!/usr/bin/env zsh
set -euo pipefail

launchctl unload "$HOME/Library/LaunchAgents/com.billiez.aiinstagram.plist" >/dev/null 2>&1 || true
openclaw daemon stop || true

echo "24/7 stack stopped."
