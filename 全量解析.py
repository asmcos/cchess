from typing import Any

import cchess
from pydantic import BaseModel


class Game(BaseModel):
    # 对局信息
    info: dict[str, Any]
    # 棋局介绍
    annotate: str
    # 初始局面
    init_board: Any
    # 着法及着法的注解
    moves: list[tuple[str, str]]
    moves_annotate: dict[int, str]


def convert_moves(moves):
    return [(f[0] * 10 + f[1], t[0] * 10 + t[1]) for (f, t) in moves]


def parse_game(game: cchess.Game):
    return Game(
        info=game.info,
        annotate=game.annote,
        init_board=game.init_board,
        moves=convert_moves(game.dump_moves()),
        moves_annotate={
            ind: annote
            for ind, (_, annote) in enumerate(game.dump_text_moves_with_annote())
        },
    )


g = parse_game(cchess.read_from_xqf("未分类/NoName.XQF"))
print(g.model_dump_json())
