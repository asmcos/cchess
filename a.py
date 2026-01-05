import json
import os
import os.path
import subprocess as sp
from collections import Counter
from pathlib import Path
from pprint import pprint
from typing import Any

import cchess
import cyclopts
import msgpack
import zstd
from pydantic import BaseModel, Field
from tabulate import tabulate
from tqdm import tqdm

app = cyclopts.App()
dist_folder = Path("dist")
if not dist_folder.exists():
    dist_folder.mkdir()


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
    src: int
    des: int
    src_chess: int
    des_chess: int
    who: int
    comment: str | None = None  # 对应move的注解
    children: list["Move"] = Field(default_factory=list)

    def to_int(self) -> int:
        return EatMoveInt.new(
            self.who, self.src, self.des, self.src_chess, self.des_chess
        )._v


class Game(BaseModel):
    # 对局信息
    info: dict[str, str | int]
    # 棋局介绍
    annotate: str | None = None
    # 初始局面
    init_board: list[int]
    # 着法及着法的注解
    moves: list[Move]

    def serialize(self):
        ans = {}
        ans["start"] = json.dumps({"A": self.init_board})
        ans["chessName"] = "ChineseChess"
        match self.info["result"]:
            case "1-0":
                ans["winner"] = 1
            case "0-1":
                ans["winner"] = 2
            case "1/2-1/2":
                ans["winner"] = 3
            case "*":
                ans["winner"] = 3
            case _:
                print(f"Unknown result: {self.info['result']}")

        ans["info"] = self.info
        comment = {}
        moves = []
        parent = {}

        def dfs(no: Move, pa: int):
            my_id = len(moves)
            moves.append(no.to_int())
            if no.comment:
                comment[my_id] = no.comment
            if pa != my_id - 1:
                parent[my_id] = pa
            for child in no.children:
                dfs(child, my_id)

        for i in self.moves:
            dfs(i, -1)

        ans["moves"] = [str(i) for i in moves]
        ans["comment"] = comment
        ans["parent"] = parent
        return ans

    def save_to(self, fpath: Path):
        with open(fpath, "w") as f:
            json.dump(self.serialize(), f, ensure_ascii=False)


def convert_board(fen: cchess.ChessBoard) -> list[int]:
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


def convert_pos(p: list[int]):
    c, r = p
    pp = r * 9 + c
    return pp


def convert_move(move: cchess.Move) -> Move:
    b = convert_board(move.board)
    src = convert_pos(move.p_from)
    des = convert_pos(move.p_to)
    src_chess = b[src]
    des_chess = b[des]
    who = 0 if src_chess <= 7 else 1
    assert src_chess != 0
    ans = Move(
        who=who,
        src=src,
        des=des,
        src_chess=src_chess,
        des_chess=des_chess,
        comment=move.annote,
    )

    all_children = []
    if move.next_move:
        all_children.append(move.next_move)
        if move.next_move.branchs:
            all_children.extend([i for i in move.next_move.branchs if i])
    for x in all_children:
        ans.children.append(convert_move(x))
    return ans


def parse_game(game: cchess.Game) -> Game:
    init_board = convert_board(game.init_board)
    if not game.first_move:
        raise Exception("no first move")
    moves = [convert_move(game.first_move)]
    for i in game.first_move.branchs:
        if not i:
            continue
        moves.append(convert_move(i))
    return Game(
        info=game.info,
        annotate=game.annote,
        init_board=init_board,
        moves=moves,
    )


def list_books() -> list[Path]:
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
            if book.is_dir():
                books.append(book)
    return books


@app.command()
def upload():
    """
    把dist目录的数据上传
    """
    sp.check_call("rsync -r --progress dist/*  me:~/app/MyStatic/xq/", shell=True)


@app.command()
def sync():
    """
    同步数据：先构建dist，再生成棋谱文件，最后上传
    """
    sp.check_call("python a.py build-dist", shell=True)
    sp.check_call("python a.py books", shell=True)
    sp.check_call("python a.py upload", shell=True)


@app.command()
def record_steps():
    records = list(dist_folder.glob("**/*.json"))
    ans = []
    for i in tqdm(records):
        a = json.load(open(i))
        ans.append((str(i), len(a.get("moves") or [])))
    ans.sort(key=lambda x: x[1], reverse=True)
    ans = ans[:10]
    print(tabulate(ans, headers=["棋谱", "步数"]))


@app.command()
def books():
    """
    列出所有棋谱文件的数量
    """
    ans = []
    for book in list_books():
        book = dist_folder / (book.relative_to(Path(".")))
        target_book_path = dist_folder / f"{book.stem}.json"
        records = list(book.glob("**/*.json", recurse_symlinks=True))
        ans.append([str(book), len(records)])

        # 构建树形结构
        catelog = {
            "label": book.stem,
            "children": [],
        }

        # 按路径分组构建树结构
        def add_to_tree(tree: dict, path_parts: list[str], full_path: Path):
            current = tree
            for i, part in enumerate(path_parts):
                # 如果是最后一个部分且是.xqf文件
                if i == len(path_parts) - 1 and part.endswith(".json"):
                    # 查找或创建children数组
                    if "children" not in current:
                        current["children"] = []

                    # 添加文件节点
                    file_node = {
                        "label": full_path.stem,
                        "url": str(full_path.relative_to(dist_folder)),
                    }
                    current["children"].append(file_node)
                else:
                    # 是文件夹，查找或创建文件夹节点
                    if "children" not in current:
                        current["children"] = []

                    # 查找是否已存在该文件夹
                    folder_found = False
                    for child in current["children"]:
                        if child.get("label") == part and "children" in child:
                            current = child
                            folder_found = True
                            break

                    # 如果没找到，创建新的文件夹节点
                    if not folder_found:
                        folder_node = {
                            "label": part,
                            "children": [],
                        }
                        current["children"].append(folder_node)
                        current = folder_node

        # 为每个文件添加到树中
        for record in records:
            parts = str(record.relative_to(book)).split("/")
            add_to_tree(catelog, parts, record)

        def sort_children(no):
            if not no.get("children"):
                return
            no["children"].sort(key=lambda x: x["label"])
            for i in no.get("children"):
                sort_children(i)

        sort_children(catelog)
        with open(target_book_path, "w") as f:
            json.dump(
                {
                    "tree": catelog,
                    "view": "tree",
                    "name": book.stem,
                    "gameName": "ChineseChess",
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    ans.sort(key=lambda x: x[1], reverse=True)
    print(tabulate(ans))


@app.command()
def build_dist():
    """
    执行最终的转换，把棋谱转成JSON，写入到dist文件夹下
    """
    # 批量执行转换，把转换之后的文件写入到dist目录中去
    a = list_books()
    all_records: list[Path] = []
    for book in a:
        records = list(book.glob("**/*.xqf", recurse_symlinks=True))
        all_records.extend(records)
    for i in tqdm(all_records, desc="正在转写xqf格式的文件"):
        try:
            g = load_xqf(i)
            target_path = dist_folder / i.relative_to(".")
            target_path = target_path.parent / (i.stem + ".json")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            # print(target_path)
            g.save_to(target_path)
        except Exception as ex:
            print(i, ex)


@app.command()
def parse(file: Path):
    # "未分类/NoName.XQF"
    g = parse_game(cchess.read_from_xqf(file))
    print(json.dumps(g.serialize(), indent=2, ensure_ascii=False))


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
    return zstd_compress(g.serialize())


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
