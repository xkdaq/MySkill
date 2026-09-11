#!/bin/sh

set -eu

. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

AGENT=""
CLAUDE_DIR=""
CURSOR_DIR=""
CODEX_DIR=""
QODER_DIR=""
WORKBUDDY_DIR=""

print_help() {
  cat <<EOF
公共 Skills 列表脚本

用法：
  sh scripts/list.sh
  sh scripts/list.sh --agent claude
  sh scripts/list.sh --agent qoder
  sh scripts/list.sh --agent workbuddy
  sh scripts/list.sh --agent all --cursor-dir /path/to/cursor/skills

参数：
  --agent AGENT                claude | cursor | codex | qoder | workbuddy | all
  --claude-dir PATH            Claude skills 目录，默认: $DEFAULT_CLAUDE_DIR
  --cursor-dir PATH            Cursor skills 目录，默认: ${CURSOR_SKILLS_DIR:-$DEFAULT_CURSOR_DIR}
  --codex-dir PATH             Codex skills 目录，默认: $DEFAULT_CODEX_DIR
  --qoder-dir PATH             Qoder skills 目录，默认: ${QODER_SKILLS_DIR:-$DEFAULT_QODER_DIR}
  --workbuddy-dir PATH         WorkBuddy skills 目录，默认: ${WORKBUDDY_SKILLS_DIR:-$DEFAULT_WORKBUDDY_DIR}
  --help                       显示帮助
EOF
}

list_repo() {
  log "仓库内 skill 列表:"
  skill_names=$(list_repo_skill_names)
  if [ -z "$skill_names" ]; then
    log "  (当前没有 skill)"
    return 0
  fi
  for skill_name in $skill_names; do
    printf -- "- %s: %s\n" "$skill_name" "$(read_skill_title "$skill_name")"
  done
}

list_agent() {
  target_agent="$1"
  [ -n "$CLAUDE_DIR" ] && export CLAUDE_DIR
  [ -n "$CURSOR_DIR" ] && export CURSOR_DIR
  [ -n "$CODEX_DIR" ] && export CODEX_DIR
  [ -n "$QODER_DIR" ] && export QODER_DIR
  [ -n "$WORKBUDDY_DIR" ] && export WORKBUDDY_DIR
  dest_dir=$(resolve_agent_dir "$target_agent")

  log "$target_agent 已安装 skill:"
  if [ ! -d "$dest_dir" ]; then
    log "  (目录不存在) $dest_dir"
    return 0
  fi

  count=0
  for skill_name in $(list_repo_skill_names); do
    if [ -d "$dest_dir/$skill_name" ] && [ -f "$dest_dir/$skill_name/SKILL.md" ]; then
      printf -- "  - %s\n" "$skill_name"
      count=$((count + 1))
    fi
  done

  if [ "$count" -eq 0 ]; then
    log "  (无当前仓库管理的 skill)"
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --agent)
      AGENT="${2:-}"
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
list_repo

if [ -n "$AGENT" ]; then
  for target_agent in $(for_each_agent "$AGENT"); do
    list_agent "$target_agent"
  done
fi
