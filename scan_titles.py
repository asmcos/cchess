#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描全库棋谱，提取"棋谱内标题"(info.title)，生成 {相对路径: 标题} 映射 title.json。
供前端左侧树在文件名下方直接展示内部标题，方便一眼定位。
只扫 .xqf（.qp 为 XQStudio 旧格式，cchess 解析失败，跳过）。
用法: python3 scan_titles.py [--workers N]
"""
import os
import json
import sys
import signal
import cchess
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.abspath(__file__))
GAME_EXTS = (".xqf",)
TIMEOUT = 8  # 单个棋谱解析超时(秒)，防止个别棋谱卡死拖累全量扫描


def collect_files():
    files = []
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        for fn in filenames:
            if fn.lower().endswith(GAME_EXTS):
                files.append(os.path.join(dirpath, fn))
    return files


def get_title(f):
    """读单个棋谱的 info.title，返回 (relpath, title) 或 None。含解析超时保护。"""
    def _timeout(_sig, _frm):
        raise TimeoutError("parse timeout")
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(TIMEOUT)
    try:
        g = cchess.read_from_xqf(f)
        t = (g.info or {}).get("title", "")
        if t and t.strip():
            return os.path.relpath(f, ROOT), t.strip()
    except Exception:
        return None
    finally:
        signal.alarm(0)
    return None


def main():
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else min(8, os.cpu_count() or 4)
    files = collect_files()
    print(f"找到 {len(files)} 个 .xqf 文件，workers={workers}", flush=True)
    out = {}
    with Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(get_title, files, chunksize=64)):
            if r:
                out[r[0]] = r[1]
            if i % 500 == 0:
                print(f"进度 {i}/{len(files)}", flush=True)
    with open(os.path.join(ROOT, "title.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"完成：{len(out)} 个内部标题已写入 title.json", flush=True)


if __name__ == "__main__":
    main()
