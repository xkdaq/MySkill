#!/bin/sh

set -eu

. "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/common.sh"

ACTION="install"
AGENT="claude"
CLAUDE_DIR=""
CURSOR_DIR=""
CODEX_DIR=""
QODER_DIR=""
WORKBUDDY_DIR=""
SKILLS_CSV=""

print_help() {
  cat <<EOF
公共 Skills 安装脚本

用法：
  sh scripts/install.sh                                # 一键安装到 claude (默认)
  sh scripts/install.sh --agent claude                 # 安装到 claude
  sh scripts/install.sh --agent codex                  # 安装到 codex
  sh scripts/install.sh --agent cursor                 # 安装到 cursor
  sh scripts/install.sh --agent qoder                  # 安装到 qoder
  sh scripts/install.sh --agent workbuddy              # 安装到 workbuddy
  sh scripts/install.sh --agent all                    # 安装到所有 agent
  sh scripts/install.sh --skills android-anti-detection # 仅安装指定 skill

兼容旧参数：
  sh scripts/install.sh --tool claude

参数：
  --agent, --tool AGENT        claude | cursor | codex | qoder | workbuddy | all (默认: claude)
  --skills NAME1,NAME2         仅链接指定 skill，默认链接仓库内全部 skill
  --claude-dir PATH            覆盖 Claude skills 目录 (默认: $DEFAULT_CLAUDE_DIR)
  --cursor-dir PATH            覆盖 Cursor skills 目录 (默认: ${CURSOR_SKILLS_DIR:-$DEFAULT_CURSOR_DIR})
  --codex-dir PATH             覆盖 Codex skills 目录 (默认: $DEFAULT_CODEX_DIR)
  --qoder-dir PATH             覆盖 Qoder skills 目录 (默认: ${QODER_SKILLS_DIR:-$DEFAULT_QODER_DIR})
  --workbuddy-dir PATH         覆盖 WorkBuddy skills 目录 (默认: ${WORKBUDDY_SKILLS_DIR:-$DEFAULT_WORKBUDDY_DIR})
  --help                       显示帮助
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --agent|--tool)
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
    --mode)
      [ "${2:-}" = "link" ] || fail "当前仅支持 --mode link"
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

# 用户指定了自定义目录时导出，供 resolve_agent_dir 使用
[ -n "$CLAUDE_DIR" ] && export CLAUDE_DIR
[ -n "$CURSOR_DIR" ] && export CURSOR_DIR
[ -n "$CODEX_DIR" ] && export CODEX_DIR
[ -n "$QODER_DIR" ] && export QODER_DIR
[ -n "$WORKBUDDY_DIR" ] && export WORKBUDDY_DIR

for target_agent in $(for_each_agent "$AGENT"); do
  dest_dir=$(resolve_agent_dir "$target_agent")
  log "开始链接到 $target_agent: $dest_dir"

  for skill_name in $(resolve_skill_set "$SKILLS_CSV"); do
    link_skill_to_dir "$skill_name" "$dest_dir"
  done

  prune_broken_links "$dest_dir"
done

log "全部完成"
