import os
import os.path
from collections import Counter
from pathlib import Path
from pprint import pprint
from typing import Any

import cchess
import cyclopts
import msgpack
import zstd
from pydantic import BaseModel, Field
from tqdm import tqdm

app = cyclopts.App()


class EatMoveInt:
    """
    着法打包成一个 32 bit 整数（Python 的 int 任意精度，但逻辑同 Go）
    位布局与 Go 版完全一致：
        who      : 2 bit
        src      : 8 bit
        des      : 8 bit
        src_chess: 7 bit
        des_chess: 7 bit
    """

    __slots__ = ("_v",)

    def __init__(self, v: int = 0) -> None:
        self._v: int = v

    # 工厂函数：与 Go 的 NewEatMoveInt 等价
    @staticmethod
    def new(
        who: int, src: int, des: int, src_chess: int, des_chess: int
    ) -> "EatMoveInt":
        if not (0 <= who <= 3):
            raise ValueError("who must in 0..3")
        if not (0 <= src <= 255):
            raise ValueError("src must in 0..255")
        if not (0 <= des <= 255):
            raise ValueError("des must in 0..255")
        if not (0 <= src_chess <= 127):
            raise ValueError("src_chess must in 0..127")
        if not (0 <= des_chess <= 127):
            raise ValueError("des_chess must in 0..127")
        v = (who << 30) | (src << 22) | (des << 14) | (src_chess << 7) | des_chess
        return EatMoveInt(v)

    # 以下五个方法与 Go 版语义完全一致
    def who_did(self) -> int:
        return (self._v >> 30) & 0b11

    def src(self) -> int:
        return (self._v >> 22) & 0xFF

    def des(self) -> int:
        return (self._v >> 14) & 0xFF

    def src_chess(self) -> int:
        return (self._v >> 7) & 0x7F

    def des_chess(self) -> int:
        return self._v & 0x7F

    # 辅助：返回 [src, des]
    def to_ints(self) -> list[int]:
        return [self.src(), self.des()]

    # 调试字符串
    def __repr__(self) -> str:
        return (
            f"EatMoveInt(who={self.who_did()}, src={self.src()}({self.src_chess()}), "
            f"des={self.des()}({self.des_chess()}))"
        )

    # 让类实例可比较、可哈希（可选）
    def __eq__(self, other: object) -> bool:
        return isinstance(other, EatMoveInt) and self._v == other._v

    def __hash__(self) -> int:
        return hash(self._v)


@app.command()
def eatmove_test():
    mv = EatMoveInt.new(who=1, src=10, des=20, src_chess=5, des_chess=0)
    print(mv)  # 调试打印
    print(mv.to_ints())  # [10, 20]
    print(mv.who_did())  # 1


class Move(BaseModel):
    src: list[int]
    des: list[int]
    comment: str | None = None  # 对应move的注解
    children: list["Move"] = Field(default_factory=list)


class Game(BaseModel):
    # 对局信息
    info: dict[str, str | int]
    # 棋局介绍
    annotate: str | None = None
    # 初始局面
    init_board: list[int]
    # 着法及着法的注解
    moves: Move


def parse_fen(fen: cchess.ChessBoard) -> tuple[list[int], int]:
    """
    Parse Chinese chess FEN string to board array and turn.

    Args:
        fen: FEN string like "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"

    Returns:
        tuple: (board_array, turn) where board_array is list[int] and turn is 0 for red, 1 for black
    """
    # Piece mapping: lowercase=black(8-14), uppercase=red(1-7)
    piece_map = {
        "r": 8,
        "n": 9,
        "b": 10,
        "a": 11,
        "k": 12,
        "c": 13,
        "p": 14,  # black pieces
        "R": 1,
        "N": 2,
        "B": 3,
        "A": 4,
        "K": 5,
        "C": 6,
        "P": 7,  # red pieces
    }
    ans = []
    for line in fen._board:
        for i in line:
            ans.append(piece_map.get(i, 0))
    return ans


def convert_moves(move: cchess.Move) -> Move:
    ans = Move(
        src=list(move.p_from),
        des=list(move.p_to),
        comment=move.annote,
    )

    all_children = []
    if move.next_move:
        all_children.append(move.next_move)
    all_children.extend(move.branchs or [])
    for x in all_children:
        ans.children.append(convert_moves(x))
    return ans


def parse_game(game: cchess.Game):
    init_board = parse_fen(game.init_board)
    moves = convert_moves(game.first_move)
    return Game(
        info=game.info,
        annotate=game.annote,
        init_board=init_board,
        moves=moves,
    )


@app.command()
def books():
    books = [
        Path(i)
        for i in [
            "比赛对局",
            "布局",
            "大师专集",
            "近代国手名局",
            "让子局",
            "实战中局夺子取胜技巧150局",
            "未分类",
        ]
    ]
    for big_book in ["残局", "全局"]:
        for book in Path(big_book).iterdir():
            books.append(book)
    print(books, len(books))


@app.command()
def parse(file: Path):
    # "未分类/NoName.XQF"
    g = parse_game(cchess.read_from_xqf(file))
    print(g.model_dump_json())


@app.command()
def tree_moves(file: Path):
    """
    用树形结构打印着法列表
    """
    g = parse_game(cchess.read_from_xqf(file))

    def dfs(m: Move, prefix: str):
        print(prefix, f"{m.src},{m.des}")
        for x in m.children:
            dfs(x, prefix + " ")

    dfs(g.moves, "")


def zstd_compress(x: dict[str, Any]):
    return zstd.compress(msgpack.dumps(x))


def zstd_game(g: Game):
    return zstd_compress(g.model_dump())


def get_all_xqf_files() -> list[Path]:
    xqf_files = []
    for parent, folders, files in os.walk("."):
        for f in files:
            if f.lower().endswith(".xqf"):
                xqf_files.append(Path(parent) / f)
    return xqf_files


def load_xqf(fpath: Path) -> Game:
    game = cchess.read_from_xqf(fpath)
    parsed_game = parse_game(game)
    return parsed_game


@app.command()
def compare_format():
    """
    我断言：zstd+msgpack比xqf格式更节省空间
    """
    xqf_files = get_all_xqf_files()
    sizes = []
    for i in tqdm(xqf_files):
        xqf_size = os.path.getsize(i)
        zstd_size = len(zstd_game(load_xqf(i)))
        sizes.append((xqf_size, zstd_size))
        print(f"{i}: xqf_size={xqf_size}, zstd_size={zstd_size}")


@app.command()
def parse_all():
    """遍历所有xqf文件并解析"""
    # 收集所有xqf文件
    xqf_files = get_all_xqf_files()

    print(f"找到 {len(xqf_files)} 个xqf文件")
    # xqf_files = xqf_files[:100]

    # 使用tqdm显示进度条，逐个解析文件
    parsed_games = []
    failed_files = []

    for file_path in tqdm(xqf_files, desc="解析xqf文件"):
        try:
            parsed_game = load_xqf(file_path)
            parsed_games.append(parsed_game)
        except Exception as e:
            print(file_path, e)
            failed_files.append((str(file_path), str(e)))

    print(f"成功解析 {len(parsed_games)} 个文件")
    if failed_files:
        print(f"失败 {len(failed_files)} 个文件:")
        for file_path, error in failed_files[:5]:  # 只显示前5个错误
            print(f"  {file_path}: {error}")
        if len(failed_files) > 5:
            print(f"  ... 还有 {len(failed_files) - 5} 个文件失败")


@app.command()
def show_file_types():
    """
    打印当前文件夹下各个文件的类型
    """
    a = []
    for parent, folders, files in os.walk("."):
        for f in files:
            _, ext = os.path.splitext(f)
            a.append(ext)
    pprint(Counter(a).most_common())
    """
    [('.XQF', 5790),
    ('.QP', 4000),
    ('.xqf', 3374),
    ('.SG', 48),
    ('.txt', 27),
    ('.doc', 17),
    ('.xqn', 17),
    ('.CBL', 16),
    ('', 10),
    ('.rar', 7),
    ('.bin', 6),
    ('.qp', 3),
    ('.py', 2),
    ('.exe', 2), 
    ('.jpg', 1),
    ('.HTT', 1),
    ('.ini', 1),
    ('.TXT', 1),
    ('.lib', 1),
    ('.SGM', 1),
    ('.data', 1),
    ('.hash', 1)]
    """


if __name__ == "__main__":
    app()
