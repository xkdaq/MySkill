#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
HOOKS_DIR="$REPO_ROOT/.githooks"
SYNC_ENV_EXAMPLE="$REPO_ROOT/.skills-sync.env.example"
SYNC_ENV_FILE="$REPO_ROOT/.skills-sync.env"

mkdir -p "$HOOKS_DIR"

chmod +x "$HOOKS_DIR/post-merge" "$HOOKS_DIR/post-checkout" "$HOOKS_DIR/post-rewrite" "$REPO_ROOT/scripts/auto-sync.sh"
git config core.hooksPath .githooks

if [ ! -f "$SYNC_ENV_FILE" ] && [ -f "$SYNC_ENV_EXAMPLE" ]; then
  cp "$SYNC_ENV_EXAMPLE" "$SYNC_ENV_FILE"
fi

echo "已启用自动同步"
echo "hooks 路径: .githooks"
echo "如需覆盖目录，请编辑: $SYNC_ENV_FILE"
