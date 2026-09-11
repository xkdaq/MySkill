---
name: exam-paired-pdf-to-excel
agent_created: true
description: Process paired exam question PDF and answer PDF (e.g. 米鹏720题-style books split into 科目.pdf + 科目答案.pdf) into a standardized Excel question bank matching the exam-processor template. Use when the user uploads two PDFs where one contains questions with options and the other contains answer letters plus explanations.
---

# 成对考试 PDF → Excel 题库

## 适用场景

- 用户上传两个 PDF：`<科目>.pdf`（题目+选项）和 `<科目>答案.pdf`（题号+答案字母+考点+解析）。
- 典型来源：考研政治模拟题丛书（如米鹏《考研政治全真模拟720题》按模块拆分的 史纲/思修/马原/毛中特 等）。
- 输出：符合 exam-processor 模板字段的 `.xlsx`（ID/题目/题型/分数/难度/选项A-E/答案/解析/一级目录/二级目录），并追加「章节」列方便按章筛选。

## 处理流程

1. **确认文件结构**
   - 题目 PDF 应按「第X章」→「一、单项选择题」/「二、多项选择题」→「N．题干」→「A．/B．/C．/D．选项」组织。
   - 答案 PDF 与题目 PDF 章/节/题号完全对应，每题以 `N．X`（X 为答案字母）开头，后接「考点」「解析」「刷题笔记」「真题思维」等块。

2. **提取文本**
   - 使用 PyMuPDF (`fitz`) 的 `page.get_text("text")` 提取文本，保留换行以便按行解析。
   - 环境要求：managed Python venv（`/Users/xuke/.workbuddy/binaries/python/envs/default`）已安装 `PyMuPDF pandas openpyxl`；如缺失则在该 venv 内安装。

3. **解析题目（parse_questions）**
   - 章标题：行首匹配 `^第[一二三四五六七八九十]+章`，长度不超过 40 字，且不含「刷题笔记」「详见」「解析」「考点」「题刷」等词，防止解析段内回指章号（如「详见第三章单选第2题」）被误判。
   - 题型节：匹配 `^[一二三四]、\s*(单项选择|多项选择)题`；检测到节标题后设置 `between=True`，在下一题号出现前不再把后续行追加到上一题的选项/题干。
   - 题号：匹配 `^(\d+)\s*[．.\u3002]`。
   - 选项：先 `strip()` 行首全角空格等，再匹配 `([A-Ea-e])\s*[．.\u3002]`；支持一行内多个选项标记（如 `C．...D．...`）按标记切分。
   - 记录每个 `(章号, 题号)` 的题干、四个选项、题型。

4. **解析答案（parse_answers）**
   - 同样的章/节识别逻辑；节标题出现时 `flush` 当前答案缓冲区，避免「多选、少选或错选均不得分」等节标题续行混入上一题解析。
   - 每题答案入口：`^(\d+)\s*[．.\u3002]\s*([A-Ea-e]+)`，提取答案字母。
   - 解析内容：从答案入口后到下一题/节/章之间的全部文本（含考点、解析、刷题笔记、真题思维），整段作为「解析」列。

5. **配对与校验**
   - 以 `(章号, 题号)` 为键合并题目与答案。
   - 校验：题目数与答案数一致；单选答案 1 个字母，多选 2-4 个字母；每题均有 4 个选项。

6. **生成 Excel（build_excel）**
   - 按 `(章号, 题号)` 排序，生成全局 `ID`。
   - 题型列：单选题 / 多选题；二级目录列保留原始「单项选择题 / 多项选择题」。
   - 一级目录示例：`27考研政治·米鹏720题（中国近现代史纲要）`，按实际科目调整。
   - 追加「章节」列：`第X章 <章标题>`。
   - 设置表头样式（主题色 #07C160）、自动换行、冻结首行。

## 常见陷阱

- **章号漂移**：答案 PDF 的解析段可能提到「第三章单选第2题」，必须用行首锚定+关键词排除，否则会把后续题号归到错误章节。
- **选项粘连**：部分排版把两个选项挤在同一行（`C．...D．...`），需按选项标记切分。
- **全角空格选项**：选项行可能以 `\u3000D．...` 开头，匹配前必须 `strip`。
- **节标题续行**：「二、多项选择题（...多选、少选或错选均不得分。）」可能折成两行，第二节标题行会混入上一题选项/解析，需在检测到节标题后停止追加并 flush 缓冲区。

## 脚本

- `scripts/parse_fixed.py`：题目/答案解析器，输出 `(questions, answers, chap_titles)` 三元组到 pickle。
- `scripts/build_excel.py`：读取 pickle 生成 Excel。

使用时把脚本复制到目标目录，修改脚本内的文件名与「一级目录」字符串，依次运行：

```bash
python parse_fixed.py
python build_excel.py
```

## 审查清单

生成 Excel 后，与原 PDF 做一致性检查：
- 行数是否等于 PDF 总题数。
- 随机抽样 10~20 题，核对题干、四个选项、答案字母、解析开头是否与 PDF 一致。
- 检查是否有题干混入选项、节标题混入题干/解析、选项缺失或合并等异常。
