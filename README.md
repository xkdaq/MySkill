# MySkill — 私人 skill 仓库

存放自维护的 agent skills。每个 skill 通过 `ln -s` 软链接到 5 个 agent 全局目录：

| Agent | 全局目录 |
|---|---|
| Claude | `~/.claude/skills/` |
| Cursor | `~/.cursor/skills/` |
| Codex  | `~/.codex/skills/` |
| Qoder  | `~/.qoder/skills/` |
| WorkBuddy | `~/.workbuddy/skills/` |

skills/ 下每加一个目录并写好 `SKILL.md`，git commit 后由 hook 自动分发到上述 5 个目录；修改/删除也同理。

## 一次性安装

```sh
cd /Users/xuke/xuke/MySkill
sh setup.sh          # 安装到全部 agent + 激活 git hooks
```

之后任何 `git commit` / `git pull` / `git checkout` 都会触发 hooks 自动重链。

## 日常命令

| 动作 | 命令 |
|---|---|
| 同步一次全部 | `sh setup.sh` |
| 只装到某 agent | `sh setup.sh workbuddy` |
| 查看仓库内有几 个 skill | `sh setup.sh list` |
| 查看各 agent 已装几个 | `sh setup.sh installed` |
| 卸载全部 | `sh setup.sh uninstall` |
| 卸载某个 agent | `sh setup.sh uninstall qoder` |
| 重新激活 hook | `sh setup.sh hooks` |

## 新增一个 skill

```sh
mkdir -p skills/my-new-skill
# 写 skills/my-new-skill/SKILL.md（frontmatter 必填 name + description）
git add . && git commit -m "feat: add my-new-skill"
# hook 自动把软链接发到 5 个 agent 全局
```

## 修改 / 删除

```sh
# 修改：直接编辑 skills/<某>/SKILL.md，5 个全局目录即时可见
# 删除：
git rm -r skills/<某>
git commit
# hook 在重链时 prune，自动清掉 5 个全局目录里的对应软链接
```

## 覆盖默认 agent 目录

默认行为（5 个全局目录）已能覆盖绝大部分场景。如需修改：

```sh
# 临时一次
CLAUDE_DIR=/path/to/custom sh setup.sh claude

# 持久（取消.example 后缀即可生效；不进 git）
cp .skills-sync.env.example .skills-sync.env
# 编辑 .skills-sync.env，把 CLAUDE_DIR 改成你想要的路径
```

## 工作流

仓库内每个 skill 目录需有 `SKILL.md`（含 `name:` 和 `description:` frontmatter）。常见结构：

```
skills/
└── my-new-skill/
    ├── SKILL.md
    ├── references/
    └── assets/
```

进阶规范（命名约定、references、scripts、telemetry 等）按 `~/.workbuddy/skills/<android-skill-name>` 或 AndroidSkills 已有 skill 模板参考。
