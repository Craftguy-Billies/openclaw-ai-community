#!/usr/bin/env zsh
set -euo pipefail

cd /Users/billiez/Downloads/openclaw

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt >/dev/null

export STRICT_OPENCLAW_ONLY=1
export OPENCLAW_USE=1
export OPENCLAW_PROFILE_NAME=""
export FORCE_AUTO_POST_MODE=1
export AUTO_LOOP_SECONDS=10
export APP_DISABLE_AUTO_LOOP=1
export APP_ENABLE_CRON_SYNC=1
export CRON_SYNC_SECONDS=6

mkdir -p "$HOME/.openclaw/workspace"
cp -f souls/SOUL-*.md "$HOME/.openclaw/workspace/" 2>/dev/null || true
if [[ -f "$HOME/.openclaw/workspace/SOUL-luna.md" ]]; then
  cp -f "$HOME/.openclaw/workspace/SOUL-luna.md" "$HOME/.openclaw/workspace/SOUL.md"
fi

openclaw daemon start

for _ in {1..10}; do
  if lsof -nP -iTCP:18789 -sTCP:LISTEN >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

openclaw daemon status || true

lsof -ti tcp:7860 | xargs -r kill -9

./scripts/install_launchagent.sh

for _ in {1..12}; do
  if curl -sS http://127.0.0.1:7860/ >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "24/7 stack started."
echo "Web: http://127.0.0.1:7860"
echo "OpenClaw: http://127.0.0.1:18789"
