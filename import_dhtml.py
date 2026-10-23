#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 community-xiangqi-games-database 的 DhtmlXQ 写成未加密 XQF 10。

这批棋谱的棋子表红方在前、黑方在后。坐标十位是从左到右的列，
个位是从上往下的行（0 在黑方底线）。XQF 里红方在下，所以行要翻成 9-y。
变着按「从第几步改走」接到主变上，注释一并写入。
"""
import os
import re
import struct
import sys

from cchess.board import ChessBoard
from cchess.common import fench_to_species

from import_dpxq import _HEADER, alloc_name, blank, fit_field, header_name, sanitize

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = "/home/jsh/下载/community-xiangqi-games-database/data"

# 输出目录：比赛谱单独放，避免和已经入库的「东萍」年份树混在一起。
SECTIONS = (
    ("opening", os.path.join(ROOT, "布局", "外站开局")),
    ("mid-games", os.path.join(ROOT, "中局")),
    ("end-games", os.path.join(ROOT, "残局", "外站残局")),
    ("puzzles", os.path.join(ROOT, "排局")),
    ("selected-games", os.path.join(ROOT, "名局")),
    ("tournaments", os.path.join(ROOT, "比赛对局", "外站赛事")),
)

_KINDS = "RNBAKABNRCCPPPPP"
_SKIP_EXT = {".md", ".json", ".png", ".jpg", ".jpeg", ".gif", ".txt", ".html"}
_FIELD = re.compile(r"\[DhtmlXQ_([A-Za-z0-9_]+)\](.*?)\[/DhtmlXQ_\1\]", re.S)
_RESULT = {
    "红胜": 1, "红先胜": 1, "先胜": 1,
    "黑胜": 2, "黑先胜": 2, "红先负": 2, "先负": 2,
    "和局": 3, "和棋": 3, "红先和": 3, "先和": 3, "和": 3,
}
_MAX_MOVES = 4000


class Mv:
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
        self.comment = ""
        self.next = None
        self.sibling = None


def clean_text(text):
    text = (text or "").replace("\r", "").replace("||", "\n").replace("|", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def norm_date(text):
    text = (text or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return text


def read_text(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    if "[DhtmlXQ" not in text:
        text = raw.decode("gb18030", errors="replace")
    return text


def fields_of(text):
    found = {}
    for key, value in _FIELD.findall(text):
        found.setdefault(key, value)
    return found


def board_bytes(binit):
    digits = re.sub(r"\D", "", binit or "")
    out = bytearray([0xFF] * 32)
    if len(digits) < 64:
        return bytes(out)

    def place(slot, pair):
        x, y = int(pair[0]), int(pair[1])
        if x > 8 or y > 9:
            return
        out[slot] = x * 10 + (9 - y)

    for i in range(16):
        place(i, digits[i * 2:i * 2 + 2])
        place(16 + i, digits[32 + i * 2:34 + i * 2])
    return bytes(out)


def move_pairs(text):
    digits = re.sub(r"\D", "", text or "")
    moves = []
    for i in range(0, min(len(digits) - 3, _MAX_MOVES * 4), 4):
        x1, y1, x2, y2 = (int(digits[i + k]) for k in range(4))
        if x1 > 8 or y1 > 9 or x2 > 8 or y2 > 9:
            break
        moves.append((x1 * 10 + (9 - y1), x2 * 10 + (9 - y2)))
    return moves


def link(moves):
    nodes = [Mv(src, dst) for src, dst in moves]
    for left, right in zip(nodes, nodes[1:]):
        left.next = right
    return nodes


def build_tree(found):
    """主变、变着、注释合成一棵着法树。变着编号是文件里的变着号。"""
    main = link(move_pairs(found.get("movelist", "")))
    lines = {0: (1, main)}
    pending = []
    for key, value in found.items():
        matched = re.fullmatch(r"move_(\d+)_(\d+)_(\d+)", key)
        if not matched:
            continue
        parent, ply, vid = (int(matched.group(i)) for i in range(1, 4))
        pending.append((vid, parent, ply, link(move_pairs(value))))
    pending.sort()
    for vid, parent, ply, nodes in pending:
        if parent not in lines or not nodes:
            continue
        start, parent_nodes = lines[parent]
        index = ply - start
        if not parent_nodes or not (0 <= index < len(parent_nodes)):
            continue
        lines[vid] = (ply, nodes)
        host = parent_nodes[index]
        while host.sibling is not None:
            host = host.sibling
        host.sibling = nodes[0]

    root_note = ""
    for key, value in found.items():
        matched = re.fullmatch(r"comment(\d+)(?:_(\d+))?", key)
        if not matched:
            continue
        text = clean_text(value)
        if not text:
            continue
        left, right = int(matched.group(1)), matched.group(2)
        if right is None:
            if left == 0:
                root_note = text if not root_note else root_note + "\n" + text
            else:
                _add_comment(lines, 0, left, text)
        else:
            _add_comment(lines, left, int(right), text)
    return (main[0] if main else None), root_note


def _add_comment(lines, line_id, ply, text):
    if line_id not in lines:
        return
    start, nodes = lines[line_id]
    index = ply - start
    if not (0 <= index < len(nodes)):
        return
    node = nodes[index]
    node.comment = text if not node.comment else node.comment + "\n" + text


def _snap(board):
    return [row[:] for row in board._board]


def _restore(board, rows):
    for y, row in enumerate(rows):
        board._board[y][:] = row


def _apply(board, src, dst):
    origin = (src // 10, src % 10)
    target = (dst // 10, dst % 10)
    fench = board.get_fench(origin)
    if not fench:
        return False
    _, side = fench_to_species(fench)
    board.move_player = side
    try:
        ok = board.is_valid_move(origin, target)
    except Exception:
        return False
    if not ok:
        return False
    board._move_piece(origin, target)
    return True


def prune(board, node):
    """丢掉走不到的着法。cchess 遇到非法着会把后面的着法接到错的父节点上。"""
    while node is not None:
        saved = _snap(board) if node.sibling is not None else None
        if not _apply(board, node.src, node.dst):
            node = node.sibling
            continue
        if node.next is not None:
            node.next = prune(board, node.next)
        if node.sibling is not None:
            _restore(board, saved)
            node.sibling = prune(board, node.sibling)
        return node
    return None


def make_board(raw):
    board = ChessBoard()
    for side in range(2):
        for index in range(16):
            pos = raw[side * 16 + index]
            if pos == 0xFF:
                continue
            board.put_fench(chr(ord(_KINDS[index]) + side * 32), (pos // 10, pos % 10))
    return board


def _comment_bytes(text):
    return (text or "").encode("gb18030", errors="ignore")


def emit(node, buf):
    flag = (0xF0 if node.next is not None else 0) | (0x01 if node.sibling is not None else 0)
    buf.append((node.src + 0x18) & 0xFF)
    buf.append((node.dst + 0x20) & 0xFF)
    buf.append(flag)
    buf.append(0)
    raw = _comment_bytes(node.comment)
    buf += struct.pack("<I", len(raw))
    buf += raw
    if node.next is not None:
        emit(node.next, buf)
    if node.sibling is not None:
        emit(node.sibling, buf)


def pack(title, event, date, site, red, black, result, pieces, root, note):
    tlen, title_b = fit_field(title, 63)
    elen, event_b = fit_field(event, 63)
    dlen, date_b = fit_field(date, 15)
    slen, site_b = fit_field("" if site in ("", "-") else site, 15)
    rlen, red_b = fit_field(header_name(red), 15)
    blen, black_b = fit_field(header_name(black), 15)
    header = struct.pack(
        _HEADER,
        b"XQ", 0x0A, blank(13), pieces, blank(3),
        result if result in (1, 2, 3) else 0, blank(12), 0, blank(15),
        tlen, title_b, blank(64),
        elen, event_b,
        dlen, date_b,
        slen, site_b,
        rlen, red_b,
        blen, black_b,
        0, blank(63),
        0, blank(15),
        0, blank(15),
        blank(32),
        0, blank(15),
        0, blank(15),
        blank(528),
    )
    note_b = _comment_bytes(note)
    body = bytearray(b"\x00\x00\x00\x00" + struct.pack("<I", len(note_b)) + note_b)
    if root is not None:
        emit(root, body)
    return header + body


def collection_name(folder):
    readme = os.path.join(folder, "README.md")
    if os.path.isfile(readme):
        for line in open(readme, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line.startswith("#"):
                continue
            title = line.lstrip("#").strip()
            if re.search(r"[\u4e00-\u9fff]", title):
                return sanitize(title, 40)
            break
    return sanitize(os.path.basename(folder), 50)


def convert_record(text):
    found = fields_of(text)
    if "binit" not in found and "movelist" not in found:
        return None
    pieces = board_bytes(found.get("binit", ""))
    root, note = build_tree(found)
    if root is not None:
        root = prune(make_board(pieces), root)
    if root is None and all(b == 0xFF for b in pieces):
        return None
    event = clean_text(found.get("event", "")).replace("\n", " ")
    opening = clean_text(found.get("open", "")).replace("\n", " ")
    # 原始谱的 open 常以 ECCO 编号开头，例如「B20 中炮对左三步虎」。
    # 编号放在赛事字段最前面，63 字节装不下时先保住编号。
    marked = re.match(r"^([A-E]\d{2})(?:\s+\S.*)?$", opening or "")
    if marked and opening not in event:
        event = f"{opening} {event}".strip() if event else opening
    elif event and opening and opening not in event:
        event = f"{event} {opening}"
    elif not event:
        event = opening
    return {
        "pieces": pieces,
        "root": root,
        "note": note,
        "title": clean_text(found.get("title", "")).replace("\n", " "),
        "event": event,
        "date": norm_date(found.get("date", "")),
        "site": clean_text(found.get("place", "")).replace("\n", " "),
        "red": clean_text(found.get("red", "")).replace("\n", " "),
        "black": clean_text(found.get("black", "")).replace("\n", " "),
        "result": _RESULT.get(clean_text(found.get("result", "")).replace("\n", " "), 0),
    }


def write_record(path, record, fallback_title):
    title = record["title"] or fallback_title
    blob = pack(
        title, record["event"], record["date"], record["site"],
        record["red"], record["black"], record["result"],
        record["pieces"], record["root"], record["note"],
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(blob)


def convert_all(src=SRC):
    written = skipped = 0
    for section, out_root in SECTIONS:
        section_dir = os.path.join(src, section)
        if not os.path.isdir(section_dir):
            print(f"缺少 {section}", flush=True)
            continue
        used = {}
        names = set()
        count = 0
        for collection in sorted(os.listdir(section_dir)):
            folder = os.path.join(section_dir, collection)
            if not os.path.isdir(folder):
                continue
            base = collection_name(folder)
            name, n = base, 2
            while name in names:
                name = sanitize(f"{base}-{n}", 50)
                n += 1
            names.add(name)
            for dirpath, _dirnames, filenames in os.walk(folder):
                rel_dir = os.path.relpath(dirpath, folder)
                parts = [] if rel_dir == "." else [sanitize(p, 40) for p in rel_dir.split(os.sep)]
                for filename in sorted(filenames):
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in _SKIP_EXT or filename.startswith("."):
                        continue
                    source = os.path.join(dirpath, filename)
                    try:
                        record = convert_record(read_text(source))
                    except Exception as exc:
                        skipped += 1
                        print(f"跳过 {source}: {exc}", flush=True)
                        continue
                    if record is None:
                        skipped += 1
                        continue
                    stem = sanitize(os.path.splitext(filename)[0], 120)
                    directory = os.path.join(out_root, name, *parts)
                    path = os.path.join(directory, alloc_name(used, directory, stem) + ".xqf")
                    write_record(path, record, stem)
                    written += 1
                    count += 1
                    if written % 5000 == 0:
                        print(f"已写入 {written}", flush=True)
        print(f"{section}：{count}", flush=True)
    print(f"完成：写入 {written}，跳过 {skipped}", flush=True)
    return written, skipped


def _test():
    import cchess
    samples = [
        (
            "end-games/残局杀势/炮兵-[卒]-攻杀-[四]",
            "/tmp/dhtml-end.xqf",
        ),
        (
            "puzzles/桔中秘残/士卒离心",
            "/tmp/dhtml-puz.xqf",
        ),
        (
            "tournaments/1986年-10中国象棋名手表演赛/19861027-李来群和陈孝坤",
            "/tmp/dhtml-tour.xqf",
        ),
    ]
    for rel, dest in samples:
        record = convert_record(read_text(os.path.join(SRC, rel)))
        write_record(dest, record, "测试")
        game = cchess.read_from_xqf(dest)
        node = game.first_move
        texts = []
        while node is not None and len(texts) < 6:
            texts.append(node.to_text())
            node = node.next_move
        print(rel, game.info.get("result"), game.info.get("red"), texts, flush=True)

    end = cchess.read_from_xqf("/tmp/dhtml-end.xqf")
    second = end.first_move.next_move
    branch = second.get_siblings()[0]
    print("变着", branch.to_text(), "注释", (second.annote or "")[:20], flush=True)
    assert branch.to_text() == "卒７平８"
    assert "卒7平8" in (second.annote or "")
    assert end.info["result"] == "1-0"

    puzzle = cchess.read_from_xqf("/tmp/dhtml-puz.xqf")
    assert puzzle.first_move.to_text() == "帅五进一"
    assert "橘中秘" in (puzzle.annote or "")
    assert puzzle.info["result"] == "1/2-1/2"

    tour = cchess.read_from_xqf("/tmp/dhtml-tour.xqf")
    assert tour.first_move.to_text() == "炮二平五"
    assert tour.first_move.next_move.to_text() == "马８进７"
    assert "李来群" in tour.info.get("red", "")
    assert tour.info.get("event", "").startswith("B20")
    node = tour.first_move
    n = 0
    while node is not None:
        n += 1
        node = node.next_move
    assert n == 178
    print("三盘样谱通过", flush=True)


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test()
    else:
        convert_all(sys.argv[1] if len(sys.argv) > 1 else SRC)
