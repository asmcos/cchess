#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按局面给全部棋谱做索引，在本机写入 pos.db。

pos.db 不提交。克隆之后运行：bash build.sh

每个局面用棋子位置和轮到谁走合成一个数字。网页按这个数字取：
有多少局走到这里、下一步各有多少局、对上的棋谱名单。
只走每盘棋的主变。读不出的加密谱跳过。
"""
import os
import sqlite3
import struct
import sys
import time
from multiprocessing import Pool

from build_cat import ROOT, _HEADER, _WORKERS, _flp, all_games
from build_move_tree import move_text
from openings import FEN_MAP

DB_PATH = os.path.join(ROOT, "pos.db")
_KINDS = "RNBAKABNRCCPPPPP"
MASK = (1 << 64) - 1
LIMIT = 800


def splitmix(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return (z ^ (z >> 31)) & MASK


KEYS = [splitmix(i + 1) for i in range(14 * 90)]
SIDE = splitmix(14 * 90 + 1)


def signed(value):
    value &= MASK
    if value >= (1 << 63):
        value -= 1 << 64
    return value


def hash_board(board, side):
    value = 0
    for square, code in enumerate(board):
        if code:
            value ^= KEYS[(code - 1) * 90 + square]
    if side:
        value ^= SIDE
    return signed(value)


def mainline(data, limit=LIMIT):
    """未加密棋谱的整条主变。变着不读。"""
    if len(data) < 0x410 or data[:2] != b"XQ" or data[2] > 0x0A:
        return None
    fields = struct.unpack_from(_HEADER, data)
    board_raw = fields[3]
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
    board = [grid[_flp(i)] for i in range(90)]
    cursor = 0x400
    if cursor + 8 > len(data):
        return board, []
    cursor += 4
    note = int.from_bytes(data[cursor:cursor + 4], "little")
    cursor += 4 + note
    steps = []
    while len(steps) < limit and cursor + 8 <= len(data):
        b0, b1, flag = data[cursor], data[cursor + 1], data[cursor + 2]
        cursor += 4
        clen = int.from_bytes(data[cursor:cursor + 4], "little")
        cursor += 4
        if clen < 0 or cursor + clen > len(data) + 1000000:
            break
        cursor += clen
        src = (b0 - 0x18) & 0xFF
        dst = (b1 - 0x20) & 0xFF
        sx, sy = divmod(src, 10)
        dx, dy = divmod(dst, 10)
        if max(sx, dx) > 8 or max(sy, dy) > 9:
            break
        steps.append((_flp(sy * 9 + sx), _flp(dy * 9 + dx)))
        if not (flag & 0xF0):
            break
    return board, steps


def chunk(paths):
    counts = {}
    branches = {}
    games = []
    for path in paths:
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            continue
        parsed = mainline(data)
        if parsed is None:
            continue
        board, steps = parsed
        seen = set()
        rows = []
        side = 0
        stopped = len(steps)
        for ply, (src, des) in enumerate(steps):
            if not board[src]:
                stopped = ply
                break
            digest = hash_board(board, side)
            if digest not in seen:
                seen.add(digest)
                counts[digest] = counts.get(digest, 0) + 1
                text = move_text(board, src, des)
                slot = branches.setdefault(digest, {})
                slot[text] = slot.get(text, 0) + 1
                rows.append((digest, ply))
            board[des] = board[src]
            board[src] = 0
            side ^= 1
        digest = hash_board(board, side)
        if digest not in seen:
            counts[digest] = counts.get(digest, 0) + 1
            rows.append((digest, stopped))
        games.append((rel, rows))
    flat = []
    for digest, slot in branches.items():
        for text, count in slot.items():
            flat.append((digest, text, count))
    return list(counts.items()), flat, games


def build(db_path=DB_PATH):
    files = all_games()
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("CREATE TABLE pos (hash INTEGER PRIMARY KEY, n INTEGER NOT NULL)")
    conn.execute(
        "CREATE TABLE nxt (hash INTEGER NOT NULL, move TEXT NOT NULL, n INTEGER NOT NULL, "
        "PRIMARY KEY (hash, move))"
    )
    conn.execute("CREATE TABLE game (id INTEGER PRIMARY KEY, path TEXT NOT NULL)")
    conn.execute("CREATE TABLE hit (hash INTEGER NOT NULL, gid INTEGER NOT NULL, ply INTEGER NOT NULL)")
    started = time.time()
    done = 0
    next_id = 1
    size = 400
    groups = [files[i:i + size] for i in range(0, len(files), size)]
    with Pool(_WORKERS) as pool:
        for counts, branches, games in pool.imap_unordered(chunk, groups):
            conn.executemany(
                "INSERT INTO pos (hash, n) VALUES (?, ?) "
                "ON CONFLICT(hash) DO UPDATE SET n = n + excluded.n",
                counts,
            )
            conn.executemany(
                "INSERT INTO nxt (hash, move, n) VALUES (?, ?, ?) "
                "ON CONFLICT(hash, move) DO UPDATE SET n = n + excluded.n",
                branches,
            )
            conn.executemany(
                "INSERT INTO game (id, path) VALUES (?, ?)",
                [(next_id + index, rel) for index, (rel, _rows) in enumerate(games)],
            )
            hits = []
            for index, (_rel, rows) in enumerate(games):
                gid = next_id + index
                for digest, ply in rows:
                    hits.append((digest, gid, ply))
            conn.executemany("INSERT INTO hit (hash, gid, ply) VALUES (?, ?, ?)", hits)
            next_id += len(games)
            done += len(games)
            if done // 20000 != (done - len(games)) // 20000:
                conn.commit()
                print(f"已读 {done} 局", flush=True)
    conn.commit()
    print(f"已读 {done} 局", flush=True)
    print("正在给棋谱名单做索引", flush=True)
    conn.execute("CREATE INDEX idx_hit ON hit(hash)")
    conn.commit()
    conn.close()
    os.replace(tmp, db_path)
    print(f"完成，用时 {time.time() - started:.1f} 秒，写入 {db_path}", flush=True)


def _test():
    from build_move_tree import standard_board
    start = hash_board(standard_board(), 0)
    print("开局", start)
    rel = "比赛对局/外站赛事/198610中国象棋名手表演赛/19861027-李来群和陈孝坤.xqf"
    data = open(os.path.join(ROOT, rel), "rb").read()
    board, steps = mainline(data)
    assert hash_board(board, 0) == start
    assert move_text(board, *steps[0]) == "炮二平五"
    from build_cat import line_from_v10
    other = line_from_v10(data, limit=20)
    assert steps[:20] == other[2]
    print("样谱通过", len(steps), "步")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test()
    else:
        build()
