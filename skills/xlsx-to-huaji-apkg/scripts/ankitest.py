#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ankitest.py —— 用 Anki 官方后端（无界面）真实导入 apkg 并渲染卡片，验证是否可用。

用法：
  PYTHONPATH=/Applications/Anki.app/Contents/Resources/app_packages \
  python ankitest.py 生成.apkg [--render N]

原理：借用 Anki.app 自带的 anki 后端（Rust 实现）建一个临时集合，导入 apkg，
      再调用 Anki 自己的卡片渲染引擎输出 HTML。渲染成功 = 打开即能用。
"""
import argparse, re, shutil, sys, tempfile
from pathlib import Path

try:
    from anki.collection import Collection
    from anki.import_export_pb2 import (ImportAnkiPackageOptions,
                                        ImportAnkiPackageRequest)
except ImportError:
    sys.exit("无法加载 Anki 后端。请设置 PYTHONPATH=/Applications/Anki.app/Contents/Resources/app_packages")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apkg", type=Path, nargs="+", help="一个或多个 apkg（按顺序导入同一集合）")
    ap.add_argument("--render", type=int, default=2, help="渲染前 N 张卡")
    args = ap.parse_args()
    args.apkg = list(args.apkg)

    tmp = Path(tempfile.mkdtemp(prefix="ankitest_"))
    col = Collection(str(tmp / "collection.anki2"))
    try:
        opts = ImportAnkiPackageOptions(
            with_scheduling=True,
            with_deck_configs=True,
            merge_notetypes=False,
        )
        for i, path in enumerate(args.apkg, 1):
            req = ImportAnkiPackageRequest(package_path=str(path), options=opts)
            out = col.import_anki_package(req)
            log = str(out.log)
            tail = [ln for ln in log.splitlines()
                    if ln.strip() and not ln.startswith(("new {", "  id {", "  }", "}", "    nid", "  fields:"))]
            print(f"[{i}/{len(args.apkg)}] {path.name} -> {' | '.join(tail[-2:])}")
            print(f"          当前集合：notes={col.note_count()} cards={col.card_count()} decks={col.decks.count()}")

        print(f"\n集合状态：notes={col.note_count()} cards={col.card_count()} "
              f"decks={col.decks.count()} notetypes={len(col.models.all_names_and_ids())}")
        print("\n牌组树：")
        for d in col.decks.all_names_and_ids():
            print("   ", d.name.replace("\x1f", " / "))

        cids = col.find_cards("")
        print(f"\n共 {len(cids)} 张卡，渲染前 {min(args.render, len(cids))} 张：")
        dumpdir = args.apkg[0].parent / (args.apkg[0].stem + "_渲染")
        dumpdir.mkdir(parents=True, exist_ok=True)
        for n, cid in enumerate(cids[:args.render], 1):
            card = col.get_card(cid)
            q = card.question()
            a = card.answer()
            (dumpdir / f"card{n}_正面.html").write_text(q, encoding="utf-8")
            (dumpdir / f"card{n}_背面.html").write_text(a, encoding="utf-8")
            for label, html_ in (("正面", q), ("背面", a)):
                body = html_.split("</style>", 1)[-1]
                body = re.sub(r"(?s)<script>.*?</script>", "", body)
                body = re.sub(r"\s+", " ", re.sub(r"(?s)<!--.*?-->", "", body)).strip()
                print("=" * 72)
                print(f"[card {cid}] {label} | deck={col.decks.name(card.did)}")
                print(body[:800])
        print("=" * 72)
        print(f"完整渲染 HTML 已保存到 {dumpdir}")
        print("结论：Anki 官方后端导入成功并完成渲染，包可用")
        return 0
    finally:
        col.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
