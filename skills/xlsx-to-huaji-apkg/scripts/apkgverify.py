#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apkgverify.py —— 校验生成的 apkg 结构是否合法、能否被 Anki 正常识别。
用法： python apkgverify.py 生成.apkg [--against 原apkg或collection.anki21b解出的sqlite]
"""
import argparse, hashlib, os, sqlite3, sys, tempfile, zipfile
from pathlib import Path
try:
    import zstandard as zstd
except ImportError:
    sys.exit("需要 zstandard")


def uc(a, b):
    return (a.casefold() > b.casefold()) - (a.casefold() < b.casefold())


def open_sqlite(path):
    p = Path(path)
    if p.suffix in (".apkg", ".colpkg"):
        with zipfile.ZipFile(p) as z:
            names = [i.filename for i in z.infolist()]
            if "collection.anki21b" in names:
                raw = zstd.ZstdDecompressor().decompress(z.read("collection.anki21b"), max_output_size=1 << 30)
            elif "collection.anki21" in names:
                raw = z.read("collection.anki21")
            else:
                raw = z.read("collection.anki2")
    else:
        raw = p.read_bytes()
        if raw[:4] == b"\x28\xb5\x2f\xfd":
            raw = zstd.ZstdDecompressor().decompress(raw, max_output_size=1 << 30)
    fd, tmp = tempfile.mkstemp(suffix=".sqlite")
    os.write(fd, raw); os.close(fd)
    con = sqlite3.connect(tmp)
    con.create_collation("unicase", uc)
    return con


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apkg", type=Path)
    ap.add_argument("--against", type=Path, help="原 apkg（比对笔记类型/字节）")
    args = ap.parse_args()

    ok = True
    def check(label, cond, extra=""):
        nonlocal ok
        print(f"  [{'通过' if cond else '不通过'}] {label} {extra}")
        if not cond:
            ok = False

    with zipfile.ZipFile(args.apkg) as z:
        infos = [(i.filename, i.compress_type) for i in z.infolist()]
        names = [n for n, _ in infos]
    print(f"包内条目：{infos}")
    check("包含 meta / collection.anki21b / media", set(names) >= {"meta", "collection.anki21b", "media"})
    if names and names[0] == "meta":
        with zipfile.ZipFile(args.apkg) as z:
            mv = int.from_bytes(z.read("meta")[1:2], "big") if len(z.read("meta")) > 1 else 0
        check("包格式版本为 3（新版 anki21b + zstd）", mv == 3, f"得到 {mv}")

    con = open_sqlite(args.apkg)
    ver = con.execute("select ver from col").fetchone()[0]
    check("collection 版本 = 18", ver == 18, f"得到 {ver}")

    n = con.execute("select count(*) from notes").fetchone()[0]
    c = con.execute("select count(*) from cards").fetchone()[0]
    check("notes 与 cards 数量一致", n == c, f"notes={n} cards={c}")
    check("无孤立卡片", con.execute("select count(*) from cards x left join notes y on y.id=x.nid where y.id is null").fetchone()[0] == 0)
    check("无悬空牌组", con.execute("select count(*) from cards x left join decks y on y.id=x.did where y.id is null").fetchone()[0] == 0)
    check("无重复 guid", con.execute("select count(*) from (select guid from notes group by guid having count(*)>1)").fetchone()[0] == 0)
    check("mid 均存在", con.execute("select count(*) from notes where mid not in (select id from notetypes)").fetchone()[0] == 0)
    check("无重复 note.id", con.execute("select count(*) from (select id from notes group by id having count(*)>1)").fetchone()[0] == 0)
    check("无重复 deck.id / 牌组名", con.execute("select count(*) from (select name from decks group by name having count(*)>1)").fetchone()[0] == 0)

    badc = [r for r in con.execute("select sfld,csum from notes")
            if int.from_bytes(hashlib.sha1(str(r[0]).encode()).digest()[:4], "big") != r[1]]
    check("csum 校验和正确", not badc, f"异常 {len(badc)} 条")

    flds_ok = con.execute("""select count(*) from notes
        where (length(flds)-length(replace(flds,char(31),'')))  <> 6""").fetchone()[0]
    check("每条笔记恰好 7 个字段", flds_ok == 0, f"异常 {flds_ok} 条")

    # 字段/选项/答案 交叉校验
    bad = []
    for flds, in con.execute("select flds from notes"):
        f = flds.split("\x1f")
        opts = f[4].split("|")
        ans = f[5]
        if len(opts) < 2 or not ans or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(opts)] for ch in ans):
            bad.append(f[0])
    check("选项与答案一一对应", not bad, f"异常 {len(bad)} 条 {bad[:5]}")

    print("  牌组树：")
    for _, name in con.execute("select id,name from decks order by id"):
        print("    " + name.replace("\x1f", " / "))

    if args.against and args.against.exists():
        ref = open_sqlite(args.against)
        for t in ("notetypes", "fields", "templates"):
            order = "id" if t == "notetypes" else "ntid,ord"
            a = ref.execute(f"select * from {t} order by {order}").fetchall()
            b = con.execute(f"select * from {t} order by {order}").fetchall()
            check(f"{t} 与壳包字节一致", a == b)
        refmap = {}
        dup = 0
        for (flds,) in ref.execute("select flds from notes"):
            k = flds.split("\x1f")[0]
            if k in refmap:
                dup += 1
            refmap[k] = flds
        same = diff = 0
        for (flds,) in con.execute("select flds from notes"):
            k = flds.split("\x1f")[0]
            if k in refmap and refmap[k] == flds:
                same += 1
            else:
                diff += 1
        if dup:
            print(f"  （原包首字段有 {dup} 条重复，比对按最后一条计）")
        print(f"  [{'通过' if diff == 0 else '提示'}] 笔记字段与原包逐字比对：一致 {same} 条，差异 {diff} 条")

    con.close()
    print("\n结论：" + ("生成包结构合法，可正常被 Anki / 滑记 识别" if ok else "存在问题，需修复"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
