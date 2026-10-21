#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国象棋棋谱 Web 解释器 — 本地浏览 XQF 棋谱
================================================
复用项目既有 a.py 的 cchess 解析逻辑（只依赖 cchess + 标准库，无额外 pip 依赖）。

用法:
    python3 server.py [port]        # 默认端口 8000
然后浏览器打开 http://127.0.0.1:8000/

API:
    GET /                        -> web/index.html
    GET /api/tree                -> 目录树（按项目分类扫描 .xqf）
    GET /api/game?path=<相对路径.xqf> -> 解析该棋谱为 JSON
"""
import json
import os
import cchess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, unquote_plus

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")

# ---------------------------------------------------------------------------
# 目录分类（与 a.py 的 list_books 保持一致）
# ---------------------------------------------------------------------------
TOP_BOOKS = [
    "比赛对局", "布局", "大师专集", "近代国手名局",
    "让子局", "实战中局夺子取胜技巧150局", "未分类",
]
GROUP_BOOKS = {"残局", "全局"}  # 其子目录为“一本书”


def list_book_roots():
    """返回所有“书”目录（Path）。"""
    roots = []
    for name in TOP_BOOKS:
        p = os.path.join(ROOT, name)
        if os.path.isdir(p):
            roots.append(p)
    for group in GROUP_BOOKS:
        gp = os.path.join(ROOT, group)
        if not os.path.isdir(gp):
            continue
        for entry in sorted(os.listdir(gp)):
            p = os.path.join(gp, entry)
            if os.path.isdir(p):
                roots.append(p)
    return roots


# ---------------------------------------------------------------------------
# 棋子编码：红 1-7，黑 8-14（与 a.py 一致）
# ---------------------------------------------------------------------------
FEN_MAP = {
    "R": 1, "N": 2, "B": 3, "A": 4, "K": 5, "C": 6, "P": 7,
    "r": 8, "n": 9, "b": 10, "a": 11, "k": 12, "c": 13, "p": 14,
}


def board_to_list(board):
    """ChessBoard -> 90 格一维数组（0=空）。"""
    ans = []
    for line in board._board:
        for ch in line:
            ans.append(FEN_MAP.get(ch, 0))
    return ans


def pos_to_index(p):
    """(col,row) -> 一维下标 row*9+col"""
    c, r = p
    return r * 9 + c


def move_to_int(move, board_list):
    """将一步着法打包为 32bit int（与 a.py 的 EatMoveInt 位布局一致）。"""
    src = pos_to_index(move.p_from)
    des = pos_to_index(move.p_to)
    src_chess = board_list[src]
    des_chess = board_list[des]
    who = 0 if src_chess <= 7 else 1
    return (who << 30) | (src << 22) | (des << 14) | (src_chess << 7) | des_chess


def parse_game_to_json(game):
    """cchess.Game -> 与 a.py serialize 兼容的 JSON dict。"""
    init = board_to_list(game.init_board)
    # 上下翻转：cchess 的 init_board 行0 为红方（与传统"红在下"相反），翻转为标准视角（红在下、黑在上）
    flp = lambda p: (9 - p // 9) * 9 + p % 9
    init = [init[flp(i)] for i in range(90)]
    # 结果 -> winner
    res = str(game.info.get("result", "*"))
    winner = {"1-0": 1, "0-1": 2, "1/2-1/2": 3, "*": 3}.get(res, 3)

    moves = []
    comment = {}
    parent = {}

    # 迭代栈遍历（避免深链棋谱触发 Python 递归深度上限，并用 seen 防循环引用导致的死循环）
    stack = [(game.first_move, -1, init)] if game.first_move else []
    seen = set()
    while stack:
        m, pa, b = stack.pop()
        if id(m) in seen:
            continue
        seen.add(id(m))
        src = flp(pos_to_index(m.p_from))
        des = flp(pos_to_index(m.p_to))
        sc = b[src]
        who = 0 if sc <= 7 else 1
        v = (who << 30) | (src << 22) | (des << 14) | (sc << 7) | b[des]
        moves.append(v)
        my_id = len(moves) - 1
        if m.annote:
            comment[my_id] = m.annote
        if pa != my_id - 1:
            parent[my_id] = pa
        b2 = b.copy()
        b2[src] = 0
        b2[des] = sc
        children = []
        for c in (m.get_children() or []):
            children.append(c)
        for s in (m.get_siblings() or []):
            if not any(c is s for c in children):
                children.append(s)
        for c in reversed(children):
            stack.append((c, my_id, b2.copy()))

    return {
        "start": json.dumps({"A": init}),
        "chessName": "ChineseChess",
        "winner": winner,
        "info": {k: v for k, v in game.info.items()},
        "annotate": game.annote,
        "moves": [str(v) for v in moves],
        "comment": {str(k): v for k, v in comment.items()},
        "parent": {str(k): v for k, v in parent.items()},
    }


# ---------------------------------------------------------------------------
# 目录树构建
# ---------------------------------------------------------------------------
GAME_EXTS = (".xqf", ".qp")  # 库内棋谱扩展名（.xqf 主流；.qp/.QP 为 XQStudio 旧格式，数量大）
def build_tree():
    """扫描所有书目录下的棋谱，构建 {label, path|children} 树。"""
    top = {"label": "棋谱库", "children": []}

    for root in list_book_roots():
        rel_root = os.path.relpath(root, ROOT)
        parts = rel_root.split(os.sep)
        node = top
        for part in parts:
            child = next((x for x in node["children"] if x.get("label") == part and "children" in x), None)
            if child is None:
                child = {"label": part, "children": []}
                node["children"].append(child)
            node = child

        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                if fn.lower().endswith(GAME_EXTS):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, ROOT)
                    node["children"].append({"label": os.path.splitext(fn)[0], "path": rel})

    def sort_node(n):
        if "children" not in n:
            return
        n["children"].sort(key=lambda x: (0 if "children" in x else 1, x["label"]))
        for c in n["children"]:
            sort_node(c)

    sort_node(top)
    return top


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/tree":
            self._json(build_tree())
            return

        if path == "/api/index":
            idx_path = os.path.join(ROOT, "index.json")
            if os.path.exists(idx_path):
                try:
                    with open(idx_path, encoding="utf-8") as f:
                        self._json(json.load(f))
                except Exception as ex:
                    self._json({"error": "索引读取失败: " + str(ex)})
            else:
                self._json({"error": "索引未生成，请先运行: python3 build_index.py"})
            return

        if path == "/api/title":
            title_path = os.path.join(ROOT, "title.json")
            if os.path.exists(title_path):
                try:
                    with open(title_path, encoding="utf-8") as f:
                        self._json(json.load(f))
                except Exception as ex:
                    self._json({"error": "标题表读取失败: " + str(ex)})
            else:
                self._json({"error": "标题表未生成，请先运行: python3 scan_titles.py"})
            return

        if path == "/api/game":
            qs = dict(kv.split("=", 1) for kv in parsed.query.split("&") if "=" in kv)
            rel = unquote_plus(qs.get("path", ""))
            target = os.path.normpath(os.path.join(ROOT, rel))
            if not target.startswith(ROOT):
                self._json({"error": "非法路径"})
                return
            try:
                game = cchess.read_from_xqf(target)
                data = parse_game_to_json(game)
                data["path"] = rel
                data["title"] = os.path.splitext(os.path.basename(rel))[0]
                self._json(data)
            except Exception as ex:
                self._json({"error": f"解析失败: {ex}"})
            return

        # 静态文件
        if path == "/" or path == "":
            path = "/index.html"
        fp = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not fp.startswith(WEB) or not os.path.isfile(fp):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ext = os.path.splitext(fp)[1].lower()
        with open(fp, "rb") as f:
            self._send(200, f.read(), CONTENT_TYPES.get(ext, "application/octet-stream"))

    def log_message(self, *args):
        pass


def main():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"中国象棋棋谱浏览器已启动: http://127.0.0.1:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
