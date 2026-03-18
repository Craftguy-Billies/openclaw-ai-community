#!/usr/bin/env zsh
set -euo pipefail

PERSONA="${1:-luna}"
EVERY="${2:-30s}"
TZ_NAME="${3:-Asia/Hong_Kong}"
JOB_NAME="IGGF Auto-Post ${PERSONA}"

SOUL_SRC="/Users/billiez/Downloads/openclaw/souls/SOUL-${PERSONA}.md"
SOUL_DST="$HOME/.openclaw/workspace/SOUL.md"

if [[ ! -f "$SOUL_SRC" ]]; then
  echo "Missing SOUL file: $SOUL_SRC"
  exit 1
fi

mkdir -p "$HOME/.openclaw/workspace"
cp "$SOUL_SRC" "$SOUL_DST"

echo "Using SOUL profile: $PERSONA"
openclaw daemon status >/dev/null || openclaw daemon start >/dev/null

retry_openclaw() {
  local attempt=1
  local max_attempts=6
  while (( attempt <= max_attempts )); do
    if "$@"; then
      return 0
    fi
    sleep 1
    ((attempt++))
  done
  return 1
}

JOBS_JSON=$(retry_openclaw openclaw cron list --all --json || echo '{"jobs":[]}')
EXISTING_ID=$(echo "$JOBS_JSON" | /Users/billiez/Downloads/openclaw/.venv/bin/python -c 'import json,sys; name=sys.argv[1];
raw=sys.stdin.read().strip();
try:
    data=json.loads(raw) if raw else {"jobs":[]}
except Exception:
    data={"jobs":[]}
print(next((str(j.get("id")) for j in data.get("jobs",[]) if j.get("name")==name), ""))' "$JOB_NAME")
if [[ -n "$EXISTING_ID" ]]; then
  echo "Removing existing job: $EXISTING_ID"
  retry_openclaw openclaw cron rm "$EXISTING_ID" >/dev/null || true
fi

retry_openclaw openclaw cron add \
  --name "$JOB_NAME" \
  --every "$EVERY" \
  --tz "$TZ_NAME" \
  --session isolated \
  --session-key "agent:main:iggf-${PERSONA}" \
  --no-deliver \
  --message "[CRON THINK] Check your Instagram mood and decide if you should post a new story right now. If posting, output exact [INSTAGRAM POST] format. If not, output NO_POST." \
  --light-context \
  --json

echo "Cron job installed."
retry_openclaw openclaw cron list --all || true
