#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子进程 worker：解析单个 XQF 并输出开局索引 JSON（含一级 opening + 二级 opening2）。

用法: python3 _index_worker.py <ROOT> <xqf绝对路径>

注意：当前 build_index.py 采用 fork 多进程 + 内嵌 worker（_process_one），
比独立 subprocess 更快，本文件不再被主流程调用，仅保留作为
「单棋谱解析」的独立可运行参考 / 替代实现。
超时或崩溃时由父进程处理（无输出即视为失败）。
"""
import sys
import os
import json

ROOT = sys.argv[1]
f = sys.argv[2]
sys.path.insert(0, ROOT)

import cchess  # noqa: E402
from openings import detect_opening, detect_opening2  # noqa: E402


def main():
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
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
