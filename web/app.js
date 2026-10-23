/*
 * 中国象棋棋谱浏览器 — 前端逻辑
 * ==================================================
 * 数据流：
 *   GET /api/tree?path=&offset=  -> 目录的一层（棋谱按页返回，不一次下完整库）
 *   GET /api/cat           -> 分类大纲；带 opening 时按页返回这一类的棋谱
 *   GET /api/game?path=xx  -> 解析单个棋谱为 JSON，加载到右侧棋盘
 *
 * 两大视图（顶部 tab 切换）：
 *   1. 棋谱库(lib)：目录树 + 开局类型下拉过滤；点棋谱在右侧棋盘打开。
 *   2. 分类(cat)  ：一级开局 -> 二级体系 -> 棋谱 的分类树；
 *                   点二级列出该类全部棋谱，点棋谱加载到棋盘。
 *
 * 坐标约定（与后端一致）：
 *   - 棋盘黑上红下；一维下标 = row*9 + col（row0 顶, row9 底=红方）。
 *   - 棋子编码：红 1-7（1车2马3相4仕5帅6炮7兵），黑 8-14。
 */
"use strict";

// ---------- 常量 ----------
const CELL = 60, PAD = 45;
const W = 8 * CELL + 2 * PAD, H = 9 * CELL + 2 * PAD;
const NUM_CN = ["零","一","二","三","四","五","六","七","八","九","十"];

// 棋子编码 -> 棋子名（红1-7，黑8-14）
const PIECE = {
  1:"车",2:"马",3:"相",4:"仕",5:"帅",6:"炮",7:"兵",
  8:"车",9:"马",10:"象",11:"士",12:"将",13:"炮",14:"卒",
};

const svg = document.getElementById("board");
let initBoard = null, moves = [], cur = -1, board = [];
let viewFlip = false;  // 视角切换：false=红方视角(红下黑上)，true=黑方视角(上下镜像，黑下红上)
let playTimer = null;
let memMode = false, selPiece = null;   // 背谱模式：memMode 开启，selPiece 为当前选中的己方棋子
let openingMap = {}, countByOpening = {}, filterOpening = "", titleMap = {};
let catGames = [], currentView = "lib";
const ORDER1 = ["中炮局","仙人指路","起马局","飞相局","过宫炮局","仕角炮局","上士局","其它炮局","其它开局","中局","残局","排局","无着法"];

// ---------- 棋盘静态绘制 ----------
function gridHTML() {
  const px = (c, r) => `x1="${PAD + c*CELL}" y1="${PAD + r*CELL}" x2="` 
  let out = "";
  const line = (x1,y1,x2,y2) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#7a4a1f" stroke-width="1.6"/>`;
  // 横线
  for (let r = 0; r <= 9; r++) out += line(PAD, PAD + r*CELL, PAD + 8*CELL, PAD + r*CELL);
  // 竖线
  for (let c = 0; c <= 8; c++) {
    const x = PAD + c*CELL;
    if (c === 0 || c === 8) out += line(x, PAD, x, PAD + 9*CELL);
    else { out += line(x, PAD, x, PAD + 4*CELL); out += line(x, PAD + 5*CELL, x, PAD + 9*CELL); }
  }
  // 九宫斜线
  const diag = (c1,r1,c2,r2) => line(PAD+c1*CELL, PAD+r1*CELL, PAD+c2*CELL, PAD+r2*CELL);
  out += diag(3,0,5,2); out += diag(5,0,3,2);   // 黑九宫
  out += diag(3,7,5,9); out += diag(5,7,3,9);   // 红九宫
  // 楚河汉界
  out += `<text x="${PAD+2*CELL}" y="${PAD+4.5*CELL}" font-size="26" fill="#7a4a1f" text-anchor="middle">楚 河</text>`;
  out += `<text x="${PAD+6*CELL}" y="${PAD+4.5*CELL}" font-size="26" fill="#7a4a1f" text-anchor="middle">汉 界</text>`;
  // 边框
  out += `<rect x="${PAD-10}" y="${PAD-10}" width="${8*CELL+20}" height="${9*CELL+20}" fill="none" stroke="#7a4a1f" stroke-width="2.5"/>`;
  return out;
}

// 棋子贴图映射（借用 GMChess wood 开源棋子，web/pieces/wood/）
const PIECE_IMG = {
  1:"red_rook",2:"red_knight",3:"red_bishop",4:"red_advisor",5:"red_king",6:"red_cannon",7:"red_pawn",
  8:"black_rook",9:"black_knight",10:"black_bishop",11:"black_advisor",12:"black_king",13:"black_cannon",14:"black_pawn",
};
function renderPieces() {
  const g = document.getElementById("pieces");
  // 当前步高亮：落点棋子套金圈红边，起点画红色虚线圆标记（让用户看清刚走的棋子）
  let hl = null;
  if (cur >= 0 && moves[cur]) hl = { s: moves[cur].src, d: moves[cur].des };
  let head = "";
  if (hl) {
    const sc = hl.s % 9, sr = Math.floor(hl.s / 9), srr = viewFlip ? 9 - sr : sr;
    head = `<circle cx="${PAD+sc*CELL}" cy="${PAD+srr*CELL}" r="15" fill="none" stroke="#e60000" stroke-width="2.2" stroke-dasharray="5 3" opacity="0.85"/>`;
  }
  g.innerHTML = head + board.map((code, p) => {
    if (!code) return "";
    const c = p % 9, r = Math.floor(p / 9);
    const rr = viewFlip ? 9 - r : r;            // 视角镜像行（黑方视角时上下翻转）
    const x = PAD + c * CELL, y = PAD + rr * CELL;
    const s = CELL * 0.9;
    const isHl = hl && p === hl.d;              // 刚走到的新位置
    const isSel = memMode && selPiece !== null && p === selPiece;  // 背谱选中的棋子
    const halo = isHl ? `<circle r="${s*0.58}" fill="rgba(255,215,0,0.28)" stroke="#e60000" stroke-width="2.5"/>` : "";
    const selRing = isSel ? `<circle r="${s*0.52}" fill="none" stroke="#4dd0ff" stroke-width="3.5"/>` : "";
    return `<g transform="translate(${x},${y})">${halo}${selRing}
      <image href="pieces/wood/${PIECE_IMG[code]}.svg" x="${-s/2}" y="${-s/2}" width="${s}" height="${s}"/>
    </g>`;
  }).join("");
}

// 切换红方/黑方视角：仅镜像棋子显示位置（棋盘网格上下对称无需改），着法文本为标准记录保持不变
function flipView() {
  viewFlip = !viewFlip;
  renderPieces();
  const b = document.getElementById("btnFlip");
  if (b) b.textContent = viewFlip ? "黑" : "红";
  if (memMode) autoAdvance();   // 红黑反转后，让系统自动走到用户要练的一方
}

// ---------- 着法解码与中文文本 ----------
function decodeInt(v) {
  v = Number(v);
  return {
    who: (v >>> 30) & 3,
    src: (v >>> 22) & 255,
    des: (v >>> 14) & 255,
    sc: (v >>> 7) & 127,
    dc: v & 127,
  };
}

function moveText(m, board) {
  const src = m.src, des = m.des;
  const srcC = src % 9, srcR = Math.floor(src / 9);
  const desC = des % 9, desR = Math.floor(des / 9);
  const code = m.sc;
  const name = PIECE[code] || "?";
  // 列号：红从右数用中文，黑从左数用阿拉伯
  let srcFile, desFile;
  if (m.who === 0) { srcFile = NUM_CN[9 - srcC]; desFile = NUM_CN[9 - desC]; }
  else { srcFile = String(srcC + 1); desFile = String(desC + 1); }

  // 同列同类棋子 -> 用 前/中/后
  let same = [];
  for (let p = 0; p < 90; p++) {
    if (p !== src && p % 9 === srcC && board[p] === code) same.push(p);
  }
  let prefix = "";
  if (same.length > 0) {
    const rows = same.map(p => Math.floor(p / 9));
    const minR = Math.min(...rows), maxR = Math.max(...rows);
    if (m.who === 0) { // 红：行小=前
      prefix = srcR === minR ? "前" : (srcR === maxR ? "后" : "中");
    } else {           // 黑：行大=前
      prefix = srcR === maxR ? "前" : (srcR === minR ? "后" : "中");
    }
  }

  let action;
  if (srcC === desC) {
    const fwd = m.who === 0 ? (desR < srcR) : (desR > srcR);
    const steps = Math.abs(desR - srcR);
    action = (fwd ? "进" : "退") + NUM_CN[steps];
  } else {
    const fwd = m.who === 0 ? (desR < srcR) : (desR > srcR);
    // 马、相/象、仕/士 斜走，不能"平"，记"进/退"+目标列
    if (code === 2 || code === 3 || code === 4 || code === 9 || code === 10 || code === 11) {
      action = (fwd ? "进" : "退") + desFile;
    } else {
      action = "平" + desFile;
    }
  }
  return prefix ? prefix + name + action : name + srcFile + action;
}

function buildMoves(data) {
  const init = JSON.parse(data.start).A;
  const arr = data.moves.map((vstr, i) => {
    const m = decodeInt(vstr);
    m.id = i;
    m.parent = data.parent && data.parent[i] !== undefined ? data.parent[i] : i - 1;
    return m;
  });
  // 着法文本按父着之后的局面计算。变着不沿用列表里前一条的局面。
  const after = new Array(arr.length);
  arr.forEach((m) => {
    const srcBoard = m.parent < 0 ? init : after[m.parent];
    m.text = moveText(m, srcBoard);
    const b = srcBoard.slice();
    b[m.src] = 0; b[m.des] = m.sc;
    after[m.id] = b;
  });
  return { init, arr };
}

// 从开局走到第 i 着实际要走的那些步（变着只含分叉前的主变）
function lineOf(i) {
  const chain = [];
  const guard = new Set();
  let k = i;
  while (k >= 0 && !guard.has(k)) {
    guard.add(k);
    chain.push(k);
    k = moves[k].parent;
  }
  chain.reverse();
  return chain;
}

// 当前着法的主续着。同一分叉上的变着排在后面，这里取最先记录的那条。
function nextStep(i) {
  for (let k = i + 1; k < moves.length; k++) {
    if (moves[k].parent === i) return k;
  }
  return -1;
}

// ---------- 导航 ----------
function goto(i) {
  if (typeof i !== "number" || i < 0) i = -1;
  if (i >= moves.length) i = moves.length - 1;
  cur = i;
  const chain = cur < 0 ? [] : lineOf(cur);
  board = initBoard.slice();
  for (const k of chain) {
    const m = moves[k];
    board[m.src] = 0; board[m.des] = m.sc;
  }
  renderPieces();
  document.getElementById("stepInfo").textContent = `${chain.length} / ${moves.length}`;
  const tip = document.getElementById("moveTip");
  // 移动端：初始局面的提示文字不显示（省空间）
  tip.textContent = cur >= 0 ? `第${chain.length}步  ${moves[cur].text}` : (window.innerWidth <= 900 ? "" : "初始局面");
  // 着法列表高亮 + 谱内滚动（只滚谱面板，页面/屏幕保持不动）
  document.querySelectorAll(".move-item").forEach(el => el.classList.toggle("current", +el.dataset.id === cur));
  const act = document.querySelector(`.move-item[data-id="${cur}"]`);
  if (act) {
    const pane = document.getElementById("movesPane");
    const top = act.offsetTop - pane.clientHeight / 2 + act.offsetHeight / 2;
    pane.scrollTop = Math.max(0, top);
  }
  // 注解
  const cb = document.getElementById("commentBox");
  const cmt = cur >= 0 ? commentMap[cur] : openingNote;
  if (cmt) { cb.style.display = "block"; cb.textContent = cmt; }
  else cb.style.display = "none";
}

let openingNote = "";

let commentMap = {};

// ---------- 着法列表 ----------
function renderMoveList() {
  const box = document.getElementById("moveList");
  box.innerHTML = "";
  moves.forEach((m, i) => {
    const div = document.createElement("div");
    div.className = "move-item" + (m.parent !== i - 1 ? " branch" : "");
    div.dataset.id = i;
    div.innerHTML = `<span class="idx">${i + 1}.</span><span>${m.text}</span>`;
    div.onclick = () => goto(i);
    box.appendChild(div);
  });
}

// ---------- 谱间导航（上一个/下一个谱）----------
let navList = [], navIdx = -1, navSub = null;
function setCtx(list, idx, sub) {
  navList = list || [];
  navIdx = idx;
  navSub = arguments.length > 2 ? sub : null;
  updateNav();
}
function folderHasMore(sub) {
  return !!(sub && sub.querySelector(":scope > .tree-more"));
}
function updateNav() {
  const p = document.getElementById("btnPrevGame");
  const n = document.getElementById("btnNextGame");
  if (p) p.disabled = !(navIdx > 0);
  if (n) n.disabled = !(navIdx < navList.length - 1 || folderHasMore(navSub));
}

// ---------- 棋谱加载 ----------
async function loadGame(path) {
  const resp = await fetch("./api/game?path=" + encodeURIComponent(path));
  const data = await resp.json();
  if (data.error) { alert(data.error); return; }
  const { init, arr } = buildMoves(data);
  initBoard = init; moves = arr; cur = -1;
  commentMap = {};
  openingNote = data.annotate || "";
  Object.entries(data.comment || {}).forEach(([k, v]) => commentMap[+k] = v);
  const info = data.info || {};
  const eccoBox = document.getElementById("gameEcco");
  if (eccoBox) {
    eccoBox.replaceChildren();
    if (info.ecco) {
      eccoBox.style.display = "";
      eccoBox.append("开局编号 ");
      const link = document.createElement("a");
      link.href = "/ecco/" + info.ecco[0].toLowerCase() + "#" + info.ecco;
      link.textContent = info.ecco;
      eccoBox.append(link);
      if (info.ecco_name) eccoBox.append(" " + info.ecco_name);
    } else {
      eccoBox.style.display = "none";
    }
  }
  // 主标题 = 文件名（去扩展名），方便用户按文件名归类
  document.getElementById("gameTitle").textContent = (data.title || path);
  // 内部标题（棋谱文件里存的正式标题，若与文件名不同则单独显示）
  const internalTitle = (info.title || "").trim();
  const gi = document.getElementById("gameInternal");
  if (internalTitle && internalTitle !== data.title) {
    gi.style.display = "";
    gi.textContent = "棋谱内标题： " + internalTitle;
  } else {
    gi.style.display = "none";
  }
  const meta = [
    info.red ? "红方 " + info.red : "",
    info.black ? " 黑方 " + info.black : "",
    info.event ? " · " + info.event : "",
    {1:"红胜",2:"黑胜",3:"和棋"}[data.winner] ? " · " + {1:"红胜",2:"黑胜",3:"和棋"}[data.winner] : "",
    " · " + (arr.length) + "步",
  ].filter(Boolean).join("");
  document.getElementById("gameMeta").textContent = meta;
  renderMoveList();
  goto(-1);
  // 同步地址栏 hash，便于分享/讨论同一棋谱（不污染浏览器历史）
  try { history.replaceState(null, "", "#path=" + encodeURIComponent(path)); } catch (e) {}
  // 谱间导航：定位当前谱在上下文列表中的位置，更新按钮可用性，并高亮对应列表行
  navIdx = navList.indexOf(path);
  updateNav();
  document.querySelectorAll(".tree-file").forEach(el => el.classList.toggle("active", el.dataset.path === path));
  document.querySelectorAll(".cat-game").forEach(el => el.classList.toggle("active", el.dataset.path === path));
  // 移动端：点棋谱后自动滚动到棋盘区，并把顶部列表收起（点击标签可再展开）
  if (window.innerWidth <= 900) {
    const el = document.getElementById("stageRow");
    if (el && el.scrollIntoView) setTimeout(() => el.scrollIntoView({ block: "start" }), 60);
    const sb = document.getElementById("sidebar");
    if (sb) sb.classList.add("collapsed");
    if (window.syncSideBtn) window.syncSideBtn();
  }
}

// ---------- 目录树（按层加载，一页 200 局）----------
const DIR_PAGE = 200;
let treeTotal = 0;
let indexPromise = null;

function folderFiles(sub) {
  return [...sub.querySelectorAll(":scope > .tree-file, :scope > .cat-game")].map(el => el.dataset.path);
}
async function fetchDir(path, offset) {
  const q = new URLSearchParams({
    path: path || "",
    offset: String(offset || 0),
    limit: String(DIR_PAGE),
  });
  const resp = await fetch("./api/tree?" + q);
  const data = await resp.json();
  if (data.error) throw new Error(data.error);
  return data;
}
function renderFile(node, container, depth, sub, before) {
  const row = document.createElement("div");
  row.className = "tree-file";
  row.style.paddingLeft = (10 + depth * 14) + "px";
  const nameDiv = document.createElement("div");
  nameDiv.className = "tree-file-name";
  nameDiv.textContent = node.label;
  row.appendChild(nameDiv);
  const t = titleMap && titleMap[node.path];
  if (t && t !== node.label) {
    const titleDiv = document.createElement("div");
    titleDiv.className = "tree-file-title";
    titleDiv.textContent = t;
    row.appendChild(titleDiv);
  }
  row.dataset.path = node.path;
  row.onclick = () => {
    document.querySelectorAll(".tree-file").forEach(el => el.classList.remove("active"));
    row.classList.add("active");
    const all = sub ? folderFiles(sub) : [node.path];
    setCtx(all, all.indexOf(node.path), sub || null);
    loadGame(node.path);
  };
  if (before) container.insertBefore(row, before);
  else container.appendChild(row);
}
function renderMore(sub, path, depth, state) {
  const row = document.createElement("div");
  row.className = "tree-more";
  row.style.paddingLeft = (10 + depth * 14) + "px";
  const rest = () => state.total - state.loaded;
  row.textContent = `继续加载（还有 ${rest()} 局）`;
  row._load = async () => {
    if (row.dataset.busy === "1" || rest() <= 0) return;
    row.dataset.busy = "1";
    row.textContent = "加载中…";
    try {
      const data = await fetchDir(path, state.loaded);
      data.files.forEach(file => renderFile(file, sub, depth, sub, row));
      state.loaded += data.files.length;
      if (rest() <= 0) row.remove();
      else row.textContent = `继续加载（还有 ${rest()} 局）`;
      if (navSub === sub) {
        const current = navList[navIdx];
        navList = folderFiles(sub);
        const at = navList.indexOf(current);
        if (at >= 0) navIdx = at;
        updateNav();
      }
    } catch (err) {
      row.textContent = "加载失败，点此重试";
    }
    row.dataset.busy = "0";
  };
  row.onclick = (e) => { e.stopPropagation(); row._load(); };
  sub.appendChild(row);
}
function fillDir(sub, data, depth, path) {
  data.folders.forEach(folder => renderFolder(folder, sub, depth));
  data.files.forEach(file => renderFile(file, sub, depth, sub));
  const loaded = data.offset + data.files.length;
  if (loaded < data.fileTotal) {
    renderMore(sub, path, depth, { loaded, total: data.fileTotal });
  }
}
function renderFolder(node, container, depth, prefetched) {
  const row = document.createElement("div");
  row.className = "tree-folder";
  row.style.paddingLeft = (10 + depth * 14) + "px";
  row.innerHTML = `<span class="tree-toggle">${depth === 0 ? "▼" : "▸"}</span>${node.label}<span class="tree-count">${node.count || 0}</span>`;
  const sub = document.createElement("div");
  sub.className = "tree-node";
  const expanded = depth === 0;
  sub.style.display = expanded ? "block" : "none";
  let built = false;
  let loading = false;
  const ensure = async () => {
    if (built || loading) return;
    loading = true;
    try {
      const data = prefetched || await fetchDir(node.path, 0);
      fillDir(sub, data, depth + 1, node.path);
      built = true;
    } catch (err) {
      sub.textContent = "这一层没有加载成功";
    }
    loading = false;
  };
  if (expanded) ensure();
  row.onclick = (e) => {
    e.stopPropagation();
    if (sub.style.display === "none") {
      ensure();
      sub.style.display = "block";
      row.children[0].textContent = "▼";
    } else {
      sub.style.display = "none";
      row.children[0].textContent = "▸";
    }
  };
  container.appendChild(row);
  container.appendChild(sub);
}
async function renderFiltered(opening) {
  const box = document.getElementById("tree");
  box.textContent = "正在加载这一类…";
  try {
    const data = await fetchCat(opening, "", 0);
    box.innerHTML = "";
    const sub = document.createElement("div");
    box.appendChild(sub);
    const state = { loaded: 0, total: data.total || 0 };
    const paint = (games) => {
      const more = sub.querySelector(":scope > .tree-more");
      games.forEach(g => renderFile({ label: g.name, path: g.path }, sub, 0, sub, more));
      state.loaded += games.length;
    };
    paint(data.games || []);
    if (state.loaded < state.total) {
      attachMore(sub, async () => {
        const next = await fetchCat(opening, "", state.loaded);
        paint(next.games || []);
        return state.loaded < state.total;
      }, () => state.total - state.loaded);
    }
    const el = document.getElementById("filterCount");
    if (el) el.textContent = state.total ? `${state.total} 局` : "";
  } catch (err) {
    box.textContent = err.message || "这一类没有加载成功";
  }
}
async function fetchCat(opening, opening2, offset) {
  const q = new URLSearchParams({
    opening: opening || "",
    opening2: opening2 || "",
    offset: String(offset || 0),
    limit: String(DIR_PAGE),
  });
  const resp = await fetch("./api/cat?" + q);
  const data = await resp.json();
  if (data.error) throw new Error(data.error);
  return data;
}
function attachMore(sub, loadNext, rest) {
  const row = document.createElement("div");
  row.className = "tree-more";
  row.style.paddingLeft = "24px";
  row.textContent = `继续加载（还有 ${rest()} 局）`;
  row._load = async () => {
    if (row.dataset.busy === "1") return;
    row.dataset.busy = "1";
    row.textContent = "加载中…";
    try {
      const moreLeft = await loadNext();
      if (!moreLeft) row.remove();
      else row.textContent = `继续加载（还有 ${rest()} 局）`;
      if (navSub === sub) {
        const current = navList[navIdx];
        navList = folderFiles(sub);
        const at = navList.indexOf(current);
        if (at >= 0) navIdx = at;
        updateNav();
      }
    } catch (err) {
      row.textContent = "加载失败，点此重试";
    }
    row.dataset.busy = "0";
  };
  row.onclick = (e) => { e.stopPropagation(); row._load(); };
  sub.appendChild(row);
}

async function loadTree() {
  const box = document.getElementById("tree");
  box.textContent = "正在整理目录…";
  try {
    const data = await fetchDir("", 0);
    treeTotal = data.count || 0;
    box.innerHTML = "";
    renderFolder({ label: "棋谱库", path: "", count: treeTotal }, box, 0, data);
  } catch (err) {
    box.textContent = "目录没有加载成功";
  }
  const el = document.getElementById("filterCount");
  if (el && !filterOpening) el.textContent = treeTotal ? `${treeTotal} 局` : "";
}
let catalog = null;
function ensureIndex() {
  if (indexPromise) return indexPromise;
  indexPromise = fetch("./api/cat").then(r => r.json()).then(data => {
    if (data.error) throw new Error(data.error);
    catalog = data;
    const sel = document.getElementById("openingFilter");
    if (sel) {
      const current = filterOpening;
      const groups = (data.groups || []).slice().sort((a, b) => orderIdx(a.opening) - orderIdx(b.opening));
      sel.innerHTML = `<option value="">全部开局</option>`;
      groups.forEach(g => {
        const opt = document.createElement("option");
        opt.value = g.opening;
        opt.textContent = `${g.opening} (${g.count})`;
        sel.appendChild(opt);
      });
      sel.value = current;
    }
    return data;
  });
  return indexPromise;
}

// ---------- 分类视图（一级 -> 二级 -> 棋谱）----------
function orderIdx(k) { const i = ORDER1.indexOf(k); return i < 0 ? 99 : i; }
function setView(v) {
  currentView = v;
  document.getElementById("tabLib").classList.toggle("active", v === "lib");
  document.getElementById("tabCat").classList.toggle("active", v === "cat");
  document.querySelector(".filter-bar").style.display = (v === "lib") ? "flex" : "none";
  document.getElementById("catList").style.display = (v === "cat") ? "block" : "none";
  // 移动端：点击标签（棋谱库/分类）时展开收起的列表
  if (window.innerWidth <= 900) {
    const sb = document.getElementById("sidebar");
    if (sb) sb.classList.remove("collapsed");
  }
  if (window.syncSideBtn) window.syncSideBtn();
  if (v === "lib") {
    if (filterOpening) renderFiltered(filterOpening);
    else loadTree();
  } else {
    ensureIndex().then(() => {
      if (currentView === "cat") renderCatTree();
    }).catch(err => {
      if (currentView === "cat") document.getElementById("tree").textContent = err.message || "分类没有加载成功";
    });
  }
}
function renderCatTree() {
  const box = document.getElementById("tree");
  box.innerHTML = "";
  const groups = ((catalog && catalog.groups) || []).slice().sort((a, b) => orderIdx(a.opening) - orderIdx(b.opening));
  groups.forEach(group => {
    const row = document.createElement("div");
    row.className = "tree-folder";
    row.style.paddingLeft = "10px";
    const toggle = document.createElement("span");
    toggle.className = "tree-toggle";
    toggle.textContent = "▸";
    row.appendChild(toggle);
    row.appendChild(document.createTextNode(group.opening));
    const cnt = document.createElement("span");
    cnt.className = "tree-count";
    cnt.textContent = String(group.count);
    row.appendChild(cnt);
    box.appendChild(row);
    const sub = document.createElement("div");
    sub.className = "tree-node";
    sub.style.display = "none";
    row.onclick = (e) => {
      e.stopPropagation();
      if (sub.style.display === "none") { sub.style.display = "block"; toggle.textContent = "▼"; }
      else { sub.style.display = "none"; toggle.textContent = "▸"; }
    };
    (group.children || []).forEach(child => {
      const r2 = document.createElement("div");
      r2.className = "tree-file cat2";
      r2.style.paddingLeft = "24px";
      const label = document.createElement("span");
      label.textContent = child.opening2;
      const count = document.createElement("span");
      count.className = "tree-count";
      count.textContent = String(child.count);
      r2.appendChild(label);
      r2.appendChild(count);
      r2.onclick = (e) => {
        e.stopPropagation();
        document.querySelectorAll(".cat2").forEach(x => x.classList.remove("active"));
        r2.classList.add("active");
        showCatGames(group.opening, child.opening2);
      };
      sub.appendChild(r2);
    });
    box.appendChild(sub);
  });
}
async function showCatGames(l1, l2) {
  const box = document.getElementById("catList");
  box.innerHTML = "";
  const head = document.createElement("div");
  head.className = "cat-head";
  head.textContent = `${l1} · ${l2}`;
  box.appendChild(head);
  const state = { loaded: 0, total: 0 };
  const paint = (games) => {
    const more = box.querySelector(":scope > .tree-more");
    games.forEach(g => {
      const r = document.createElement("div");
      r.className = "cat-game";
      const name = document.createElement("span");
      name.className = "cat-g-name";
      name.textContent = g.name;
      r.appendChild(name);
      if (g.red || g.black) {
        const meta = document.createElement("span");
        meta.className = "cat-g-meta";
        meta.textContent = `${g.red || ""}${g.black ? " vs " + g.black : ""}`;
        r.appendChild(meta);
      }
      r.dataset.path = g.path;
      r.onclick = () => {
        document.querySelectorAll(".cat-game").forEach(x => x.classList.remove("active"));
        r.classList.add("active");
        const paths = folderFiles(box);
        setCtx(paths, paths.indexOf(g.path), box);
        loadGame(g.path);
      };
      if (more) box.insertBefore(r, more);
      else box.appendChild(r);
    });
    state.loaded += games.length;
    head.textContent = `${l1} · ${l2}（${state.total} 局）`;
  };
  try {
    const data = await fetchCat(l1, l2, 0);
    state.total = data.total || 0;
    paint(data.games || []);
    if (state.loaded < state.total) {
      attachMore(box, async () => {
        const next = await fetchCat(l1, l2, state.loaded);
        paint(next.games || []);
        return state.loaded < state.total;
      }, () => state.total - state.loaded);
    }
  } catch (err) {
    head.textContent = err.message || "这一类没有加载成功";
  }
}

// ---------- 背谱模式 ----------
function memTip(msg, ok) {
  const el = document.getElementById("memTip");
  if (!el) return;
  el.textContent = msg;
  el.className = ok ? "mem-ok" : "mem-err";
}
let toastTimer = null;
function showToast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}
function exitMem() {
  if (memMode) { memMode = false; selPiece = null; }
  const b = document.getElementById("btnMem"); if (b) b.classList.remove("active");
  memTip("", true);
}
function userSide() { return viewFlip ? 1 : 0; }
function systemSide() { return viewFlip ? 0 : 1; }
function autoAdvance() {
  let guard = 0;
  while (guard++ < 400) {
    const nxt = nextStep(cur);
    if (nxt < 0 || moves[nxt].who !== systemSide()) break;
    goto(nxt);
  }
  const nxt = nextStep(cur);
  if (nxt < 0) memTip("🎉 整局背谱完成！", true);
  else memTip("正确！轮到你走" + (moves[nxt].who === 0 ? "红" : "黑") + "方", true);
}
function trunkIndex(ply) {
  let i = -1;
  for (let t = 0; t < ply; t++) {
    const n = nextStep(i);
    if (n < 0) return i;
    i = n;
  }
  return i;
}
function trunkLength() {
  let n = 0, i = -1;
  while (n <= moves.length) {
    const nxt = nextStep(i);
    if (nxt < 0) return n;
    i = nxt;
    n++;
  }
  return n;
}
function enterMem(startN) {
  memMode = true; selPiece = null;
  const b = document.getElementById("btnMem"); if (b) b.classList.add("active");
  goto(trunkIndex(Math.max(0, startN - 1)));
  autoAdvance();
}
function openMemModal() {
  const from = document.getElementById("memFrom"), lim = document.getElementById("memLimit");
  from.value = 1; lim.value = 15;
  from.disabled = true; lim.disabled = false;
  document.getElementById("memRand").checked = true;
  document.getElementById("memModal").style.display = "flex";
}
function closeMemModal() {
  document.getElementById("memModal").style.display = "none";
}
function startMemFromModal() {
  const rand = document.getElementById("memRand").checked;
  let startN = 1;
  const span = trunkLength() || moves.length;
  if (rand) {
    let M = parseInt(document.getElementById("memLimit").value, 10) || 15;
    M = Math.max(1, Math.min(M, span));
    startN = 1 + Math.floor(Math.random() * M);
  } else {
    startN = parseInt(document.getElementById("memFrom").value, 10) || 1;
  }
  startN = Math.max(1, Math.min(startN, span));
  closeMemModal();
  enterMem(startN);
}
function onCell(c, rr) {
  if (!memMode || !moves.length) return;
  const nxt = nextStep(cur);
  if (nxt >= 0 && moves[nxt].who !== userSide()) { autoAdvance(); return; }
  const r = viewFlip ? 9 - rr : rr;
  const p = r * 9 + c;
  const next = nxt >= 0 ? moves[nxt] : null;
  if (!next) { memTip("🎉 整局背谱完成！", true); return; }
  const code = board[p];
  if (code && (code <= 7) === (userSide() === 0)) { selPiece = p; renderPieces(); return; }
  if (selPiece !== null) {
    if (selPiece === next.src && p === next.des) {
      goto(nxt);
      selPiece = null; renderPieces();
      autoAdvance();
    } else {
      selPiece = null; renderPieces();
      const ply = lineOf(nxt).length;
      memTip("走错了！原谱第" + ply + "步：" + next.text + "，请重走", false);
      showToast("走错了！原谱第" + ply + "步：" + next.text);
    }
  }
}

function bindControls() {
  const $ = id => document.getElementById(id);
  const nav = (fn) => () => { exitMem(); fn(); };
  $("btnFirst").onclick = nav(() => goto(-1));
  $("btnPrev").onclick = nav(() => goto(cur < 0 ? -1 : moves[cur].parent));
  $("btnNext").onclick = nav(() => { const n = nextStep(cur); if (n >= 0) goto(n); });
  $("btnLast").onclick = nav(() => {
    let i = cur < 0 ? nextStep(-1) : cur;
    let guard = 0;
    while (i >= 0 && guard++ < moves.length) {
      const n = nextStep(i);
      if (n < 0) break;
      i = n;
    }
    if (i >= 0) goto(i);
  });
  $("btnReset").onclick = () => goto(-1);
  const pg = document.getElementById("btnPrevGame");
  if (pg) pg.onclick = () => { if (navIdx > 0) { navIdx--; loadGame(navList[navIdx]); updateNav(); } };
  const ng = document.getElementById("btnNextGame");
  if (ng) ng.onclick = async () => {
    if (navIdx >= navList.length - 1 && navSub) {
      const more = navSub.querySelector(":scope > .tree-more");
      if (more && more._load) await more._load();
    }
    if (navIdx < navList.length - 1) {
      navIdx++;
      loadGame(navList[navIdx]);
      updateNav();
    }
  };
  const sel = document.getElementById("openingFilter");
  if (sel) {
    sel.addEventListener("focus", () => ensureIndex());
    sel.onchange = async () => {
      filterOpening = sel.value;
      if (!filterOpening) { await loadTree(); return; }
      renderFiltered(filterOpening);
    };
  }
  $("btnMem").onclick = () => {
    if (!moves.length) { alert("请先选择一个棋谱再进入背谱"); return; }
    if (memMode) { exitMem(); goto(-1); return; }
    openMemModal();
  };
  const memCancel = document.getElementById("memCancel");
  if (memCancel) memCancel.onclick = closeMemModal;
  const memOk = document.getElementById("memOk");
  if (memOk) memOk.onclick = startMemFromModal;
  const memRand = document.getElementById("memRand");
  if (memRand) memRand.onchange = () => {
    const on = memRand.checked;
    document.getElementById("memFrom").disabled = on;
    document.getElementById("memLimit").disabled = !on;
  };
  $("btnPlay").onclick = () => {
    exitMem();
    if (playTimer) { clearInterval(playTimer); playTimer = null; $("btnPlay").textContent = "▶▶"; return; }
    $("btnPlay").textContent = "⏸";
    playTimer = setInterval(() => {
      const n = nextStep(cur);
      if (n < 0) { clearInterval(playTimer); playTimer = null; $("btnPlay").textContent = "▶▶"; return; }
      goto(n);
    }, 900);
  };
  window.addEventListener("keydown", (e) => {
    const hop = (n) => {
      exitMem();
      let i = cur;
      if (n > 0) {
        for (let t = 0; t < n; t++) {
          const nxt = nextStep(i);
          if (nxt < 0) break;
          i = nxt;
        }
      } else {
        for (let t = 0; t < -n; t++) {
          if (i < 0) break;
          i = moves[i].parent;
        }
      }
      goto(i);
    };
    if (e.key === "ArrowRight") hop(1);
    else if (e.key === "ArrowLeft") hop(-1);
    else if (e.key === "ArrowUp") hop(5);
    else if (e.key === "ArrowDown") hop(-5);
  });
}

function init() {
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  let clicks = "";
  for (let r = 0; r < 10; r++) for (let c = 0; c < 9; c++)
    clicks += `<rect x="${PAD + c*CELL - CELL/2}" y="${PAD + r*CELL - CELL/2}" width="${CELL}" height="${CELL}" fill="transparent" pointer-events="all" data-c="${c}" data-r="${r}"/>`;
  svg.innerHTML = gridHTML() + '<g id="pieces"></g>' + `<g id="gridClick">${clicks}</g>`;
  svg.addEventListener("click", (e) => {
    if (!memMode) return;
    const t = e.target;
    const c = +(t.getAttribute && t.getAttribute("data-c"));
    const r = +(t.getAttribute && t.getAttribute("data-r"));
    if (!isNaN(c) && !isNaN(r)) onCell(c, r);
  });
  bindControls();
  document.getElementById("tabLib").onclick = () => setView("lib");
  document.getElementById("tabCat").onclick = () => setView("cat");
  window.syncSideBtn = () => {
    const sb = document.getElementById("sidebar");
    const b = document.getElementById("toggleSide");
    if (b) b.textContent = sb && sb.classList.contains("collapsed") ? "▼" : "▲";
  };
  const sideBtn = document.getElementById("toggleSide");
  if (sideBtn) sideBtn.onclick = () => {
    const sb = document.getElementById("sidebar");
    sb.classList.toggle("collapsed");
    window.syncSideBtn();
  };
  loadTree();
  const hm = location.hash.match(/[#&]path=([^&]+)/);
  if (hm) { const p = decodeURIComponent(hm[1]); setTimeout(() => loadGame(p), 0); }
}
init();
