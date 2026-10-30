#!/usr/bin/env bash
# 部署前扫全库，生成本机要用的库和分叉数据。
# catalog.db、pos.db 不进仓库，克隆之后要跑这一次。
set -euo pipefail
cd "$(dirname "$0")"

echo "1/3 分类库 catalog.db"
python3 build_cat.py

echo "2/3 局面索引 pos.db"
python3 build_pos.py

echo "3/3 流行谱 web/move-tree.json 和 web/move-parts/"
python3 build_move_tree.py

echo "生成完成。接着可以 python3 server.py"
