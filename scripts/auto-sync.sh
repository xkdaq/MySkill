#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SYNC_ENV_FILE="$REPO_ROOT/.skills-sync.env"

if [ -f "$SYNC_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$SYNC_ENV_FILE"
fi

cd "$REPO_ROOT"

if [ ! -d "$REPO_ROOT/skills" ]; then
  exit 0
fi

# 分发前先把 _shared 母本同步进各 skill references 副本，避免 pull 后副本不一致
sh "$REPO_ROOT/scripts/sync-refs.sh"

install_cmd="sh \"$REPO_ROOT/scripts/install.sh\" --agent all"

if [ -n "${CLAUDE_DIR:-}" ]; then
  install_cmd="$install_cmd --claude-dir \"$CLAUDE_DIR\""
fi

if [ -n "${CURSOR_DIR:-}" ]; then
  install_cmd="$install_cmd --cursor-dir \"$CURSOR_DIR\""
fi

if [ -n "${CODEX_DIR:-}" ]; then
  install_cmd="$install_cmd --codex-dir \"$CODEX_DIR\""
fi

if [ -n "${QODER_DIR:-}" ]; then
  install_cmd="$install_cmd --qoder-dir \"$QODER_DIR\""
fi

if [ -n "${WORKBUDDY_DIR:-}" ]; then
  install_cmd="$install_cmd --workbuddy-dir \"$WORKBUDDY_DIR\""
fi

eval "$install_cmd"
