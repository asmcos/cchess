#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给棋谱库做开局分类，在本机写入 catalog.db。

catalog.db 不提交。克隆之后运行：bash build.sh

网页按「一级 / 二级」分页取，不把三十万局一次发给浏览器。
版本 10 的棋谱只读开局几步；加密的旧谱交给 cchess。
残局、排局、中局按所在书名归类，不拿第一步去套开局。
"""
import os
import sqlite3
import struct
import sys
import time
from multiprocessing import Pool

import cchess

from openings import FEN_MAP, classify_line, detect_opening, detect_opening2
from server import list_book_roots

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "catalog.db")
_HEADER = "<2sB13s32s3sB12sB15sB63s64sB63sB15sB15sB15sB15sB63sB15sB15s32sB15sB15s528s"
_KINDS = "RNBAKABNRCCPPPPP"
_WORKERS = min(8, os.cpu_count() or 4)


def _flp(index):
    return (9 - index // 9) * 9 + index % 9


def _decode_name(length, raw):
    if not length:
        return ""
    try:
        return raw[:length].decode("gb18030").strip()
    except Exception:
        return ""


def folder_class(rel):
    parts = rel.split("/")
    if not parts:
        return None
    if parts[0] == "残局":
        if len(parts) >= 3 and parts[1] == "外站残局":
            return "残局", parts[2]
        if len(parts) >= 2:
            return "残局", parts[1]
    if parts[0] in ("排局", "中局") and len(parts) >= 2:
        return parts[0], parts[1]
    return None


def line_from_v10(data, limit=8):
    """未加密棋谱的主变前几步。变着写在主变后面，这里不读。"""
    if len(data) < 0x410 or data[:2] != b"XQ" or data[2] > 0x0A:
        return None
    fields = struct.unpack_from(_HEADER, data)
    board_raw = fields[3]
    kind = fields[7] + 1
    red = _decode_name(fields[18], fields[19])
    black = _decode_name(fields[20], fields[21])
    grid = [0] * 90
    for side in range(2):
        for index in range(16):
            pos = board_raw[side * 16 + index]
            if pos == 0xFF:
                continue
            x, y = divmod(pos, 10)
            if not (0 <= x <= 8 and 0 <= y <= 9):
                continue
            grid[y * 9 + x] = FEN_MAP[_KINDS[index] if side == 0 else _KINDS[index].lower()]
    flipped = [grid[_flp(i)] for i in range(90)]
    pos = 0x400
    # 起始注释：4 字节点 + 长度 + 正文
    if pos + 8 > len(data):
        return flipped, kind, [], red, black
    pos += 4
    note = int.from_bytes(data[pos:pos + 4], "little")
    pos += 4 + note
    steps = []

    def pull():
        nonlocal pos
        if pos + 8 > len(data) or len(steps) >= limit:
            return
        b0, b1, flag = data[pos], data[pos + 1], data[pos + 2]
        pos += 4
        clen = int.from_bytes(data[pos:pos + 4], "little")
        pos += 4
        if clen < 0 or pos + clen > len(data) + 1000000:
            return
        pos += clen
        src = (b0 - 0x18) & 0xFF
        dst = (b1 - 0x20) & 0xFF
        sx, sy = divmod(src, 10)
        dx, dy = divmod(dst, 10)
        if max(sx, dx) > 8 or max(sy, dy) > 9:
            return
        steps.append((_flp(sy * 9 + sx), _flp(dy * 9 + dx)))
        if flag & 0xF0 and len(steps) < limit:
            pull()

    pull()
    return flipped, kind, steps, red, black


def classify_file(path):
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    placed = folder_class(rel)
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return (rel, "无着法", "无着法", "", "")
    parsed = line_from_v10(data)
    if parsed is None:
        return _classify_with_cchess(path, rel, placed)
    board, kind, steps, red, black = parsed
    if placed:
        return (rel, placed[0], placed[1], red, black)
    opening, opening2 = classify_line(board, steps, kind)
    return (rel, opening, opening2, red, black)


def _classify_with_cchess(path, rel, placed):
    try:
        game = cchess.read_from_xqf(path)
    except Exception:
        if placed:
            return (rel, placed[0], placed[1], "", "")
        return (rel, "无着法", "无着法", "", "")
    info = game.info or {}
    red = str(info.get("red") or "")
    black = str(info.get("black") or "")
    if placed:
        return (rel, placed[0], placed[1], red, black)
    try:
        return (rel, detect_opening(game), detect_opening2(game), red, black)
    except Exception:
        return (rel, "无着法", "无着法", red, black)


def all_games():
    files = []
    for root in list_book_roots():
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.lower().endswith((".xqf", ".qp")):
                    files.append(os.path.join(dirpath, name))
    files.sort()
    return files


def _chunk(paths):
    return [classify_file(path) for path in paths]


def build(db_path=DB_PATH):
    files = all_games()
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE games (id INTEGER PRIMARY KEY, path TEXT, opening TEXT, "
        "opening2 TEXT, red TEXT, black TEXT)"
    )
    started = time.time()
    done = 0
    size = 400
    groups = [files[i:i + size] for i in range(0, len(files), size)]
    with Pool(_WORKERS) as pool:
        for rows in pool.imap_unordered(_chunk, groups):
            conn.executemany(
                "INSERT INTO games (path, opening, opening2, red, black) VALUES (?,?,?,?,?)",
                rows,
            )
            done += len(rows)
            if done % 20000 < size:
                conn.commit()
                print(f"已分类 {done}/{len(files)}", flush=True)
    conn.execute("CREATE INDEX idx_cat ON games(opening, opening2, id)")
    conn.commit()
    conn.close()
    os.replace(tmp, db_path)
    print(f"完成 {done} 局，用时 {time.time() - started:.1f} 秒，写入 {db_path}", flush=True)


def _test():
    samples = [
        "比赛对局/外站赛事/198610中国象棋名手表演赛/19861027-李来群和陈孝坤.xqf",
        "排局/桔中秘残-137/士卒离心.xqf",
        "残局/外站残局/残局杀势-154/炮兵-[卒]-攻杀-[四].xqf",
    ]
    for rel in samples:
        path = os.path.join(ROOT, rel)
        fast = classify_file(path)
        game = cchess.read_from_xqf(path)
        print(rel.split("/")[-1], fast[1], fast[2], "| cchess", detect_opening(game), detect_opening2(game))
    # 和 cchess 对一下标准开局
    rel = samples[0]
    path = os.path.join(ROOT, rel)
    data = open(path, "rb").read()
    board, kind, steps, red, black = line_from_v10(data)
    opening, opening2 = classify_line(board, steps, kind)
    game = cchess.read_from_xqf(path)
    assert opening == detect_opening(game), (opening, detect_opening(game))
    assert opening2 == detect_opening2(game), (opening2, detect_opening2(game))
    assert "李来群" in red and "陈孝坤" in black
    placed = classify_file(os.path.join(ROOT, samples[1]))
    assert placed[1] == "排局" and placed[2] == "桔中秘残-137"
    print("分类样谱通过")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test()
    else:
        build()
