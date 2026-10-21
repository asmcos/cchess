#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开局分类：基于红方第一步着法判定棋谱的开局类型（一级），
再结合红方体系与黑方应法给出二级开局名。
供 build_index.py 建索引、server.py 供前端过滤复用。
只依赖 cchess，不依赖 server.py。

分类体系：
  - 一级（红第一步）：炮平五路=中炮局、炮平六路=过宫炮局、炮平四路=仕角炮局、
      上马=起马局、挺兵=仙人指路、飞相=飞相局、上士=上士局、其它炮=其它炮局、其它=其它开局。
  - 二级（一级 + 对黑方应法，见 detect_opening2）：
      例：中炮对屏风马 / 中炮进三兵对屏风马 / 仙人指路对卒底炮 / 飞相对士角炮。
      黑方应法取前 8 步主变判定（屏风马需看第二只马是否正马位）。
  - 残局/排局（info.type 2/3）不判开局，二级记为"残局"。

坐标约定（与 a.py / server.py 一致）：
  - 一维下标 row*9+col；cchess 行0 为红方，_flp 上下翻转为标准视角（红在下）。
  - 红视角列：col0=九路 … col8=一路；红子 1-7、黑子 8-14。
"""
import cchess

# 列 -> 红方视角路数（红在下，col8=一，col0=九）
# col: 0=九,1=八,2=七,3=六,4=五,5=四,6=三,7=二,8=一

# 红棋子编码（与 a.py 一致）：1车 2马 3相 4仕 5帅 6炮 7兵
OPENING_TYPES = [
    "中炮局", "起马局", "仙人指路", "飞相局",
    "过宫炮局", "仕角炮局", "上士局", "其它炮局", "其它开局", "无着法",
]

FEN_MAP = {
    "R": 1, "N": 2, "B": 3, "A": 4, "K": 5, "C": 6, "P": 7,
    "r": 8, "n": 9, "b": 10, "a": 11, "k": 12, "c": 13, "p": 14,
}


def _board_to_list(board):
    ans = []
    for line in board._board:
        for ch in line:
            ans.append(FEN_MAP.get(ch, 0))
    return ans


def _pos_to_index(p):
    c, r = p
    return r * 9 + c


def _flp(p):
    """上下翻转：cchess 行0为红，翻转为标准视角（红在下）。"""
    return (9 - p // 9) * 9 + p % 9


def detect_opening(game):
    """根据红方第一步着法判定开局类型。game 为 cchess.Game。"""
    fm = game.first_move
    if not fm:
        return "无着法"
    init = _board_to_list(game.init_board)
    init = [init[_flp(i)] for i in range(90)]
    src = _flp(_pos_to_index(fm.p_from))
    des = _flp(_pos_to_index(fm.p_to))
    sc = init[src]
    dc = des % 9  # 目标列（0-8）
    # 红方先行，sc 应为红棋子(1-7)
    if sc == 6:      # 炮
        if dc == 4:      return "中炮局"    # 炮平五路(中路)
        if dc == 3:      return "过宫炮局"  # 炮平六路
        if dc == 5:      return "仕角炮局"  # 炮平四路(士角)
        return "其它炮局"
    if sc == 2:      return "起马局"        # 上马
    if sc == 7:      return "仙人指路"      # 挺兵
    if sc == 3:      return "飞相局"        # 飞相
    if sc == 4:      return "上士局"        # 上士
    return "其它开局"


def mainline_moves(game, n):
    """提取主变前 n 步，返回 [(src, des, piece), ...]，坐标为翻转后（红在下）。
    主变 = 每层取第一个子着法（棋谱常规主变）。piece 为移动棋子的编码。"""
    init = _board_to_list(game.init_board)
    init = [init[_flp(i)] for i in range(90)]
    b = init[:]
    out = []
    m = game.first_move
    for _ in range(n):
        if not m:
            break
        src = _flp(_pos_to_index(m.p_from))
        des = _flp(_pos_to_index(m.p_to))
        piece = b[src]
        b[des] = b[src]
        b[src] = 0
        out.append((src, des, piece))
        kids = m.get_children() or []
        m = kids[0] if kids else None
    return out


def _black_first_reply(ml):
    """黑方第一步应法名称（通用，用于非中炮一级的二级细分）。"""
    if len(ml) < 2:
        return "未知"
    s, d, p = ml[1]
    dc = d % 9
    if p == 13:                  # 黑炮
        if dc == 4:
            return "左中炮" if s % 9 <= 1 else "右中炮"
        if dc in (3, 5):
            return "士角炮"
        return "炮"
    if p == 9:                   # 黑马
        if dc in (2, 6):         # 黑马跳正马位
            pos = {s % 9}
            for k in (3, 5, 7):  # 黑方后续几步是否第二只马也正马
                if len(ml) > k:
                    s2, d2, p2 = ml[k]
                    if p2 == 9 and d2 % 9 in (2, 6):
                        pos.add(s2 % 9)
            return "屏风马" if len(pos) >= 2 else "单提马"
        return "马"
    if p == 14: return "挺卒"
    if p == 10: return "飞相"
    if p == 11: return "上士"
    if p == 8:  return "车"
    return "其它"


def _red_system(ml):
    """红方中炮体系细分（用于"对屏风马"等大类再细分）。扫描红方步（偶数下标 0,2,4..）。
    返回体系名：进三兵/过河车/五六炮/五七炮/进七兵/横车，未命中返回""。"""
    had_three = had_seven = had_56 = had_57 = had_cross = had_heng = had_zhix = False
    for i in range(2, len(ml), 2):
        s, d, p = ml[i]
        cs, cd, rd = s % 9, d % 9, d // 9
        if p == 7:                 # 红兵
            if cs == 6: had_three = True       # 三路兵
            elif cs == 2: had_seven = True     # 七路兵
        elif p == 6:               # 红炮
            if cd == 2: had_57 = True         # 五七炮（炮平七路）
            elif cd == 3: had_56 = True       # 五六炮（炮平六路）
        elif p == 1:               # 红车（红方编码：1车 2马 3相 4仕 5帅 6炮 7兵）
            if rd < 5: had_cross = True       # 过河车（红在下，行<5 即过河界）
            if cs in (0, 8) and cd in (3, 4, 5): had_heng = True  # 横车（边路车平中）
            if (cs == 8 and cd == 7) or (cs == 0 and cd == 1): had_zhix = True  # 直车(车一平二/车九平八)
    # 优先级：从具体体系到泛体系
    if had_three: return "进三兵"
    if had_cross: return "过河车"
    if had_56:    return "五六炮"
    if had_57:    return "五七炮"
    if had_seven: return "进七兵"
    if had_zhix:  return "直车"
    if had_heng:  return "横车"
    return ""


def _detect_zhongpao(ml):
    """中炮局的二级：红进兵/体系 + 对黑方应法。"""
    black_style = ""
    if len(ml) >= 2:
        s, d, p = ml[1]
        if p == 13:              # 黑炮
            if d % 9 == 4:
                black_style = "对顺炮" if s % 9 <= 1 else "对列炮"
            elif d % 9 in (3, 5):
                black_style = "对反宫马"
            else:
                black_style = "对其它炮"
        elif p == 9:             # 黑马
            dc = d % 9
            if dc not in (2, 6):
                return "中炮对单提马"
            pos = {s % 9}
            for k in (3, 5, 7):
                if len(ml) > k:
                    s2, d2, p2 = ml[k]
                    if p2 == 9 and d2 % 9 in (2, 6):
                        pos.add(s2 % 9)
            black_style = "对屏风马" if len(pos) >= 2 else "对单提马"
        elif p == 14: black_style = "对卒底"
        elif p == 8:  black_style = "对车"
        else:         black_style = "对其它"

    # "对屏风马"（最大类）按红方中炮体系进一步细分
    if black_style == "对屏风马":
        return "中炮" + _red_system(ml) + "对屏风马"

    # 其它黑应法：保留原有简单进兵细分
    red_sys = ""
    for i in range(2, len(ml), 2):
        s, d, p = ml[i]
        if p == 7:
            if s % 9 == 6: red_sys = "进三兵"; break
            if s % 9 == 2: red_sys = "进七兵"; break
    return "中炮" + red_sys + (black_style or "")


def detect_opening2(game):
    """二级开局名：一级 + 对黑方应法。所有一级都有二级细分；
    残局/排局类（info.type 2/3）返回"残局"。"""
    info = game.info or {}
    if info.get("type") in (2, 3):
        return "残局"
    o1 = detect_opening(game)
    ml = mainline_moves(game, 8)
    if o1 == "中炮局":
        return _detect_zhongpao(ml)
    base = {"中炮局": "中炮", "仙人指路": "仙人指路", "起马局": "起马",
            "飞相局": "飞相", "过宫炮局": "过宫炮", "仕角炮局": "仕角炮", "上士局": "上士"}.get(o1, o1)
    reply = _black_first_reply(ml)
    # 仙人指路(红挺兵)后黑挺卒 -> 卒底炮（标准叫法）
    if o1 == "仙人指路" and reply == "挺卒":
        return "仙人指路对卒底炮"
    return f"{base}对{reply}"


OPENING2_TYPES = [
    "中炮进三兵对屏风马", "中炮进三兵对反宫马", "中炮进三兵对顺炮",
    "中炮进三兵对列炮", "中炮进三兵对单提马", "中炮进三兵对卒底",
    "中炮进七兵对屏风马", "中炮进七兵对反宫马", "中炮进七兵对顺炮",
    "中炮进七兵对列炮", "中炮进七兵对单提马",
    "中炮对屏风马", "中炮对反宫马", "中炮对顺炮", "中炮对列炮",
    "中炮对单提马", "中炮对卒底", "中炮对其它",
]


if __name__ == "__main__":
    # 自测：读指定棋谱输出开局
    import sys, glob
    f = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob("**/*.xqf", recursive=True))[0]
    g = cchess.read_from_xqf(f)
    print(f"{f} -> {detect_opening(g)} | 二级: {detect_opening2(g)}")
