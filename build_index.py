#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建棋谱开局索引：扫描项目下全部 .xqf，判定每局开局类型，生成 index.json。

策略：多进程并行 + 卡死防护。
- 并行 N 个 worker 进程（fork，复用解释器，比 subprocess 快得多）。
- 每个棋谱在独立进程里解析；某棋谱解析超过 TIMEOUT 秒即判定卡死，
  父进程 terminate 该进程并记 fail，绝不拖垮整个构建。

用法:
    python3 build_index.py
生成:
    index.json
"""
import json
import multiprocessing as mp
import os
import sys
import time
from collections import Counter

import cchess  # noqa: E402  父进程 import，fork 子进程直接继承，减少启动开销
from openings import detect_opening, detect_opening2, OPENING_TYPES  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(ROOT, "index.json")
SKIP_DIRS = {"web", "dist", "node_modules", ".git"}
TIMEOUT = 8  # 单个棋谱解析超时（秒），超过即 terminate
N_WORKERS = min(8, os.cpu_count() or 4)


def _process_one(f, ROOT, result_q):
    """在独立子进程里解析单个棋谱，结果放入队列。"""
    try:
        sys.path.insert(0, ROOT)
        g = cchess.read_from_xqf(f)
        info = g.info or {}
        rel = os.path.relpath(f, ROOT)
        out = {
            "path": rel,
            "name": os.path.splitext(os.path.basename(f))[0],
            "opening": detect_opening(g),
            "opening2": detect_opening2(g),
            "red": str(info.get("red", "") or ""),
            "black": str(info.get("black", "") or ""),
            "event": str(info.get("event", "") or ""),
            "result": str(info.get("result", "") or ""),
        }
        result_q.put(("ok", out))
    except Exception as e:  # noqa: BLE001
        result_q.put(("err", repr(e)[:200]))


def all_xqf_files():
    files = []
    for dp, dirs, fns in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in fns:
            if fn.lower().endswith(".xqf"):
                files.append(os.path.join(dp, fn))
    return files


def _drain(q):
    """非阻塞取出队列全部结果。"""
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except Exception:
            break
    return out


def main():
    t = time.time()
    files = all_xqf_files()
    ctx = mp.get_context("fork")
    games = []
    fail = 0
    timeout_n = 0
    pending = []  # [(process, file, queue, start_time)]
    total = len(files)
    i = 0
    while i < total or pending:
        # 回收已完成 / 超时的进程，腾出槽位
        if pending:
            for idx, (p, f0, q, st) in enumerate(list(pending)):
                p.join(timeout=0.05)
                if not p.is_alive():
                    for tag, val in _drain(q):
                        if tag == "ok":
                            games.append(val)
                        else:
                            fail += 1
                    pending.pop(idx)
                    break
                elif time.time() - st > TIMEOUT:
                    p.terminate()
                    p.join()
                    _drain(q)
                    fail += 1
                    timeout_n += 1
                    pending.pop(idx)
                    break
        # 空闲槽位则提交新任务
        while i < total and len(pending) < N_WORKERS:
            f = files[i]
            q = ctx.Queue()
            p = ctx.Process(target=_process_one, args=(f, ROOT, q))
            p.start()
            pending.append((p, f, q, time.time()))
            i += 1
        if not pending:
            break
        # 防止空转
        time.sleep(0.01)
        if i % 500 == 0 and i > 0:
            print(f"进度 {i}/{total} 已得{len(games)} 失败{fail} 超时{timeout_n} ...", flush=True)

    idx = {
        "version": 1,
        "openings": OPENING_TYPES,
        "games": games,
        "count": len(games),
        "fail": fail,
        "timeout": timeout_n,
        "build_seconds": round(time.time() - t, 1),
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as fp:
        json.dump(idx, fp, ensure_ascii=False, separators=(",", ":"))

    c = Counter(x["opening"] for x in games)
    print("=== 开局统计 ===")
    for k in OPENING_TYPES:
        print(f"  {k}: {c.get(k, 0)}")
    print(f"总计 {len(games)}/{total} 个，失败 {fail}（含超时 {timeout_n}），"
          f"耗时 {idx['build_seconds']}s，已写入 {INDEX_PATH}")


if __name__ == "__main__":
    main()
