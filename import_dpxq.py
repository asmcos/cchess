#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把东萍 ICCS 棋谱（.pgns）写成未加密的 XQF 10，放进 比赛对局/东萍。

cchess 只读 XQF。版本号 10 不加密，着法按象棋演播室的低版本偏移存放。
"""
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "比赛对局", "东萍")

# 红方 16 子、黑方 16 子。坐标是 x * 10 + y，y=0 在红方底线。
def _xy(x, y):
    return x * 10 + y

_BACK = (0, 1, 2, 3, 4, 5, 6, 7, 8)
_PAWNS = (0, 2, 4, 6, 8)
STANDARD_BOARD = bytes(
    [_xy(x, 0) for x in _BACK] + [_xy(1, 2), _xy(7, 2)] + [_xy(x, 3) for x in _PAWNS]
    + [_xy(x, 9) for x in _BACK] + [_xy(1, 7), _xy(7, 7)] + [_xy(x, 6) for x in _PAWNS]
)
assert len(STANDARD_BOARD) == 32

_BAD = str.maketrans({c: " " for c in '\\/:*?"<>|'})
_MOVE = re.compile(r"^([A-Ia-i])(\d)-([A-Ia-i])(\d)$")
_RESULT = {"1-0": 1, "0-1": 2, "1/2-1/2": 3}
_RESULT_WORD = {"1-0": "先胜", "0-1": "先负", "1/2-1/2": "先和"}
_HEADER = "<2sB13s32s3sB12sB15sB63s64sB63sB15sB15sB15sB15sB63sB15sB15s32sB15sB15s528s"


def gb_fit(text, limit):
    text = text or ""
    if len(text.encode("gb18030", errors="ignore")) <= limit:
        return text.encode("gb18030", errors="ignore")
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(text[:mid].encode("gb18030", errors="ignore")) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].encode("gb18030", errors="ignore")


def fit_field(text, size):
    raw = gb_fit(text, size)
    return len(raw), raw + b"\x00" * (size - len(raw))


def blank(size):
    return b"\x00" * size


def pack_xqf(title, event, date, site, red, black, result, moves):
    tlen, title_b = fit_field(title, 63)
    elen, event_b = fit_field(event, 63)
    dlen, date_b = fit_field(date, 15)
    slen, site_b = fit_field("" if site in ("", "-") else site, 15)
    rlen, red_b = fit_field(red, 15)
    blen, black_b = fit_field(black, 15)
    header = struct.pack(
        _HEADER,
        b"XQ", 0x0A, blank(13), STANDARD_BOARD, blank(3),
        _RESULT.get(result, 0), blank(12), 0, blank(15),
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
    body = bytearray(b"\x00\x00\x00\x00" + struct.pack("<I", 0))
    last = len(moves) - 1
    for i, (src, dst) in enumerate(moves):
        body.append((src + 0x18) & 0xFF)
        body.append((dst + 0x20) & 0xFF)
        body.append(0xF0 if i < last else 0x00)
        body.append(0)
        body += struct.pack("<I", 0)
    return header + body


def parse_move(token):
    matched = _MOVE.match(token)
    if not matched:
        return None
    fx = ord(matched.group(1).upper()) - ord("A")
    fy = int(matched.group(2))
    tx = ord(matched.group(3).upper()) - ord("A")
    ty = int(matched.group(4))
    if not (0 <= fx <= 8 and 0 <= fy <= 9 and 0 <= tx <= 8 and 0 <= ty <= 9):
        return None
    return fx * 10 + fy, tx * 10 + ty


def iter_games(path):
    headers, moves, bad = {}, [], False
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                if line.startswith("[Game ") and (headers or moves):
                    yield headers, moves, bad
                    headers, moves, bad = {}, [], False
                key, _, rest = line[1:-1].partition(" ")
                if rest.startswith('"') and rest.endswith('"'):
                    headers[key] = rest[1:-1]
                continue
            if line in _RESULT:
                headers.setdefault("Result", line)
                continue
            if line[0].isdigit() and "." in line:
                body = line.split(".", 1)[1].strip()
                for token in body.split():
                    if token in _RESULT:
                        headers.setdefault("Result", token)
                        continue
                    step = parse_move(token)
                    if step is None:
                        bad = True
                    else:
                        moves.append(step)
        if headers or moves:
            yield headers, moves, bad


def sanitize(text, limit=80):
    text = (text or "").replace(":", "-").translate(_BAD)
    text = re.sub(r"\s+", " ", text).strip(" .")
    text = text[:limit].rstrip(" .")
    return text or "未命名"


def header_name(full):
    """XQF 红黑姓名栏只有 15 字节。装不下队名加人名时，只留人名。"""
    full = full or ""
    if len(full.encode("gb18030", errors="ignore")) <= 15:
        return full
    last = full.split()[-1]
    if last and len(last.encode("gb18030", errors="ignore")) <= 15:
        return last
    return full


def alloc_name(used, directory, stem):
    names = used.setdefault(directory, set())
    name = stem
    n = 2
    while name in names:
        name = f"{stem}-{n}"
        n += 1
    names.add(name)
    return name


def convert(src, out_root=OUT):
    os.makedirs(out_root, exist_ok=True)
    used = {}
    written = skipped = 0
    for headers, moves, bad in iter_games(src):
        if bad or not moves:
            skipped += 1
            continue
        event = sanitize(headers.get("Event") or "未标赛事", 60)
        date = headers.get("Date") or ""
        year = date[:4] if len(date) >= 4 and date[:4].isdigit() else "未知年份"
        red = headers.get("Red") or headers.get("RedTeam") or "红方"
        black = headers.get("Black") or headers.get("BlackTeam") or "黑方"
        result = headers.get("Result") or "*"
        word = _RESULT_WORD.get(result, "未知")
        directory = os.path.join(out_root, sanitize(year, 8), event)
        os.makedirs(directory, exist_ok=True)
        stem = sanitize(f"{date} {red} {word} {black}".strip(), 140)
        path = os.path.join(directory, alloc_name(used, directory, stem) + ".xqf")
        title = f"{red} {word} {black}"
        date_hdr = date[:10] if len(date) >= 10 and date[4] == "-" else date
        blob = pack_xqf(
            title, event, date_hdr, headers.get("Site") or "",
            header_name(red), header_name(black), result, moves,
        )
        with open(path, "wb") as handle:
            handle.write(blob)
        written += 1
        if written % 5000 == 0:
            print(f"已写入 {written}", flush=True)
    print(f"完成：写入 {written}，跳过 {skipped}", flush=True)
    return written, skipped


if __name__ == "__main__":
    convert(sys.argv[1] if len(sys.argv) > 1 else
            "/home/jsh/下载/ICCS-20261023T005006Z-1-001/ICCS/dpxq-99813games.pgns")
