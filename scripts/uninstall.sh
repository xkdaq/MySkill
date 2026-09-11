#!/bin/sh

set -eu

. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

AGENT="claude"
CLAUDE_DIR=""
CURSOR_DIR=""
CODEX_DIR=""
QODER_DIR=""
WORKBUDDY_DIR=""
SKILLS_CSV=""

print_help() {
  cat <<EOF
公共 Skills 卸载脚本

用法：
  sh scripts/uninstall.sh                              # 从 claude 卸载 (默认)
  sh scripts/uninstall.sh --agent all                  # 从所有 agent 卸载
  sh scripts/uninstall.sh --agent qoder                # 从 qoder 卸载
  sh scripts/uninstall.sh --agent workbuddy            # 从 workbuddy 卸载
  sh scripts/uninstall.sh --skills android-anti-detection # 仅卸载指定 skill

参数：
  --agent AGENT                claude | cursor | codex | qoder | workbuddy | all (默认: claude)
  --skills NAME1,NAME2         仅移除指定 skill，默认移除仓库内全部 skill
  --claude-dir PATH            覆盖 Claude skills 目录
  --cursor-dir PATH            覆盖 Cursor skills 目录
  --codex-dir PATH             覆盖 Codex skills 目录
  --qoder-dir PATH             覆盖 Qoder skills 目录
  --workbuddy-dir PATH         覆盖 WorkBuddy skills 目录
  --help                       显示帮助
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --agent)
      AGENT="${2:-}"
      shift 2
      ;;
    --skills)
      SKILLS_CSV="${2:-}"
      shift 2
      ;;
    --claude-dir)
      CLAUDE_DIR="${2:-}"
      shift 2
      ;;
    --cursor-dir)
      CURSOR_DIR="${2:-}"
      shift 2
      ;;
    --codex-dir)
      CODEX_DIR="${2:-}"
      shift 2
      ;;
    --qoder-dir)
      QODER_DIR="${2:-}"
      shift 2
      ;;
    --workbuddy-dir)
      WORKBUDDY_DIR="${2:-}"
      shift 2
      ;;
    --help|-h)
      print_help
      exit 0
      ;;
    *)
      fail "未知参数: $1"
      ;;
  esac
done

ensure_repo_skills_dir

[ -n "$CLAUDE_DIR" ] && export CLAUDE_DIR
[ -n "$CURSOR_DIR" ] && export CURSOR_DIR
[ -n "$CODEX_DIR" ] && export CODEX_DIR
[ -n "$QODER_DIR" ] && export QODER_DIR
[ -n "$WORKBUDDY_DIR" ] && export WORKBUDDY_DIR

for target_agent in $(for_each_agent "$AGENT"); do
  dest_dir=$(resolve_agent_dir "$target_agent")
  log "开始从 $target_agent 移除: $dest_dir"

  for skill_name in $(resolve_skill_set "$SKILLS_CSV"); do
    remove_skill_from_dir "$skill_name" "$dest_dir"
  done
done

log "全部完成"
