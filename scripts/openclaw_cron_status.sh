#!/usr/bin/env zsh
set -euo pipefail

openclaw cron status --json || true
echo "---"
openclaw cron list --all --json || true
