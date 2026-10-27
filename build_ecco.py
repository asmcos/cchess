#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ECCO 2004 的 A–E 类页面整理成 web/ecco/{a-e}.html。

源文件是象棋百科全书的 ecco_a.htm … ecco_e.htm（gb18030）。
默认从 /tmp/ecco/ 读取。
"""
import re
import sys
from html import escape
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "web" / "ecco"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/ecco")

LETTERS = {
    "a": ("非中炮类", "不含仙人指路。本组 1569 局。"),
    "b": ("中炮对反宫马及其他", "屏风马、顺炮、列炮另列。本组 938 局。"),
    "c": ("中炮对屏风马", "本组 3012 局，是现代布局里最大的一类。"),
    "d": ("顺炮与列炮", "含半途列炮。本组 1009 局。"),
    "e": ("仙人指路", "本组 1669 局。"),
}
SHORT = {
    "a": "非中炮",
    "b": "反宫马",
    "c": "屏风马",
    "d": "顺炮列炮",
    "e": "仙人指路",
}


def tidy(text):
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([0-9n])\s*\.\s*", r"\1. ", text)
    text = re.sub(r"\s+([，。、])", r"\1", text)
    text = text.replace("(一)", "（一）").replace("(二)", "（二）").replace("(三)", "（三）")
    text = re.sub(r"(?<=[\u4e00-\u9fff])(?=[A-E][0-9])", " ", text)
    text = re.sub(r"(?<=[A-E0-9])(?=[\u4e00-\u9fff])", " ", text)
    text = re.sub(r"\s*\(\s*", " (", text)
    text = re.sub(r"\s*\)\s*", ") ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def cell_lines(td):
    inner = td.find("table")
    lines = []
    if inner:
        for tr in inner.find_all("tr"):
            if tr.find("table"):
                continue
            line = tidy(tr.get_text("", strip=False))
            if line:
                lines.append(line)
        if lines:
            return lines
    line = tidy(td.get_text("", strip=False))
    return [line] if line else []


def gloss(note):
    note = note.strip("()（）")
    m = re.search(r"共(\d+)\+(\d+)\+(\d+)=(\d+)局", note)
    if not m:
        return note
    red, draw, black, total = m.groups()
    rest = note[m.end():].lstrip("，,")
    text = f"红胜 {red}，和棋 {draw}，黑胜 {black}，合计 {total} 局"
    if rest:
        rest = rest.strip("()（）")
        rest = re.sub(r"共(?=\d)", "共 ", rest)
        rest = re.sub(r"(\d)局", r"\1 局", rest)
        text += "。" + rest
    return text


def split_heading(text):
    raw = re.sub(r"\s+", "", text)
    m = re.match(r"^([A-E]\d)．(.*)$", raw)
    if not m:
        return "", tidy(text), ""
    code, rest = m.group(1), m.group(2)
    name, sep, note = rest.partition("(共")
    if sep:
        note = "共" + note.rstrip(")")
    else:
        name, note = rest, ""
    return code, tidy(name), gloss(note) if note else ""


def count_bits(count):
    compact = re.sub(r"\s+", "", count)
    if compact in ("", "无"):
        return "", "无" if compact == "无" else ""
    m = re.search(r"(\d+)\+(\d+)\+(\d+)=(\d+)", compact)
    if not m:
        return "", tidy(count)
    red, draw, black, total = m.groups()
    return total, f"{red}+{draw}+{black}"


def parse(letter):
    raw = (SRC / f"ecco_{letter}.htm").read_bytes().decode("gb18030")
    soup = BeautifulSoup(raw, "lxml")
    groups = []
    for anchor in soup.find_all("a", attrs={"name": re.compile(rf"^ecco_{letter}[0-9]$")}):
        if anchor.get("href"):
            continue
        dt = anchor.find_parent("dt")
        table = dt.find_next("table") if dt else None
        code, name, note = split_heading(dt.get_text(" ", strip=True) if dt else "")
        codes = []
        if table:
            rows = table.find_all("tr", recursive=False)
            i = 0
            while i < len(rows):
                td = rows[i].find("td", recursive=False)
                if not td or td.find("table"):
                    i += 1
                    continue
                title = re.sub(r"\s+", "", td.get_text("", strip=True))
                matched = re.match(r"^([A-E]\d{2})[．.](.*)$", title)
                if not matched:
                    i += 1
                    continue
                item_code, item_name = matched.group(1), matched.group(2)
                moves, count = [], ""
                if i + 1 < len(rows):
                    next_td = rows[i + 1].find("td", recursive=False)
                    box = next_td.find("table") if next_td else None
                    box_text = box.get_text("", strip=True) if box else ""
                    if box and (box.find("a") or "共" in box_text or "无" in box_text or box.find("table")):
                        for row in box.find_all("tr", recursive=False):
                            cells = row.find_all("td", recursive=False)
                            if not cells:
                                continue
                            moves.extend(cell_lines(cells[0]))
                            if len(cells) > 1:
                                count = tidy(cells[1].get_text(" ", strip=True))
                        i += 2
                        codes.append((item_code, tidy(item_name), moves, count))
                        continue
                codes.append((item_code, tidy(item_name), moves, count))
                i += 1
        groups.append((code.lower(), code, name, note, codes))
    return groups


def render(letter, groups):
    title, blurb = LETTERS[letter]
    upper = letter.upper()
    switches = ['<a href="/ecco">目录</a>']
    for key, label in SHORT.items():
        current = ' aria-current="page"' if key == letter else ""
        switches.append(f'<a href="/ecco/{key}"{current}>{key.upper()} {escape(label)}</a>')
    decades = []
    for gid, code, name, _note, _codes in groups:
        shown = "空" if name == "空" else name
        decades.append(f'<a href="#{gid}">{escape(code)} {escape(shown)}</a>')

    sections = []
    for gid, code, name, note, codes in groups:
        if name == "空" and all(item_name == "空" and not moves for _c, item_name, moves, _n in codes):
            chips = "".join(
                f'<li id="{item}"><span>{item}</span> 空</li>' for item, _n, _m, _c in codes
            )
            body = f'<ul class="empty-list">{chips}</ul>'
            heading = f"{code} · 空"
            sub = "这一组留空。"
        else:
            blocks = []
            for item, item_name, moves, count in codes:
                total, formula = count_bits(count)
                if item_name == "空" and not moves:
                    blocks.append(
                        f'<article class="code is-empty" id="{item}">'
                        f'<span class="code-id">{item}</span><h3>空</h3></article>'
                    )
                    continue
                stat = f"{total} 局" if total else (formula or "")
                formula_html = f'<span class="formula">{escape(formula)}</span>' if formula and total else ""
                move_html = "".join(f"<p>{escape(line)}</p>" for line in moves)
                blocks.append(
                    f'<article class="code" id="{item}">'
                    f'<div class="code-head"><span class="code-id">{item}</span>'
                    f"<h3>{escape(item_name)}</h3>"
                    f'<div class="tags">{escape(stat)}{formula_html}</div></div>'
                    f'<div class="moves">{move_html}</div></article>'
                )
            body = "".join(blocks)
            heading = f"{code} · {name}"
            sub = note
        sections.append(
            f'<section class="section ecco-block" id="{gid}">'
            f"<h2>{escape(heading)}</h2>"
            f'<p class="sub">{escape(sub)}</p>{body}</section>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{upper} · {escape(title)} · 象棋棋书</title>
<meta name="description" content="ECCO 2004 {upper} 类开局编号，{escape(title)}。逐条着法与局数整理自象棋百科全书。">
<link rel="stylesheet" href="/home.css">
</head>
<body>
<div class="sheet">
  <header class="top">
    <a class="brand" href="/">
      <span class="seal">谱</span>
      <span>
        <strong>象棋棋书</strong>
        <em>xqbook.cn</em>
      </span>
    </a>
    <nav class="nav">
      <a href="/">首页</a>
      <a href="/qipu">棋谱</a>
      <a href="/ecco" aria-current="page">开局</a>
      <a href="/moves">流行谱</a>
      <a href="/zhongpao">中炮</a>
      <a href="/bingqi">仙人指路</a>
      <a href="/feixiang">飞相局</a>
      <a href="/guogong">过宫炮</a>
      <a href="/me">我的</a>
      <a href="/#memorize">背谱</a>
    </nav>
  </header>

  <section class="hero solo">
    <div>
      <p class="eyebrow">ECCO 2004 · {upper}00–{upper}99</p>
      <h1>{upper} · {escape(title)}</h1>
      <p class="lead">{escape(blurb)}局数按红胜、和棋、黑胜分开，再相加。括号里的“不包括”是这一号不收的旁支。</p>
      <nav class="switch">{''.join(switches)}</nav>
      <nav class="decade-nav">{''.join(decades)}</nav>
    </div>
  </section>
  {''.join(sections)}
  <footer class="foot">
    <div>象棋棋书 · xqbook.cn<br>{upper} 类整理自 ECCO 2004。</div>
    <div class="friends">
      <span>友情链接</span>
      <a href="https://www.xqbase.com/ecco/ecco_{letter}.htm" target="_blank" rel="noopener">{upper} 类原文</a>
      <a href="https://www.xqbase.com/" target="_blank" rel="noopener">www.xqbase.com</a>
    </div>
  </footer>
</div>
</body>
</html>
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for letter in "abcde":
        groups = parse(letter)
        codes = [item for _g in groups for item in _g[4]]
        if len(groups) != 10 or len(codes) != 100:
            raise SystemExit(f"{letter}: {len(groups)} 组 {len(codes)} 条，期望 10 组 100 条")
        path = OUT / f"{letter}.html"
        path.write_text(render(letter, groups), encoding="utf-8")
        print(f"{path.name}: {len(groups)} 组, {len(codes)} 条, {path.stat().st_size} 字节")


if __name__ == "__main__":
    main()
