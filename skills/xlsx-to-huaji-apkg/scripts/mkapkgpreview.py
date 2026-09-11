#!/usr/bin/env python3
"""从 .apkg 生成独立的效果预览 HTML（牌组树 + 科目分布 + 样题）。

用法：
    python tools/mkapkgpreview.py out/结果.apkg --title "标题" --out out/预览.html
    python tools/mkapkgpreview.py out/结果.apkg --out out/预览.html --samples 6

依赖：openpyxl / zstandard（读取用），无其它外部依赖。
"""
from __future__ import annotations

import argparse
import html
import pathlib
import sqlite3
import zipfile

import zstandard as zstd

FLD = "\x1f"


def _unicase(a: str, b: str) -> int:
    return (a.casefold() > b.casefold()) - (a.casefold() < b.casefold())


def load_collection(apkg: pathlib.Path) -> sqlite3.Connection:
    with zipfile.ZipFile(apkg) as z:
        raw = z.read("collection.anki21b")
    db_bytes = zstd.ZstdDecompressor().decompress(raw, max_output_size=512 * 1024 * 1024)
    tmp = pathlib.Path("/tmp") / f"_prev_{apkg.stem}.db"
    tmp.write_bytes(db_bytes)
    con = sqlite3.connect(tmp)
    con.create_collation("unicase", _unicase)
    return con


def _tree_html(node: dict) -> list[str]:
    out = []
    for k in sorted(node.keys()):
        out.append(f"<li>{html.escape(k)}")
        if node[k]:
            out.append("<ul>")
            out.extend(_tree_html(node[k]))
            out.append("</ul>")
        out.append("</li>")
    return out


def _card_html(c: dict) -> str:
    opts = "".join(
        f'<li><span class="letter">{chr(ord("A") + i)}.</span> {html.escape(o)}</li>'
        for i, o in enumerate(c["opts"])
    )
    expl = html.escape(c["expl"]).replace("\\n", "<br>")
    for tag in ("【识记点】", "【解题思路】", "【干扰选项】", "【考点】", "【解析】"):
        expl = expl.replace(tag, f"<b>{tag}</b>")
    return f"""
<div class="card">
<div class="meta">
    <span class="qid">#{html.escape(c["id"])}</span>
    <span class="qtype">{html.escape(c["qtype"])}</span>
    <span class="src">{html.escape(c["src"])}</span>
</div>
<div class="stem">{html.escape(c["stem"])}</div>
<ul class="opts">{opts}</ul>
<div class="answer"><span class="ans-label">正确答案</span>
    <span class="ans-value">{html.escape(c["ans"])}</span></div>
<details><summary>解析</summary><div class="expl">{expl}</div></details>
</div>"""


CSS = """body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;
max-width:1100px;margin:0 auto;padding:32px 24px;color:#1f2329;background:#fafbfc}
h1{font-size:28px;margin:0 0 8px}
h2{font-size:20px;margin:32px 0 12px;border-bottom:2px solid #07c160;padding-bottom:6px}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}
.cell{background:#fff;padding:14px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.cell .num{font-size:28px;color:#07c160;font-weight:600}
.cell .lbl{font-size:13px;color:#8f959e}
ul.tree,ul.tree ul{list-style:none;padding-left:16px;border-left:1px dashed #dde2e8;font-size:13px}
ul.tree li{margin:4px 0;line-height:1.7}
table.summary-table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}
table.summary-table th,table.summary-table td{text-align:left;padding:8px 12px;border-bottom:1px solid #ebeef5}
table.summary-table th{background:#f7f8fa;color:#4e5969}
.card{background:#fff;padding:16px 20px;border-radius:10px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.card .meta{display:flex;gap:10px;align-items:center;font-size:12px;margin-bottom:8px}
.card .qid{color:#8f959e}
.card .qtype{background:#07c160;color:#fff;padding:2px 8px;border-radius:4px}
.card .src{color:#4e5969}
.card .stem{font-size:15px;line-height:1.7;margin:10px 0}
.card .opts{list-style:none;padding:0;margin:8px 0}
.card .opts li{padding:6px 8px;margin:2px 0;font-size:14px;line-height:1.6}
.card .opts li .letter{display:inline-block;width:20px;color:#07c160;font-weight:600}
.card .answer{padding:8px 12px;background:#f0fff5;border-radius:6px;margin:8px 0}
.card .answer .ans-label{color:#8f959e;font-size:13px}
.card .answer .ans-value{color:#07c160;font-weight:600;font-size:18px;margin-left:8px}
.card details{font-size:13px;color:#4e5969}
.card details summary{cursor:pointer;color:#07c160}
.card details .expl{padding:8px 12px;background:#f7f8fa;border-radius:6px;margin-top:8px;line-height:1.7}
pre.param{background:#f7f8fa;padding:12px;border-radius:6px;font-size:12px;overflow-x:auto}"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("apkg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--samples", type=int, default=8, help="样题数量（每科抽 1 张 + 补多选）")
    ap.add_argument("--root-hint", default=None, help="根牌组名提示（仅用于显示）")
    args = ap.parse_args()

    apkg = pathlib.Path(args.apkg)
    con = load_collection(apkg)
    cur = con.cursor()

    deck_names = [r[0] for r in cur.execute("SELECT name FROM decks")]
    tree: dict = {}
    for name in deck_names:
        node = tree
        for seg in name.split(FLD):
            node = node.setdefault(seg, {})

    cards = []
    for (f,) in cur.execute("SELECT flds FROM notes"):
        p = f.split(FLD)
        if len(p) < 7:
            continue
        cards.append(
            dict(id=p[0], src=p[1], qtype=p[2], stem=p[3],
                 opts=p[4].split("|"), ans=p[5], expl=p[6])
        )

    qtypes: dict = {}
    src_counts: dict = {}
    for c in cards:
        qtypes[c["qtype"]] = qtypes.get(c["qtype"], 0) + 1
        src_counts[c["src"]] = src_counts.get(c["src"], 0) + 1

    # 样题：每个科目各抽 1 张，再补若干张多选凑够
    samples: list[dict] = []
    for src_name in src_counts:
        for c in cards:
            if c["src"] == src_name and c not in samples:
                samples.append(c)
                break
        if len(samples) >= args.samples:
            break
    for c in cards:
        if len(samples) >= args.samples:
            break
        if c not in samples:
            samples.append(c)

    title = args.title or apkg.stem
    src_rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v}</td>"
        f"<td>{v / max(1, len(cards)) * 100:.1f}%</td></tr>"
        for k, v in sorted(src_counts.items(), key=lambda x: -x[1])
    )

    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>{html.escape(title)} 效果预览</title><style>{CSS}</style></head><body>
<h1>{html.escape(title)} · 效果预览</h1>
<p>源包: <code>{html.escape(str(apkg))}</code> · {len(cards)} 题 / {len(deck_names)} 牌组 / {apkg.stat().st_size // 1024} KB
{"<br>根牌组: <code>" + html.escape(args.root_hint) + "</code>" if args.root_hint else ""}</p>
<div class="summary">
<div class="cell"><div class="num">{len(cards)}</div><div class="lbl">总题数</div></div>
<div class="cell"><div class="num">{len(deck_names)}</div><div class="lbl">牌组数</div></div>
<div class="cell"><div class="num">{qtypes.get("单选题", 0)}</div><div class="lbl">单选题</div></div>
<div class="cell"><div class="num">{qtypes.get("多选题", 0)}</div><div class="lbl">多选题</div></div>
</div>
<h2>科目分布（按「出处」字段）</h2>
<table class="summary-table"><tr><th>出处</th><th>题数</th><th>占比</th></tr>{src_rows}</table>
<h2>牌组结构</h2>
<ul class="tree">{"".join(_tree_html(tree))}</ul>
<h2>样题预览（共 {len(samples)} 题）</h2>
{"".join(_card_html(c) for c in samples)}
</body></html>"""

    pathlib.Path(args.out).write_text(page, encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
