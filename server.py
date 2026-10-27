#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国象棋棋谱 Web 解释器 — 本地浏览 XQF 棋谱
================================================
复用项目既有 a.py 的 cchess 解析逻辑（只依赖 cchess + 标准库，无额外 pip 依赖）。

用法:
    python3 server.py [port]        # 默认端口 8945
然后浏览器打开 http://127.0.0.1:8945/

页面:
    GET /                        -> web/index.html  站点首页
    GET /ecco                    -> web/ecco.html   ECCO 开局目录
    GET /ecco/a … /ecco/e        -> web/ecco/a.html … e.html  逐条编号
    GET /qipu                    -> web/qipu.html   棋谱（二级页）

API:
    GET /api/tree?path=&offset=&limit=  -> 某一层目录（文件夹一次给全，棋谱按页给）
    GET /api/game?path=<相对路径.xqf> -> 解析该棋谱为 JSON
"""
import json
import os
import re
import sqlite3
import threading
import time
import cchess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote, unquote_plus

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")

# ---------------------------------------------------------------------------
# 目录分类（与 a.py 的 list_books 保持一致）
# ---------------------------------------------------------------------------
TOP_BOOKS = [
    "比赛对局", "布局", "中局", "排局", "名局",
    "大师专集", "近代国手名局",
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

    # 迭代栈遍历。变着是「这一步的另一种走法」，挂在父着上，用父着之后的局面。
    # 主变先入栈后弹出，所以编号靠前；变着排在后面，用 parent 指回分叉点。
    firsts = []
    if game.first_move:
        firsts = list(game.first_move.get_siblings(include_me=True))
    stack = [(m, -1, init) for m in reversed(firsts)]
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
        children = list(m.get_children() or [])
        for c in reversed(children):
            stack.append((c, my_id, b2.copy()))

    info = {k: v for k, v in game.info.items()}
    code, name, event_left = split_ecco(str(info.get("event") or ""))
    if code:
        info["ecco"] = code
        if name:
            info["ecco_name"] = name
        if event_left:
            info["event"] = event_left
        else:
            info.pop("event", None)

    return {
        "start": json.dumps({"A": init}),
        "chessName": "ChineseChess",
        "winner": winner,
        "info": info,
        "annotate": game.annote,
        "moves": [str(v) for v in moves],
        "comment": {str(k): v for k, v in comment.items()},
        "parent": {str(k): v for k, v in parent.items()},
    }


# ---------------------------------------------------------------------------
# 目录树构建
# ---------------------------------------------------------------------------
_ECCO_CODE = re.compile(r"[A-E]\d{2}")


def split_ecco(event):
    """从赛事字段里取出原始谱带来的 ECCO 编号，例如 B20、C30。"""
    if not event:
        return "", "", ""
    found = list(_ECCO_CODE.finditer(event))
    if not found:
        return "", "", event
    match = found[-1]
    code = match.group(0)
    name = event[match.end():].strip(" \t-—:：")
    left = event[:match.start()].strip(" \t-—:：")
    return code, name, left


GAME_EXTS = (".xqf", ".qp")  # 库内棋谱扩展名（.xqf 主流；.qp/.QP 为 XQStudio 旧格式，数量大）
DIR_PAGE = 200


class DirIndex:
    """目录只在内存里记一遍。对外按层返回，避免一次吐出三十万局。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.ready = False
        self.dirs = {}
        self.counts = {}
        self.top = {}
        self.total = 0

    def build(self):
        started = time.time()
        dirs = {}
        for root in list_book_roots():
            for dirpath, dirnames, filenames in os.walk(root):
                rel = os.path.relpath(dirpath, ROOT)
                files = sorted(fn for fn in filenames if fn.lower().endswith(GAME_EXTS))
                dirs[rel] = {"files": files, "subs": list(dirnames)}
        counts = {}
        for rel in sorted(dirs, key=lambda item: item.count(os.sep), reverse=True):
            info = dirs[rel]
            total = len(info["files"])
            kept = []
            for name in info["subs"]:
                child = os.path.join(rel, name)
                count = counts.get(child, 0)
                if count:
                    kept.append(name)
                    total += count
            info["subs"] = sorted(kept)
            counts[rel] = total
        top = {}
        total = 0
        for root in list_book_roots():
            rel = os.path.relpath(root, ROOT)
            count = counts.get(rel, 0)
            total += count
            name = rel.split(os.sep)[0]
            top[name] = top.get(name, 0) + count
        self.dirs = dirs
        self.counts = counts
        self.top = top
        self.total = total
        self.ready = True
        print(
            f"目录索引完成：{total} 局，{len(dirs)} 个目录，用时 {time.time() - started:.1f} 秒",
            flush=True,
        )

    def count_of(self, rel):
        if not rel:
            return self.total
        if rel in self.counts:
            return self.counts[rel]
        return sum(self._children(rel).values())

    def _children(self, rel):
        prefix = rel + os.sep
        found = {}
        for path, count in self.counts.items():
            if not path.startswith(prefix) or not count:
                continue
            name = path[len(prefix):].split(os.sep, 1)[0]
            child = prefix + name
            if name not in found:
                found[name] = self.counts.get(child, 0)
        return found

    def resolve(self, rel):
        rel = (rel or "").replace("\\", "/").strip("/")
        if not rel:
            return ""
        rel = os.path.normpath(rel)
        if rel.startswith("..") or os.path.isabs(rel):
            return None
        if rel in self.dirs or rel in self.top:
            return rel
        prefix = rel + os.sep
        if any(path.startswith(prefix) for path in self.dirs):
            return rel
        return None

    def page(self, rel, offset, limit):
        rel = self.resolve(rel)
        if rel is None:
            return {"error": "没有这个目录"}
        if rel in self.dirs:
            info = self.dirs[rel]
            folder_pairs = [
                (name, self.counts.get(os.path.join(rel, name), 0))
                for name in info["subs"]
            ]
            filenames = info["files"]
        elif rel == "":
            folder_pairs = sorted(self.top.items())
            filenames = []
        else:
            folder_pairs = sorted(self._children(rel).items())
            filenames = []
        folders = []
        if offset == 0:
            for name, count in folder_pairs:
                if not count:
                    continue
                child = os.path.join(rel, name) if rel else name
                folders.append({
                    "label": name,
                    "path": child.replace(os.sep, "/"),
                    "count": count,
                })
        chunk = filenames[offset:offset + limit]
        files = []
        for fn in chunk:
            full = os.path.join(rel, fn) if rel else fn
            files.append({
                "label": os.path.splitext(fn)[0],
                "path": full.replace(os.sep, "/"),
            })
        return {
            "path": rel.replace(os.sep, "/") if rel else "",
            "count": self.count_of(rel),
            "folders": folders,
            "files": files,
            "fileTotal": len(filenames),
            "offset": offset,
        }


DIR_INDEX = DirIndex()


def ensure_index():
    if DIR_INDEX.ready:
        return
    with DIR_INDEX.lock:
        if not DIR_INDEX.ready:
            DIR_INDEX.build()


CAT_DB = os.path.join(ROOT, "catalog.db")
CAT_PAGE = 200
_cat_cache = {"mtime": None, "outline": None}


def _cat_conn():
    if not os.path.isfile(CAT_DB):
        return None
    return sqlite3.connect(f"file:{CAT_DB}?mode=ro", uri=True)


_TAIL_CACHE = {}
_TAIL_LOCK = threading.Lock()


def move_tail(part, key, kind="tail"):
    """按编号取出一支后续着法，不把整包发给浏览器。"""
    if kind not in ("tail", "late") or not part.isdigit() or not key.isdigit():
        return None
    cache_key = kind + ":" + part
    with _TAIL_LOCK:
        data = _TAIL_CACHE.get(cache_key)
        if data is None:
            path = os.path.join(WEB, "move-parts", f"{part}-{kind}.json")
            if not os.path.isfile(path):
                return None
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            _TAIL_CACHE[cache_key] = data
    return data.get(key, [])


def cat_outline():
    mtime = os.path.getmtime(CAT_DB) if os.path.isfile(CAT_DB) else None
    if mtime is None:
        return {"error": "分类还在整理，稍后再打开"}
    if _cat_cache["mtime"] == mtime and _cat_cache["outline"] is not None:
        return _cat_cache["outline"]
    conn = _cat_conn()
    groups = {}
    order = []
    total = 0
    try:
        for opening, opening2, count in conn.execute(
            "SELECT opening, opening2, COUNT(*) FROM games GROUP BY opening, opening2"
        ):
            total += count
            if opening not in groups:
                groups[opening] = {"opening": opening, "count": 0, "children": []}
                order.append(opening)
            groups[opening]["count"] += count
            groups[opening]["children"].append({"opening2": opening2, "count": count})
    finally:
        conn.close()
    for group in groups.values():
        group["children"].sort(key=lambda item: (-item["count"], item["opening2"]))
    outline = {"total": total, "groups": [groups[name] for name in order]}
    _cat_cache["mtime"] = mtime
    _cat_cache["outline"] = outline
    return outline


def cat_page(opening, opening2, offset, limit):
    conn = _cat_conn()
    if conn is None:
        return {"error": "分类还在整理，稍后再打开"}
    try:
        if opening2:
            where = "WHERE opening=? AND opening2=?"
            args = (opening, opening2)
        else:
            where = "WHERE opening=?"
            args = (opening,)
        total = conn.execute(f"SELECT COUNT(*) FROM games {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT path, red, black FROM games {where} ORDER BY path LIMIT ? OFFSET ?",
            args + (limit, offset),
        ).fetchall()
    finally:
        conn.close()
    games = []
    for path, red, black in rows:
        name = os.path.splitext(os.path.basename(path))[0]
        games.append({"path": path, "name": name, "red": red or "", "black": black or ""})
    return {
        "opening": opening,
        "opening2": opening2,
        "total": total,
        "offset": offset,
        "games": games,
    }


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
            ensure_index()
            qs = parse_qs(parsed.query)
            rel = unquote_plus(qs.get("path", [""])[0])
            try:
                offset = max(0, int(qs.get("offset", ["0"])[0] or 0))
                limit = int(qs.get("limit", [str(DIR_PAGE)])[0] or DIR_PAGE)
            except ValueError:
                offset, limit = 0, DIR_PAGE
            limit = max(1, min(limit, 500))
            self._json(DIR_INDEX.page(rel, offset, limit))
            return

        if path == "/api/cat":
            qs = parse_qs(parsed.query)
            opening = unquote_plus(qs.get("opening", [""])[0])
            opening2 = unquote_plus(qs.get("opening2", [""])[0])
            if not opening:
                self._json(cat_outline())
                return
            try:
                offset = max(0, int(qs.get("offset", ["0"])[0] or 0))
                limit = int(qs.get("limit", [str(CAT_PAGE)])[0] or CAT_PAGE)
            except ValueError:
                offset, limit = 0, CAT_PAGE
            limit = max(1, min(limit, 500))
            self._json(cat_page(opening, opening2, offset, limit))
            return

        if path == "/api/move-tail":
            qs = parse_qs(parsed.query)
            part = qs.get("part", [""])[0]
            key = qs.get("key", [""])[0]
            kind = qs.get("kind", ["tail"])[0]
            rows = move_tail(part, key, kind)
            if rows is None:
                self._json({"error": "没有这一步"})
            else:
                self._json(rows)
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

        # 首页是 / ，棋谱是二级页 /qipu。
        if path in ("/", ""):
            path = "/index.html"
        elif path in ("/ecco", "/ecco/"):
            path = "/ecco.html"
        elif path.startswith("/ecco/"):
            letter = path.strip("/").split("/")[-1]
            if letter in "abcde":
                path = f"/ecco/{letter}.html"
        elif path in ("/qipu", "/qipu/"):
            path = "/qipu.html"
        elif path in ("/moves", "/moves/"):
            path = "/moves.html"
        elif path in ("/zhongpao", "/zhongpao/"):
            path = "/zhongpao.html"
        elif path in ("/bingqi", "/bingqi/"):
            path = "/bingqi.html"
        elif path in ("/feixiang", "/feixiang/"):
            path = "/feixiang.html"
        elif path in ("/guogong", "/guogong/"):
            path = "/guogong.html"
        elif path in ("/me", "/me/"):
            path = "/me.html"

        # 静态文件
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
    threading.Thread(target=ensure_index, daemon=True).start()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8945
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"象棋棋书已启动: http://127.0.0.1:{port}/  棋谱: http://127.0.0.1:{port}/qipu")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
