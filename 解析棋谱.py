from cchess import read_from_xqf

game = read_from_xqf("未分类/NoName.XQF")  # 你的文件路径
game.init_board.print_board()  # 初始局面
game.print_text_moves()  # 带中文符号的完整棋谱
print(dir(game))
print(game.dump_info())
print(game.info)
print(game.dump_text_moves_with_annote())
print(game.dump_moves())
