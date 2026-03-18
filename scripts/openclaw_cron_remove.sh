#!/usr/bin/env zsh
set -euo pipefail

PERSONA="${1:-luna}"
JOB_NAME="IGGF Auto-Post ${PERSONA}"

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
if [[ -z "$EXISTING_ID" ]]; then
  echo "No job found for ${JOB_NAME}"
  exit 0
fi

retry_openclaw openclaw cron rm "$EXISTING_ID"
echo "Removed ${JOB_NAME} (${EXISTING_ID})"
