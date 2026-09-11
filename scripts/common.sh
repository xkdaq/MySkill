#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SKILLS_SOURCE_DIR="$REPO_ROOT/skills"

DEFAULT_CLAUDE_DIR="$HOME/.claude/skills"
DEFAULT_CURSOR_DIR="$HOME/.cursor/skills"
DEFAULT_CODEX_DIR="$HOME/.codex/skills"
DEFAULT_QODER_DIR="$HOME/.qoder/skills"
DEFAULT_WORKBUDDY_DIR="$HOME/.workbuddy/skills"

log() {
  echo "$*"
}

fail() {
  echo "错误：$*" >&2
  exit 1
}

ensure_repo_skills_dir() {
  [ -d "$SKILLS_SOURCE_DIR" ] || fail "未找到 skills 目录: $SKILLS_SOURCE_DIR"
}

trim_spaces() {
  printf "%s" "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

normalize_agent_name() {
  agent=$(printf "%s" "$1" | tr '[:upper:]' '[:lower:]')
  case "$agent" in
    claude|cursor|codex|qoder|workbuddy|all)
      printf "%s" "$agent"
      ;;
    *)
      fail "不支持的 agent: $1"
      ;;
  esac
}

resolve_agent_dir() {
  agent=$(normalize_agent_name "$1")

  case "$agent" in
    claude)
      printf "%s" "${CLAUDE_DIR:-$DEFAULT_CLAUDE_DIR}"
      ;;
    cursor)
      printf "%s" "${CURSOR_DIR:-${CURSOR_SKILLS_DIR:-$DEFAULT_CURSOR_DIR}}"
      ;;
    codex)
      printf "%s" "${CODEX_DIR:-$DEFAULT_CODEX_DIR}"
      ;;
    qoder)
      printf "%s" "${QODER_DIR:-${QODER_SKILLS_DIR:-$DEFAULT_QODER_DIR}}"
      ;;
    workbuddy)
      printf "%s" "${WORKBUDDY_DIR:-${WORKBUDDY_SKILLS_DIR:-$DEFAULT_WORKBUDDY_DIR}}"
      ;;
    *)
      fail "all 不是具体安装目录，请先展开"
      ;;
  esac
}

list_repo_skill_names() {
  ensure_repo_skills_dir
  # 递归查找所有带 SKILL.md 的目录；输出相对于 SKILLS_SOURCE_DIR 的路径
  # -mindepth 2 排除 SKILLS_SOURCE_DIR 自身；管道+while read 规避 set -eu 下 find 空结果非零退出
  find "$SKILLS_SOURCE_DIR" -mindepth 2 -type f -name SKILL.md | while IFS= read -r skill_file; do
    skill_dir=$(dirname "$skill_file")
    case "$skill_dir" in
      "$SKILLS_SOURCE_DIR"/*) ;;
      *) continue ;;
    esac
    rel_path=${skill_dir#"$SKILLS_SOURCE_DIR"/}
    printf '%s\n' "$rel_path"
  done
}

skill_exists_in_repo() {
  skill_name="$1"
  [ -d "$SKILLS_SOURCE_DIR/$skill_name" ] && [ -f "$SKILLS_SOURCE_DIR/$skill_name/SKILL.md" ]
}

resolve_skill_set() {
  skills_csv=${1:-}

  if [ -z "$skills_csv" ]; then
    list_repo_skill_names
    return 0
  fi

  OLD_IFS=$IFS
  IFS=','
  for raw_name in $skills_csv; do
    skill_name=$(trim_spaces "$raw_name")
    [ -n "$skill_name" ] || continue
    skill_exists_in_repo "$skill_name" || fail "仓库内不存在 skill: $skill_name"
    printf "%s\n" "$skill_name"
  done
  IFS=$OLD_IFS
}

for_each_agent() {
  agent_spec="$1"
  if [ "$agent_spec" = "all" ]; then
    printf "claude\ncursor\ncodex\nqoder\nworkbuddy\n"
  else
    printf "%s\n" "$(normalize_agent_name "$agent_spec")"
  fi
}

write_repo_marker() {
  dest_base_dir="$1"
  mkdir -p "$dest_base_dir"
  printf "%s\n" "$REPO_ROOT" > "$dest_base_dir/.public-agent-skills-repo"
}

link_skill_to_dir() {
  skill_name="$1"
  dest_base_dir="$2"
  src_dir="$SKILLS_SOURCE_DIR/$skill_name"
  # 嵌套 skill（含 /）平铺到 dest_base_dir 的 basename 位置，避免 agent skills 索引不扫子目录
  skill_basename=$(basename "$skill_name")
  link_target="$dest_base_dir/$skill_basename"

  mkdir -p "$dest_base_dir"

  # 安全移除：符号链接用 unlink 避免跟随链接删除源文件
  if [ -L "$link_target" ]; then
    current_target=$(readlink "$link_target")
    if [ "$current_target" = "$src_dir" ]; then
      log "已链接: $skill_name -> $link_target (跳过, 已存在)"
      write_repo_marker "$dest_base_dir"
      return 0
    fi
    unlink "$link_target"
  elif [ -e "$link_target" ]; then
    fail "目标已存在且不是符号链接: $link_target (源 skill: $skill_name)"
  fi

  ln -s "$src_dir" "$link_target"
  write_repo_marker "$dest_base_dir"
  log "已链接: $skill_name -> $link_target"
}

prune_broken_links() {
  dest_base_dir="$1"
  [ -d "$dest_base_dir" ] || return 0
  find "$dest_base_dir" -maxdepth 1 -type l ! -exec test -e {} \; -print | while IFS= read -r broken; do
    # unlink 在 macOS 上偶尔遇到 EPERM（例如 SIP/权限保护或上一次 hook 残留），
    # 这里用 if/else 包裹：成功才报"已清理"，失败时给"无法清理"提示但不中断外层 setup.sh，
    # 避免一个 agent 目录的清理故障让整轮分发中途退出。
    if unlink "$broken" 2>/dev/null; then
      log "已清理断链: $broken"
    else
      log "无法清理断链（已跳过，待人工处理）: $broken"
    fi
  done
}

remove_skill_from_dir() {
  skill_name="$1"
  dest_base_dir="$2"
  # 嵌套 skill 平铺在 dest_base_dir/<basename>，与 link_skill_to_dir 对称
  skill_basename=$(basename "$skill_name")
  remove_target="$dest_base_dir/$skill_basename"

  if [ -e "$remove_target" ] || [ -L "$remove_target" ]; then
    rm -rf "$remove_target"
    log "已移除: $remove_target"
  else
    log "跳过: $remove_target 不存在"
  fi
}

read_skill_title() {
  skill_name="$1"
  skill_file="$SKILLS_SOURCE_DIR/$skill_name/SKILL.md"
  description=$(sed -n '/^description:/{
n
    /^  /p
    q
  }' "$skill_file" 2>/dev/null | sed 's/^[[:space:]]*//')

  if [ -z "$description" ]; then
    description=$(sed -n 's/^description:[[:space:]]*//p' "$skill_file" | head -n 1 | sed 's/^|[[:space:]]*//')
  fi

  if [ -z "$description" ]; then
    description="无描述"
  fi

  printf "%s" "$description"
}
