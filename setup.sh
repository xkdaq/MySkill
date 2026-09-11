#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
  cat <<EOF
MySkill 私人 skill 仓库管理脚本

用法：
  sh setup.sh              # 一键软链接到全部 agent (默认)
  sh setup.sh claude       # 仅软链接到 claude
  sh setup.sh cursor       # 仅软链接到 cursor
  sh setup.sh codex        # 仅软链接到 codex
  sh setup.sh qoder        # 仅软链接到 qoder
  sh setup.sh workbuddy    # 仅软链接到 workbuddy
  sh setup.sh hooks        # 激活 git hooks，commit / merge / checkout 后自动分发
  sh setup.sh list         # 列出仓库内所有 skills
  sh setup.sh installed    # 列出已安装到各 agent 的 skills
  sh setup.sh uninstall        # 从所有 agent 卸载 (默认)
  sh setup.sh uninstall qoder  # 仅从 qoder 卸载
  sh setup.sh help         # 显示本帮助
EOF
}

case "${1:-}" in
  ""|all)
    sh "$SCRIPT_DIR/scripts/install.sh" --agent all
    sh "$SCRIPT_DIR/scripts/setup-auto-sync.sh"
    ;;
  claude|cursor|codex|qoder|workbuddy)
    sh "$SCRIPT_DIR/scripts/install.sh" --agent "$1"
    sh "$SCRIPT_DIR/scripts/setup-auto-sync.sh"
    ;;
  hooks)
    sh "$SCRIPT_DIR/scripts/setup-auto-sync.sh"
    ;;
  list)
    sh "$SCRIPT_DIR/scripts/list.sh"
    ;;
  installed)
    sh "$SCRIPT_DIR/scripts/list.sh" --agent all
    ;;
  uninstall)
    if [ -n "${2:-}" ]; then
      sh "$SCRIPT_DIR/scripts/uninstall.sh" --agent "$2"
    else
      sh "$SCRIPT_DIR/scripts/uninstall.sh" --agent all
    fi
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "未知命令: $1" >&2
    usage
    exit 1
    ;;
esac
