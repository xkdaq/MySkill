---
name: xlsx-to-huaji-apkg
description: 把 Excel 选择题题库转成「滑记选择题模板」的 .apkg（Anki 卡包）。当用户提供 Excel/xlsx/csv 题库并要生成 apkg、导入滑记 App、做选择题卡包时使用。触发词：Excel 转 apkg、题库转 apkg、生成 apkg、滑记卡包、Anki 卡包、选择题导入滑记。
agent_created: true
---

# Excel 题库 → 滑记选择题 apkg

## 适用场景
- 手上有一份**选择题**题库 Excel（题干 + 选项 + 答案 + 解析），想批量生成 .apkg 导入滑记 App 背题。
- 目标模板是滑记的「1.滑记选择题模板」（7 字段：ID / 出处 / 题型 / 题目 / 选项 / 答案 / 解析）。

## 核心思路：以现有 apkg 为「壳」，只换数据
不要从零拼 collection.anki2。新版 apkg 是 **schema 18 + zstd**，直接从零构造极易踩坑。

正确做法是把一个已知能用的 apkg 当模板壳：
1. 解压 → `collection.anki21b` 是 zstd 压缩的 SQLite（`meta` = `0803`，即包格式 v3）。
2. 解压后**只替换** `notes` / `cards` / `decks` / `tags` 表数据。
3. `notetypes` / `fields` / `templates` / `deck_config` / `config` 原样保留 → 模板、CSS、字段定义、滑记 UUID 全部零改动。
4. 重新 zstd 压缩 → 按 `meta, collection.anki21b, collection.anki2, media` 顺序、**全部 STORED（不压缩）** 写 zip。

## 必须记住的坑（都踩过）
- **`fields` / `templates` / `decks` / `deck_config` / `tags` 表带 `COLLATE unicase`**，sqlite3 连接必须 `create_collation("unicase", lambda a,b: (a.casefold()>b.casefold())-(a.casefold()<b.casefold()))`，否则任何查询/建索引都报 `no such collation sequence: unicase`。
- **`notes.csum`** = 首字段文本的 SHA1 前 4 字节 **大端** 整数（`int.from_bytes(sha1(text)[:4],'big')`），不是自研校验和。
- **`cards.due`** 对新卡就是「排序位置」，用连续整数（如 1..n）即可；同时把 `config` 表 `nextPos` 更新为 n+1。
- **新建行的 `usn` 用 -1**（表示待同步）。
- **`col` 表的 `conf` / `models` / `decks` / `dconf` / `tags` 在 schema 18 全是空串**，数据在独立表里；`col.ver` 必须 = 18。
- **`notes.flds` 用 `\x1f` 分隔成 7 段**；`cards.id` 可以等于 `notes.id`（原包就这么干）。
- **牌组名用 `\x1f` 拼多层路径**（`科目\x1f章节\x1f题型`），不是 `::`；写入时按 `\x1f`，Anki 显示时自动变 `::`。
- **末级题型别重复分层**：Excel 二级目录写「单项选择题」时不要再加一层「单选题」——判断要按语义（'单选'/'单项' → single），不能直接子串匹配。
- **选项列映射**：滑记模板的「选项」字段是 `选项1|选项2|选项3|选项4`，**不带 A/B/C/D 前缀**；模板里的 JS `createOptionDivs` 会自动加 `A. ` 前缀并把首字符写进 `value`。答案字段就是 `ABC` 这样的字母串。

## 执行流程
```bash
PY=/Users/xuke/.workbuddy/binaries/python/envs/default/bin/python   # 需要 openpyxl + zstandard

# 1) 生成（auto 识别表头）
$PY tools/xlsx2apkg.py 题库.xlsx --shell 参考.apkg --root "27米鹏720题·思修" \
    --source "27米鹏720题·思修" --sheet 思修720题 --out out/结果.apkg
# 常用开关：--no-type-subdeck 不按题型分层 / --limit N 试跑 / --keep-html 题库已含 HTML

# 2) 结构与整性校验（必做）
$PY tools/apkgverify.py out/结果.apkg --against 参考.apkg
```

**多文件合并成一个包**：直接给多个 xlsx 即可。`--source` 支持 `{name}`（文件名）/`{sub}`（去掉开头序号的文件名）占位符，这样每个文件能有自己的「出处」。

```bash
$PY tools/xlsx2apkg.py 题库/01.马原.xlsx 题库/02.毛中特.xlsx 题库/03.新思想.xlsx \
    题库/04.史纲.xlsx 题库/05.思修.xlsx \
    --sheet 模板 --root "27肖秀荣1000题" --source "27版肖秀荣《1000题》·{sub}" \
    --keep-html --out out/合集.apkg
```
共用同一个 `--root` 时，各文件的一级目录会挂在同一个根下面（`根/科目/章节/题型`），所以「分开发」和「合并成一个」产出的牌组树结构完全一致，只是包的数量不同。

```bash
# 3) 用 Anki 官方后端真实导入 + 渲染（最硬核的验证）
PYTHONPATH=/Applications/Anki.app/Contents/Resources/app_packages \
  $PY tools/ankitest.py out/结果.apkg --render 1
# 多个包可一次性传入，验证「多个 apkg 导入同一集合能否合并成一棵树」：
PYTHONPATH=... $PY tools/ankitest.py out/*.apkg --render 1
```
`ankitest.py` 借用 Anki.app 自带的 Rust 后端（`anki/_rsbridge.so`，cpython-313，可直接用 3.13 解释器加载）在临时目录建集合导入，再调 `card.question()/card.answer()` 拿真实渲染 HTML——**不需要开 GUI**。这是判断「包能不能用」的最快办法。

```bash
# 4) 生成独立的效果预览 HTML（牌组树 + 科目分布 + 样题）——给用户看结果用
$PY tools/mkapkgpreview.py out/结果.apkg --title "XX题库合集" \
    --root-hint "27考研政治/27徐涛《优题库·基础篇》" --out out/结果_效果预览.html
# --samples N 控制样题数量（默认 8：每科目各 1 张 + 补多选）
```

## Excel 表头（自动识别，不区分大小写）
| 字段 | 可接受的列名 |
|---|---|
| ID | ID / 编号 / 题号 / 序号（没有则自动编号） |
| 出处 | 出处 / 来源 / source / 教材 |
| 题型 | 题型 / 类型 / type（缺省按答案位数推） |
| 题目 | 题目 / 题干 / 问题 / question |
| 选项 | 选项A..选项Z 或 OptionA..Z，或一列「选项」用 `\|` 分隔 |
| 答案 | 答案 / 正确答案 / answer / key |
| 解析 | 解析 / 答案解析 / analysis / 详解 |
| 目录 | 一级目录 / 二级目录 / 三级目录 / 章节 / 小节 → 自动建多层牌组 |
| 牌组 | 牌组 / deck（精确匹配，作为根牌组下的第一层） |
| 标签 | 标签 / tags |

## 牌组层级与排序（照抄原包的约定）
原包 `26考研政治__26肖秀荣《1000题》.apkg` 的真实层级是 **5 层**：
`26考研政治 / 26肖秀荣《1000题》 / 01.马原 / 00.导论 马克思主义是… / 单选题|多选题`
即 **书名一层不能省**，且科目与章都带阿拉伯数字前缀。生成时要对齐：

| 层 | 内容 | 命令开关 |
|---|---|---|
| 1 | 书名（如 `27肖秀荣1000题`） | `--root "27肖秀荣1000题"`（多级用 `/` 分隔） |
| 2 | 科目 `01.马原` `02.毛中特` `03.新思想` `04.史纲` `05.思修` | `--order "马原,毛中特,新思想,史纲,思修"` |
| 3 | 章 `00.导论` `01.第一章` … `17.第十七章` | `--number-chapters` |
| 4 | 题型 `单选题` / `多选题` | 由「三级目录」列自动生成 |

- **章必须补阿拉伯数字前缀**：Anki 牌组按名字排序，中文数字字形顺序是乱的（一<七<三<二<五<六<四），不补前缀会排成「第一章→第七章→第三章→第二章…」。`--number-chapters` 会识别并补前缀的三类命名：
  - `导论/绪论/前言/序言/总论/概论` → `00.`
  - `第X章/第X部分/第X篇/第X编/第X节`（支持「第十七章」→17、「第二十一章」→21），**连续章也支持**：「第六-七章」→ `06.`、「第八-九章」→ `08.`（取起始数字）
  - `综合测试X / 阶段测试X / 模拟测试X / 模拟卷X / 测试卷X / 综合练习X / 全真模拟X / 真题X / 练习X / 测试X / 试卷X / 试题X` → `0X.`
- **科目也要带序号**，否则排序变成「史纲/思修/新思想/毛中特/马原」。用 `--order` 显式给定顺序，比依赖文件名可靠。**注意 `--order` 是拿 d1 列的值去匹配的**——如果 Excel 的「一级目录」列装的是章节名而不是科目名（科目只写在文件名里），`--order` 会完全落空，科目层根本不会出现在牌组树里。这种情况见下面的「科目只存在于文件名」一节。
- `--root ""`（空串）表示不要书名层——一般不要这么做，除了要跟原包做逐层对照。

### 科目只存在于文件名时（常见坑）

很多题库把一个科目切一个文件（`01.马原.xlsx` … `05.思修.xlsx`），文件内部的「一级目录」列直接是**章节名**（「导论 …」「第一章 …」）。此时直接跑 skill 会得到 4 层结构 `书名/章/题型`，**科目层缺失**，而且 `--order`、`--number-chapters` 都作用不到正确层次。

**修法：先用临时脚本把「科目」注入第 1 层目录，把原来的目录依次降级**，再交给 skill：

```python
import openpyxl, shutil
from pathlib import Path

src_dir = Path('题库目录'); tmp = Path('/tmp/inject_v2')
shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()

# 文件名 → 科目名，按业务口径映射（不要猜，问用户或看文件序号约定）
mapping = [('01.马原.xlsx', '马原'), ('02.毛中特.xlsx', '毛中特'), ('03.新思想.xlsx', '新思想'),
           ('04.史纲.xlsx', '史纲'), ('05.思修.xlsx', '思修')]

for fname, subject in mapping:
    wb = openpyxl.load_workbook(src_dir / fname); ws = wb.active
    rows = list(ws.iter_rows(values_only=True)); hdr, body = list(rows[0]), rows[1:]
    d1, d2 = hdr.index('一级目录'), hdr.index('二级目录')
    new_body = []
    for r in body:
        r = list(r); old_d1, old_d2 = r[d1], r[d2]
        r[d1], r[d2] = subject, old_d1          # 科目 → d1，原目录 → d2
        new_body.append(r + [old_d2])            # 原二级目录 → d3（新增列）
    out = tmp / f'{subject}.xlsx'
    w2 = openpyxl.Workbook(); ws2 = w2.active; ws2.title = ws.title
    ws2.append(list(hdr) + ['三级目录'])
    for r in new_body: ws2.append(r)
    w2.save(out)
```

然后正常跑 skill，`--root "书名/分册"`、`--order "马原,毛中特,新思想,史纲,思修"`、`--number-chapters` 就都会各就各位。产出结构与「基础篇」那种科目清晰的包**逐层同构**。

> 反例警示：`27徐涛优题库/强化篇/` 的 5 个文件叫 `强化01.xlsx`…`强化05.xlsx`，文件名里没科目，但用户口径是「强化01-05 依次还是 马原、毛中特、新思想、史纲、思修」——即**文件序号本身编码了科目**。这类要跟用户确认映射关系，不能按文件名猜。

## 数据缺陷自动修复（内置）
题库 Excel 常带两类提取残留，脚本会自动处理并打印修了什么，**不改动源文件**：

1. **选项粘贴错位**：上一选项单元格里混入了下一个选项的文字，且带字母标记。
   例 `选项B = 「人的认识具有能动性C,理性认识是感性认识的基础」`
   → 拆成 `B=人的认识具有能动性`、`C=理性认识是感性认识的基础`，并把该行后续选项整体前移重排字母（日志显示 `ABCC -> ABCD`）。
   只在该行确实发生拆分时才重排，避免误伤本来就跳字母的表。
2. **裸尖括号**：`《<共产党人>发刊词》` 这类内容里的 `<` 在 `--keep-html` 下会被当成标签起始，自动转义为 `&lt;`。

生成前建议先体检，确认没有会被跳过的行：
- 答案字母超出实际选项范围
- 选项列中间空列（如只填了 A、C 没填 B）
- 题型与答案位数冲突（单选却多答案、多选却单答案）

## 硬限制（要提前告知用户）
1. **只支持选择题**。滑记这个模板的判定逻辑依赖选项，问答题/名词解释塞进去会显示异常——那类内容需要另一套「问答题模板」的壳。
2. **图片/音频不支持**：`media` 目前原样复制空映射，Excel 里的 `<img src="x.jpg">` 不会带图。要带图得额外把文件写进包并按 `media` JSON 建映射。
3. **交互判定依赖滑记 App**：模板 JS 调 `HuajiJS.AnkiDroidJS.showAnswer()`，`HuajiJS` 是滑记注入的桥。在**纯 Anki / AnkiDroid 里卡片能正常渲染和翻面，但点选项不会自动揭示答案**（会抛 ReferenceError）。要兼容 AnkiDroid 需把脚本换成 `AnkiDroidJS` / `pycmd('ans')`。
4. **版权**：真题搬运是长期风险点，生成前提醒一句。
