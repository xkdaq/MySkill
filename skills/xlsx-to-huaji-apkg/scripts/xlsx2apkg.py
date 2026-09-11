#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xlsx2apkg —— 把 Excel 题库转成「滑记选择题模板」的 .apkg

做法：以现有 apkg 为「壳」，只替换 notes / cards / decks 数据，
      笔记类型、字段定义、CSS、模板、滑记 uuid、包内布局全部原样复用。

用法：
  python xlsx2apkg.py 题库.xlsx
  python xlsx2apkg.py 题库.xlsx --root "27米鹏720题·思修" --out out/思修.apkg
  python xlsx2apkg.py 题库.xlsx --sheet 题库 --limit 50
列名自动识别（不区分大小写）：
  ID / 题目 / 题型 / 选项A..选项Z 或 选项(用 | 分隔) / 答案 / 解析 / 出处
  一级目录 / 二级目录 / 三级目录 / 章节 / 牌组
"""

import argparse
import hashlib
import html
import os
import random
import re
import shutil
import sqlite3
import string
import sys
import tempfile
import time
import zipfile
from pathlib import Path

try:
    import zstandard as zstd
except ImportError:
    sys.exit("缺少 zstandard，请先 pip install zstandard")

HERE = Path(__file__).resolve().parent
DEFAULT_SHELL = HERE.parent / "26考研政治__26肖秀荣《1000题》.apkg"

DECK_SEP = "\x1f"
FLD_SEP = "\x1f"
GUID_CHARS = string.ascii_letters + string.digits + "!#$%&()*+,-./:;<=>?@[]^_`{|}~"


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- 工具函数

def strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"\[sound:[^\]]*\]", "", s)
    s = re.sub(r"(?is)<(br|/div|/p|/li|/tr)[^>]*>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def field_checksum(text: str) -> int:
    d = hashlib.sha1(text.encode("utf-8")).digest()
    return int.from_bytes(d[:4], "big")


def make_guid(used: set) -> str:
    while True:
        g = "".join(random.choice(GUID_CHARS) for _ in range(10))
        if g not in used:
            used.add(g)
            return g


def sel_kind(s: str):
    """判断题型语义：单选 / 多选 / 判断 / 不定项，用于避免重复分层。"""
    s = s or ""
    if "不定项" in s:
        return "indef"
    if "多选" in s or "多项" in s:
        return "multi"
    if "单选" in s or "单项" in s:
        return "single"
    if "判断" in s:
        return "judge"
    return None


EMBEDDED_OPT = re.compile(r"(?<![A-Za-z])([A-Z])[,，、．.]")

CJK_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cjk_to_int(s: str):
    """把中文/阿拉伯数字串转成 int：'21'->21，'十七'->17，'十'->10，'二'->2，认不出返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "十" in s:
        a, _, b = s.partition("十")
        return (CJK_NUM.get(a, 1) if a else 1) * 10 + (CJK_NUM.get(b, 0) if b else 0)
    return CJK_NUM.get(s)


# 「综合测试一」「阶段测试二」「模拟卷三」「强化练习四」这类"卷/测试 + 序数"命名
SERIES_RE = re.compile(
    r"^(综合测试|阶段测试|模拟测试|强化测试|模拟试题|模拟卷|测试卷|全真模拟"
    r"|综合练习|强化练习|练习|测试|试卷|试题|真题)"
    r"([一二三四五六七八九十\d]+)$"
)


def chapter_index(name: str):
    """从章节名推断排序序号：导论/绪论 -> 0，第X章/第X部分 -> X，综合测试X/模拟卷X -> X。

    Anki 牌组按名字排序，中文数字的字形顺序是乱的（一<七<三<二<五<六<四），
    所以必须补阿拉伯数字前缀，才能保证 第一章 → 第二章 → … 与
    综合测试一 → 综合测试二 → … 都按正确顺序排列。认不出返回 None。
    """
    n = (name or "").strip()
    if re.match(r"^(导论|绪论|前言|序言|总论|概论)", n):
        return 0
    m = re.match(
        r"^第([一二三四五六七八九十百\d]+)\s*"
        r"(?:[-–—~至]\s*第?([一二三四五六七八九十百\d]+)\s*)?"
        r"(章|部分|篇|编|节)",
        n,
    )
    if m:
        return cjk_to_int(m.group(1))
    m2 = SERIES_RE.match(n)
    if m2:
        return cjk_to_int(m2.group(2))
    return None


def repair_options(opts):
    """修复 Excel 粘贴错位：选项单元格里混入了后续选项。

    例：选项B = 「人的认识具有能动性C,理性认识是感性认识的基础」
        → 拆成 B=人的认识具有能动性、C=理性认识是感性认识的基础，
          并把该行后续选项统一前移一位重排字母。
    返回 (opts, 修复说明列表)
    """
    out, notes, repaired = [], [], False
    for letter, text in opts:
        cur, split = [(letter, text or "")], False
        changed = True
        while changed:
            changed = False
            nxt = []
            for l, t in cur:
                m = EMBEDDED_OPT.search(t)
                if m and m.group(1) > l:
                    nxt.append((l, t[:m.start()].strip()))
                    nxt.append((m.group(1), t[m.end():].strip()))
                    changed = split = True
                else:
                    nxt.append((l, t))
            cur = nxt
        if split:
            repaired = True
            notes.append(f"选项{letter} 单元格内混入了后续选项，已拆分")
        out.extend(cur)
    out = [(l, t) for l, t in out if t]
    if repaired:
        old = "".join(l for l, _ in out)
        out = [(chr(65 + i), t) for i, (_, t) in enumerate(out)]
        notes.append(f"本行选项字母重排：{old} -> {''.join(l for l, _ in out)}")
    return out, notes


def escape_bare_lt(s: str) -> str:
    """把不像标签起始的「<」转义，避免《<共产党人>发刊词》这类内容被当成标签吞掉。"""
    return re.sub(r"<(?![A-Za-z/!])", "&lt;", s)


def plain_to_html(text: str, keep_html: bool) -> str:
    if text is None:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    if keep_html:
        return escape_bare_lt(text).replace("\n", "<br>")
    lines = [html.escape(ln).replace("  ", "&nbsp;&nbsp;") for ln in text.split("\n")]
    return "<br>".join(lines)


def analysis_to_html(text: str, keep_html: bool) -> str:
    """解析：按行包 <p>，行首【标签】加粗，模仿滑记排版。"""
    if text is None:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    if keep_html:
        return escape_bare_lt(text) if "<p" in text.lower() else "<p>" + escape_bare_lt(text).replace("\n", "</p><p>") + "</p>"
    out = []
    for ln in text.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        esc = html.escape(ln).replace("  ", "&nbsp;&nbsp;")
        m = re.match(r"^([【\[]([^】\]]{1,8})[】\]])\s*(.*)$", esc)
        if m:
            out.append(f"<p><strong>{m.group(1)}</strong>{m.group(3)}</p>")
        else:
            out.append(f"<p>{esc}</p>")
    return "".join(out)


# ---------------------------------------------------------------- 读取 Excel

ALIAS = {
    "id": ["id", "编号", "题号", "序号"],
    "src": ["出处", "来源", "source", "教材", "书目"],
    "qtype": ["题型", "类型", "type", "题目类型"],
    "stem": ["题目", "题干", "问题", "question", "试题"],
    "answer": ["答案", "正确答案", "answer", "correct", "key"],
    "analysis": ["解析", "解答", "答案解析", "analysis", "考点解析", "详解", "分析"],
    "deck": ["牌组", "deck"],
    "d1": ["一级目录", "章节", "章", "板块", "科目"],
    "d2": ["二级目录", "小节", "节"],
    "d3": ["三级目录"],
    "tags": ["标签", "tags", "tag"],
}


def norm(s) -> str:
    return re.sub(r"[\s　]+", "", str(s if s is not None else "")).lower()


def read_rows(path: Path, sheet: str | None, keep_html: bool, tag: str = ""):
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if sheet and sheet in wb.sheetnames:
        ws = wb[sheet]
    else:
        ws = wb.worksheets[0]
        if sheet:
            log(f"  [{tag}] 未找到工作表「{sheet}」，改用「{ws.title}」")
    log(f"  [{tag}] 读取 {path.name} / {ws.title}（{ws.max_row} 行 x {ws.max_column} 列）")

    it = ws.iter_rows(values_only=True)
    header = None
    for row in it:
        if row and any(c is not None and str(c).strip() for c in row):
            header = [norm(c) for c in row]
            break
    if not header:
        sys.exit("表头为空")

    def find(key, exact_only=False):
        for i, h in enumerate(header):
            if h in ALIAS[key]:
                return i
        if not exact_only:
            for i, h in enumerate(header):
                for a in ALIAS[key]:
                    if len(a) >= 2 and a in h:
                        return i
        return None

    idx = {k: find(k) for k in ALIAS}
    # 选项列：选项A / 选项B / A / B
    opt_cols = []
    for i, h in enumerate(header):
        for pat in (r"^选项([a-z])$", r"^option([a-z])$", r"^([a-z])$"):
            m = re.match(pat, h)
            if m:
                opt_cols.append((m.group(1).upper(), i))
                break
    opt_cols.sort()
    pipe_col = next((i for i, h in enumerate(header) if h in ("选项", "options")), None)

    if idx["stem"] is None:
        sys.exit(f"找不到「题目」列，表头为：{header}")
    if idx["answer"] is None:
        sys.exit(f"找不到「答案」列，表头为：{header}")
    if not opt_cols and pipe_col is None:
        sys.exit(f"找不到选项列（选项A..选项E 或 选项），表头为：{header}")

    log(f"  [{tag}] 列映射：" + ", ".join(f"{k}={header[v]!r}" for k, v in idx.items() if v is not None)
        + (", 选项列=" + "".join(c for c, _ in opt_cols) if opt_cols else ", 选项=| 分隔"))

    records = []
    for n, row in enumerate(it, start=2):
        def get(key):
            i = idx.get(key)
            if i is None or i >= len(row) or row[i] is None:
                return ""
            return str(row[i]).strip()

        stem = get("stem")
        if not stem:
            continue
        if opt_cols:
            opts = [(c, str(row[i]).strip() if i < len(row) and row[i] is not None else "")
                    for c, i in opt_cols]
            opts = [(c, o) for c, o in opts if o]
        else:
            raw = str(row[pipe_col]).strip() if pipe_col < len(row) and row[pipe_col] is not None else ""
            opts = [(chr(65 + k), p.strip()) for k, p in enumerate(raw.split("|")) if p.strip()]

        opts, fixes = repair_options(opts)
        for fx in fixes:
            log(f"  [{tag}] 第 {n} 行：{fx}")

        if len(opts) < 2:
            log(f"  [{tag}] 跳过第 {n} 行：有效选项不足 2 个")
            continue

        letters = [c for c, _ in opts]
        answer = re.sub(r"[^A-Za-z]", "", get("answer")).upper()
        answer = "".join(sorted(set(answer)))
        bad = [ch for ch in answer if ch not in letters]
        if not answer or bad:
            log(f"  [{tag}] 跳过第 {n} 行：答案 {answer!r} 与选项 {letters} 不匹配")
            continue

        qtype = get("qtype")
        if not qtype:
            qtype = "多选题" if len(answer) > 1 else "单选题"

        records.append({
            "id": get("id") or f"{tag}-{len(records) + 1}",
            "src": get("src"),
            "qtype": qtype,
            "stem": plain_to_html(stem, keep_html),
            "options": "|".join(o for _, o in opts),
            "answer": answer,
            "analysis": analysis_to_html(get("analysis"), keep_html),
            "deck_path": [x for x in (get("d1"), get("d2"), get("d3")) if x],
            "deck": get("deck"),
            "tags": [t for t in re.split(r"[,\s，、]+", get("tags")) if t],
            "row": n,
        })
    wb.close()
    return records


# ---------------------------------------------------------------- 构建 apkg

def build(records, shell: Path, out: Path, root_deck: str, source_label: str,
          type_subdeck: bool, start_pos: int):
    tmp = Path(tempfile.mkdtemp(prefix="x2a_"))
    try:
        with zipfile.ZipFile(shell) as z:
            z.extractall(tmp)
        raw = zstd.ZstdDecompressor().decompress(
            (tmp / "collection.anki21b").read_bytes(), max_output_size=1 << 30)
        db = tmp / "c.anki2"
        db.write_bytes(raw)

        con = sqlite3.connect(db)
        con.create_collation("unicase", lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
        cur = con.cursor()

        ntid = cur.execute("select id from notetypes where name like '%滑记%'").fetchone()
        if not ntid:
            sys.exit("壳包里找不到「滑记选择题模板」笔记类型")
        ntid = ntid[0]
        fields = [r[0] for r in cur.execute("select name from fields where ntid=? order by ord", (ntid,))]
        log(f"笔记类型 id={ntid} 字段={fields}")
        if fields[:7] != ["ID", "出处", "题型", "题目", "选项", "答案", "解析"]:
            sys.exit(f"字段结构不符，实际为 {fields}")

        orig_scm, orig_crt = cur.execute("select scm, crt from col").fetchone()

        # ---- 清空数据
        for t in ("notes", "cards", "revlog", "graves", "tags"):
            cur.execute(f"delete from {t}")
        cur.execute("delete from decks")

        now_ms = int(time.time() * 1000)
        now_s = now_ms // 1000
        used_guid = set()
        deck_ids = {}
        deck_order = []
        tags_used = set()

        def ensure_deck(path_parts):
            if not path_parts:
                return 1
            full = DECK_SEP.join(path_parts)
            if full in deck_ids:
                return deck_ids[full]
            if len(path_parts) > 1:
                ensure_deck(path_parts[:-1])
            did = 1700000000000 + len(deck_order) * 7 + random.randint(0, 5)
            while did in deck_ids.values() or did == 1:
                did += 1
            deck_ids[full] = did
            deck_order.append((did, full))
            return did

        cur.execute("insert into decks(id,name,mtime_secs,usn,common,kind) values(?,?,?,?,?,?)",
                    (1, "Default", 0, 0, b"\x08\x01\x10\x01", b"\x0a\x02\x08\x01"))

        notes, cards = [], []
        nid_base = now_ms
        for i, r in enumerate(records):
            parts = [x for x in re.split(r"[/／]", root_deck) if x] if root_deck else []
            if r["deck"] and r["deck"] not in parts:
                parts.append(r["deck"])
            for p in r["deck_path"]:
                if p not in parts:
                    parts.append(p)
            if type_subdeck and r["qtype"] and r["qtype"] not in parts:
                # 末级目录已按题型分层（如「单项选择题」「多项选择题」）时不重复加一层
                if sel_kind(parts[-1]) != sel_kind(r["qtype"]):
                    parts.append(r["qtype"])
            did = ensure_deck(parts)

            flds = FLD_SEP.join([
                r["id"], r["src"] or source_label, r["qtype"],
                r["stem"], r["options"], r["answer"], r["analysis"],
            ])
            sfld = strip_html(r["id"]) or r["id"]
            nid = nid_base + i
            tags = " ".join(r["tags"])
            tags_used.update(r["tags"])
            notes.append((nid, make_guid(used_guid), ntid, now_s, -1, tags,
                          flds, sfld, field_checksum(sfld), 0, ""))
            cards.append((nid, nid, did, 0, now_s, -1, 0, 0, start_pos + i,
                          0, 0, 0, 0, 0, 0, 0, 0, "{}"))

        cur.executemany(
            "insert into notes(id,guid,mid,mod,usn,tags,flds,sfld,csum,flags,data) "
            "values(?,?,?,?,?,?,?,?,?,?,?)", notes)
        cur.executemany(
            "insert into cards(id,nid,did,ord,mod,usn,type,queue,due,ivl,factor,reps,lapses,left,odue,odid,flags,data) "
            "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", cards)

        for t in sorted(tags_used):
            cur.execute("insert or replace into tags(tag,usn,collapsed,config) values(?,?,?,?)",
                        (t, -1, 0, None))

        cur.executemany(
            "insert into decks(id,name,mtime_secs,usn,common,kind) values(?,?,?,?,?,?)",
            [(did, name, now_s, -1, b"", b"\x0a\x02\x08\x01") for did, name in deck_order])

        cur.execute("update col set mod=?, scm=?", (now_ms, orig_scm))
        cur.execute("insert or replace into config(KEY,usn,mtime_secs,val) values('nextPos',0,0,?)",
                    (str(start_pos + len(records) + 1).encode(),))
        con.commit()
        cur.execute("vacuum")
        con.commit()

        cnt_n = cur.execute("select count(*) from notes").fetchone()[0]
        cnt_c = cur.execute("select count(*) from cards").fetchone()[0]
        cnt_d = cur.execute("select count(*) from decks").fetchone()[0]
        log(f"写库完成：{cnt_n} 条笔记 / {cnt_c} 张卡片 / {cnt_d} 个牌组")
        con.close()

        # ---- 重新打包
        out.parent.mkdir(parents=True, exist_ok=True)
        packed = zstd.ZstdCompressor(level=19).compress(db.read_bytes())
        meta = (tmp / "meta").read_bytes()
        stub = (tmp / "collection.anki2").read_bytes()
        media = (tmp / "media").read_bytes()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
            z.writestr("meta", meta)
            z.writestr("collection.anki21b", packed)
            z.writestr("collection.anki2", stub)
            z.writestr("media", media)
        log(f"生成：{out}  ({out.stat().st_size/1024:.0f} KB, 原始壳 {shell.stat().st_size/1024:.0f} KB)")
        return deck_ids
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path, nargs="+", help="Excel/CSV 题库，可给多个（合并为一个 apkg）")
    ap.add_argument("--shell", type=Path, default=DEFAULT_SHELL, help="作为壳的 apkg")
    ap.add_argument("--out", type=Path, help="输出 apkg 路径")
    ap.add_argument("--sheet", help="工作表名（默认第一个；某个文件没有该表时自动退回第一个）")
    ap.add_argument("--root", help="根牌组名（默认用第一个文件名；传空串 \"\" 表示不要根牌组，一级目录直接当顶层）")
    ap.add_argument("--order", help="指定一级目录（科目）的固定顺序，逗号分隔，会加 01./02. 前缀"
                                   "；例：--order \"马原,毛中特,新思想,史纲,思修\"")
    ap.add_argument("--pad-intro", "--number-chapters", dest="number_chapters", action="store_true",
                    help="给章节加排序序号：导论/绪论 -> 00.，第X章 -> 01./02./…（Anki 按名字排序，"
                         "中文数字字形顺序是乱的，必须补阿拉伯数字前缀）")
    ap.add_argument("--source", default="",
                    help="出处默认值；多文件时支持 {name}（文件名）/{sub}（去掉序号的文件名）占位符")
    ap.add_argument("--no-type-subdeck", action="store_true", help="不按题型再分子牌组")
    ap.add_argument("--start-pos", type=int, default=1, help="新卡排序位置起点")
    ap.add_argument("--limit", type=int, help="只取前 N 题")
    ap.add_argument("--keep-html", action="store_true", help="题目/解析已含 HTML，原样透传")
    args = ap.parse_args()

    if not args.shell.exists():
        sys.exit(f"壳包不存在：{args.shell}")

    files = list(args.xlsx)
    for p in files:
        if not p.exists():
            sys.exit(f"题库文件不存在：{p}")

    root = args.root if args.root is not None else files[0].stem
    out = args.out or (HERE.parent / "out" / f"{root or files[0].stem}.apkg")

    order_map = {}
    if args.order:
        for i, nm in enumerate((x.strip() for x in args.order.split(",") if x.strip()), 1):
            order_map[nm] = f"{i:02d}.{nm}"

    def subject_of(p: Path) -> str:
        return re.sub(r"^\d+\s*[.\-、_]\s*", "", p.stem).strip() or p.stem

    def label_of(p: Path) -> str:
        if args.source:
            try:
                return args.source.format(name=p.stem, sub=subject_of(p))
            except (KeyError, IndexError, ValueError):
                return args.source
        return subject_of(p) if len(files) > 1 else root

    recs = []
    for p in files:
        sub = subject_of(p)
        got = read_rows(p, args.sheet, args.keep_html, tag=sub)
        label = label_of(p)
        for r in got:
            if not r["src"]:
                r["src"] = label
            dp = r["deck_path"]
            if dp and dp[0] in order_map:
                dp[0] = order_map[dp[0]]
            if args.number_chapters and len(dp) > 1 and not re.match(r"^\d+\.", dp[1]):
                idx = chapter_index(dp[1])
                if idx is not None:
                    dp[1] = f"{idx:02d}." + dp[1]
        log(f"  [{sub}] 有效 {len(got)} 道（出处：{label}）")
        recs.extend(got)

    if args.limit:
        recs = recs[:args.limit]
    if not recs:
        sys.exit("没有解析出任何有效题目")

    log(f"合并完成：{len(files)} 个文件 -> {len(recs)} 道题；"
        f"单选题 {sum(1 for r in recs if r['qtype']=='单选题')}，"
        f"多选题 {sum(1 for r in recs if r['qtype']=='多选题')}")
    build(recs, args.shell, out, root, root, not args.no_type_subdeck, args.start_pos)
    print(out)


if __name__ == "__main__":
    main()
