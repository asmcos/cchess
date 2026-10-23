#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计标准开局前 20 步的主变分叉，每层只留局数最多的 10 种。

写出 web/move-tree.json（只有第一步）和 web/move-parts/。
点开第一步先取到第十步；点到第十步再取第十一到第十五步；
点到第十五步再取第十六到第二十步。
网页在同一页里点开下一层，不另开页面。
"""
import json
import os
import time
from multiprocessing import Pool

from build_cat import _WORKERS, all_games, line_from_v10

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "web", "move-tree.json")
PARTS = os.path.join(ROOT, "web", "move-parts")
DEPTH = 20
TAIL_AT = 10
LATE_AT = 15
KEEP = 10
NUM = "零一二三四五六七八九"
PIECE = {
    1: "车", 2: "马", 3: "相", 4: "仕", 5: "帅", 6: "炮", 7: "兵",
    8: "车", 9: "马", 10: "象", 11: "士", 12: "将", 13: "炮", 14: "卒",
}


def standard_board():
    board = [0] * 90
    for col, code in enumerate((1, 2, 3, 4, 5, 4, 3, 2, 1)):
        board[81 + col] = code
    for col, code in enumerate((8, 9, 10, 11, 12, 11, 10, 9, 8)):
        board[col] = code
    board[7 * 9 + 1] = board[7 * 9 + 7] = 6
    board[2 * 9 + 1] = board[2 * 9 + 7] = 13
    for col in (0, 2, 4, 6, 8):
        board[6 * 9 + col] = 7
        board[3 * 9 + col] = 14
    return board


STANDARD = standard_board()


def move_text(board, src, des):
    code = board[src]
    who = 0 if code <= 7 else 1
    src_c, src_r = src % 9, src // 9
    des_c, des_r = des % 9, des // 9
    name = PIECE.get(code, "?")
    if who == 0:
        src_file, des_file = NUM[9 - src_c], NUM[9 - des_c]
    else:
        src_file, des_file = str(src_c + 1), str(des_c + 1)
    same = [pos for pos in range(90) if pos != src and pos % 9 == src_c and board[pos] == code]
    prefix = ""
    if same:
        rows = [pos // 9 for pos in same]
        lo, hi = min(rows), max(rows)
        if who == 0:
            prefix = "前" if src_r == lo else ("后" if src_r == hi else "中")
        else:
            prefix = "前" if src_r == hi else ("后" if src_r == lo else "中")
    if src_c == des_c:
        forward = des_r < src_r if who == 0 else des_r > src_r
        action = ("进" if forward else "退") + NUM[abs(des_r - src_r)]
    else:
        forward = des_r < src_r if who == 0 else des_r > src_r
        if code in (2, 3, 4, 9, 10, 11):
            action = ("进" if forward else "退") + des_file
        else:
            action = "平" + des_file
    return (prefix + name + action) if prefix else name + src_file + action


def line_of(path):
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    parsed = line_from_v10(data, limit=DEPTH)
    if parsed is None:
        return None
    board, _kind, steps, _red, _black = parsed
    if board != STANDARD or not steps:
        return None
    names = []
    for src, des in steps:
        if board[src] == 0:
            break
        names.append(move_text(board, src, des))
        board[des] = board[src]
        board[src] = 0
    return names or None


def absorb(tree, names):
    node = tree
    for name in names:
        slot = node.get(name)
        if slot is None:
            slot = [0, {}]
            node[name] = slot
        slot[0] += 1
        node = slot[1]


def chunk(paths):
    tree = {}
    kept = 0
    for path in paths:
        names = line_of(path)
        if not names:
            continue
        absorb(tree, names)
        kept += 1
    return tree, kept


def merge(dest, src):
    for name, (count, kids) in src.items():
        slot = dest.get(name)
        if slot is None:
            dest[name] = [count, kids]
        else:
            slot[0] += count
            merge(slot[1], kids)


def prune(node):
    ranked = sorted(node.items(), key=lambda item: (-item[1][0], item[0]))[:KEEP]
    out = []
    for name, (count, kids) in ranked:
        item = {"m": name, "n": count}
        if kids:
            item["c"] = prune(kids)
        out.append(item)
    return out


def count_nodes(items):
    total = 0
    for item in items:
        total += 1 + count_nodes(item.get("c") or [])
    return total


def clip_late(nodes, depth, lates):
    """第十五步以后的着法再单独存放，点到第十五步再取。"""
    out = []
    for node in nodes:
        item = {"m": node["m"], "n": node["n"]}
        kids = node.get("c") or []
        if kids and depth >= LATE_AT:
            item["late"] = str(len(lates))
            lates[item["late"]] = kids
        elif kids:
            item["c"] = clip_late(kids, depth + 1, lates)
        out.append(item)
    return out


def detach_tail(nodes, depth, tails, lates):
    """第十步以后的着法单独存放，点到第十步再取。"""
    out = []
    for node in nodes:
        item = {"m": node["m"], "n": node["n"]}
        kids = node.get("c") or []
        if kids and depth >= TAIL_AT:
            item["tail"] = str(len(tails))
            tails[item["tail"]] = clip_late(kids, depth + 1, lates)
        elif kids:
            item["c"] = detach_tail(kids, depth + 1, tails, lates)
        out.append(item)
    return out


def main():
    files = all_games()
    started = time.time()
    groups = [files[i:i + 600] for i in range(0, len(files), 600)]
    tree = {}
    kept = 0
    seen = 0
    with Pool(_WORKERS) as pool:
        for part, n in pool.imap_unordered(chunk, groups):
            merge(tree, part)
            kept += n
            seen += 600
            if seen % 48000 < 600:
                print(f"已读 {min(seen, len(files))}/{len(files)}", flush=True)
    children = prune(tree)
    os.makedirs(PARTS, exist_ok=True)
    index = []
    part_bytes = 0
    for number, item in enumerate(children):
        tails = {}
        lates = {}
        body_nodes = detach_tail(item.get("c") or [], 2, tails, lates)
        body = json.dumps(body_nodes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(os.path.join(PARTS, f"{number}.json"), "wb") as handle:
            handle.write(body)
        tail_raw = json.dumps(tails, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(os.path.join(PARTS, f"{number}-tail.json"), "wb") as handle:
            handle.write(tail_raw)
        late_raw = json.dumps(lates, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(os.path.join(PARTS, f"{number}-late.json"), "wb") as handle:
            handle.write(late_raw)
        part_bytes += len(body) + len(tail_raw) + len(late_raw)
        index.append({"m": item["m"], "n": item["n"], "part": str(number)})
    payload = {
        "library": len(files),
        "total": kept,
        "depth": DEPTH,
        "keep": KEEP,
        "children": index,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(OUT, "wb") as handle:
        handle.write(raw)
    print(
        f"完成 {kept} 局，节点 {count_nodes(children)}，"
        f"首页 {len(raw) / 1024:.0f} KB，分叉 {part_bytes / 1024:.0f} KB，"
        f"用时 {time.time() - started:.1f} 秒",
        flush=True,
    )
    first = next(item for item in children if item["m"] == "炮二平五")
    print("炮二平五的第二步：")
    for item in first["c"][:10]:
        print(f"  {item['n']:7d}  {item['m']}")


if __name__ == "__main__":
    main()
