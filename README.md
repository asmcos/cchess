# 象棋棋书 · 首页说明

xqbook 是代码开源、使用免费的背谱打谱软件，同时也是一个学棋社区。网站在 [https://xqbook.cn/](https://xqbook.cn/)。它延续 [象棋百科全书](https://www.xqbase.com/) 的 [ECCO 2004](https://www.xqbase.com/ecco/ecco_intro.htm) 开局编号，把中国象棋布局收成可以背的棋谱，帮助初学者按类记谱。

棋谱阅读、打谱、背谱在二级页，说明见 [readme-qipu.md](readme-qipu.md)。

## 收藏了 30 万+ 棋谱

库里收藏了 **30 万+** 局棋谱，足够大家学习。比赛对局、布局、中局、残局、排局和名局都收在一起：有联赛和名手对局，有中炮、仙人指路这些开局，也有残局、排局和古谱全局。

到 [棋谱页](https://xqbook.cn/qipu) 可以按书翻，也可以按开局分类。目录和分类都是一页一页打开的，三十万局不会一次堆到页面上。

## 中国象棋

中国象棋是两个人对下的棋。棋盘由九条竖线、十条横线交叉而成，中间隔着楚河汉界。双方各有十六子：车、马、炮、相（象）、仕（士）、帅（将）和兵（卒）。红方先走，双方轮流走子，把对方的将或帅将死即胜。开局有定式，残局有杀法，所以学棋常常从记谱开始。

---

## 页面

| 页面 | 地址 | 做什么 |
| --- | --- | --- |
| 首页 | [https://xqbook.cn/](https://xqbook.cn/) | 说明这本棋书：延续 ECCO、五大类目录、怎么背谱 |
| 棋谱 | [https://xqbook.cn/qipu](https://xqbook.cn/qipu) | 30 万+ 局：按书翻、按开局分类、自己走主变 |
| 分叉 | [https://xqbook.cn/moves](https://xqbook.cn/moves) | 标准开局前 20 步，每层最常见的 10 种着法。第一步在 `web/move-tree.json`，点开后再取 `web/move-parts/`。部署时 `bash build.sh` 会重新生成 |

顶栏两边相同。「首页」留在本页，「棋谱」进入二级页。

---

## 首页在讲什么

首页不做打谱，只把书的用法讲清楚。三件事：

1. **延续编号**。沿用 ECCO：一个字母、两位数字，A 到 E 五大类。开局仍叫原来的名字。
2. **写成棋书**。编号下面挂上棋谱、主变和注释。同一类开局收在一处。
3. **帮人背谱**。先认类，再看这一类的主变，然后在棋谱页里自己走。走对往下，走错停下。

ECCO 五大类在首页做成目录：

- **A** 非中炮类（不含仙人指路）：飞相、起马、仕角炮、过宫炮
- **B** 中炮对反宫马及其他：单提马、左三步虎、反宫马、五六炮、五七炮
- **C** 中炮对屏风马：过河车、两头蛇、平炮兑车、五六炮、五七炮
- **D** 顺炮与列炮，含半途列炮
- **E** 仙人指路：对卒底炮、对兵局、转中炮

点目录里的任一类，进入开局目录 [https://xqbook.cn/ecco](https://xqbook.cn/ecco)。这份目录按 [ECCO 2004 目录](https://www.xqbase.com/ecco/ecco_contents.htm) 整理到十位分组，两位数字的逐条着法在各类页面：[A](https://xqbook.cn/ecco/a)、[B](https://xqbook.cn/ecco/b)、[C](https://xqbook.cn/ecco/c)、[D](https://xqbook.cn/ecco/d)、[E](https://xqbook.cn/ecco/e)。要背谱再去棋谱页。首页棋盘画的是中炮对屏风马的前两回合：红方炮二平五、马二进三，黑方上屏风马。

页脚「友情链接」指向象棋百科全书 [www.xqbase.com](https://www.xqbase.com/)。

---

## 自己部署

线上用 [https://xqbook.cn/](https://xqbook.cn/)。下面是在自己机器上跑的时候。

```bash
pip install cchess
bash build.sh
python3 server.py
```

`bash build.sh` 扫完全库，依次写出三样东西：

- `catalog.db`：棋谱页的「分类」和「开局类型」。不在仓库里。没生成时仍可按书翻谱，分类要等这一步跑完。棋谱按层打开，分类按页打开。
- `pos.db`：局面页按棋盘查找同样的局面和下一步的局数。不在仓库里。没生成时页面会提示还在整理。
- `web/move-tree.json` 和 `web/move-parts/`：流行谱、中炮、仙人指路、飞相局、过宫炮用的前 20 步分叉。

默认端口 **8945**。

- 首页：http://127.0.0.1:8945/
- 棋谱：http://127.0.0.1:8945/qipu
- 局面：http://127.0.0.1:8945/ju

---

## 首页相关文件

```
web/
├── index.html     # 首页
├── home.css       # 首页样式
├── ecco.html      # 开局目录
├── ecco/          # A–E 逐条编号
├── qipu.html      # 棋谱页
├── chess.css
└── app.js
server.py          # / 首页，/ecco 开局，/qipu 棋谱页
```
