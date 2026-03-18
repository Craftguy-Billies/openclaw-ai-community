#!/usr/bin/env zsh
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <luna|yuki|serena|rina|mira>"
  exit 1
fi

NAME="$1"
SRC="$HOME/.openclaw/workspace/SOUL-${NAME}.md"
DST="$HOME/.openclaw/workspace/SOUL.md"

if [[ ! -f "$SRC" ]]; then
  echo "Missing file: $SRC"
  exit 1
fi

cp "$SRC" "$DST"
openclaw daemon restart

echo "Active SOUL set to: $NAME"
