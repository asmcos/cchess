/*
 * 中国象棋棋谱浏览器 — 前端逻辑
 * ==================================================
 * 数据流：
 *   GET /api/tree          -> 目录树（棋谱库视图，按目录浏览）
 *   GET /api/index         -> 开局索引（含一级 opening + 二级 opening2）
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
let openingMap = {}, countByOpening = {}, filterOpening = "", treeData = null, titleMap = {};
let catGames = [], currentView = "lib";
const ORDER1 = ["中炮局","仙人指路","起马局","飞相局","过宫炮局","仕角炮局","上士局","其它开局","残局","排局","无着法"];

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
  const b = init.slice();
  const arr = data.moves.map((vstr, i) => {
    const m = decodeInt(vstr);
    m.id = i;
    m.text = moveText(m, b);
    m.parent = data.parent && data.parent[i] !== undefined ? data.parent[i] : i - 1;
    b[m.src] = 0; b[m.des] = m.sc;   // 更新局面供下一步着法文本计算
    return m;
  });
  return { init, arr };
}

// ---------- 导航 ----------
function goto(i) {
  cur = Math.max(-1, Math.min(moves.length - 1, i));
  // 重放局面
  board = initBoard.slice();
  for (let k = 0; k <= cur; k++) {
    const m = moves[k];
    board[m.src] = 0; board[m.des] = m.sc;
  }
  renderPieces();
  document.getElementById("stepInfo").textContent = `${cur + 1} / ${moves.length}`;
  const tip = document.getElementById("moveTip");
  // 移动端：初始局面的提示文字不显示（省空间）
  tip.textContent = cur >= 0 ? `第${cur + 1}步  ${moves[cur].text}` : (window.innerWidth <= 900 ? "" : "初始局面");
  // 着法列表高亮 + 滚动
  document.querySelectorAll(".move-item").forEach(el => el.classList.toggle("current", +el.dataset.id === cur));
  const act = document.querySelector(`.move-item[data-id="${cur}"]`);
  if (act && act.scrollIntoView) act.scrollIntoView({ block: "nearest" });
  // 注解
  const cb = document.getElementById("commentBox");
  const cmt = cur >= 0 ? commentMap[cur] : null;
  if (cmt) { cb.style.display = "block"; cb.textContent = cmt; }
  else cb.style.display = "none";
}

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

// ---------- 棋谱加载 ----------
async function loadGame(path) {
  const resp = await fetch("./api/game?path=" + encodeURIComponent(path));
  const data = await resp.json();
  if (data.error) { alert(data.error); return; }
  const { init, arr } = buildMoves(data);
  initBoard = init; moves = arr; cur = -1;
  commentMap = {};
  Object.entries(data.comment || {}).forEach(([k, v]) => commentMap[+k] = v);
  const info = data.info || {};
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
  if (data.annotate) { document.getElementById("commentBox").style.display = "block"; document.getElementById("commentBox").textContent = data.annotate; }
  renderMoveList();
  goto(-1);
  // 同步地址栏 hash，便于分享/讨论同一棋谱（不污染浏览器历史）
  try { history.replaceState(null, "", "#path=" + encodeURIComponent(path)); } catch (e) {}
  // 移动端：点棋谱后自动滚动到棋盘区，并把顶部列表收起（点击标签可再展开）
  if (window.innerWidth <= 900) {
    const el = document.getElementById("stageRow");
    if (el && el.scrollIntoView) setTimeout(() => el.scrollIntoView({ block: "start" }), 60);
    const sb = document.getElementById("sidebar");
    if (sb) sb.classList.add("collapsed");
  }
}

// ---------- 目录树 ----------
function renderTree(node, container, depth) {
  if (node.children) {
    const row = document.createElement("div");
    row.className = "tree-folder";
    row.style.paddingLeft = (10 + depth * 14) + "px";
    const toggle = document.createElement("span");
    toggle.className = "tree-toggle"; toggle.textContent = depth === 0 ? "▼" : "▸";
    const countFiles = (n) => (n.children ? n.children.reduce((s, c) => s + countFiles(c), 0) : 1);
    const cnt = countFiles(node);
    row.innerHTML = `<span class="tree-toggle">${depth===0?"▼":"▸"}</span>${node.label}<span class="tree-count">${cnt}</span>`;
    const sub = document.createElement("div");
    sub.className = "tree-node";
    const expanded = depth === 0;
    if (expanded) sub.style.display = "block"; else sub.style.display = "none";
    node.children.forEach(c => renderTree(c, sub, depth + 1));
    row.onclick = (e) => {
      e.stopPropagation();
      if (sub.style.display === "none") { sub.style.display = "block"; row.children[0].textContent = "▼"; }
      else { sub.style.display = "none"; row.children[0].textContent = "▸"; }
    };
    container.appendChild(row);
    container.appendChild(sub);
  } else {
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
    row.onclick = () => {
      document.querySelectorAll(".tree-file").forEach(el => el.classList.remove("active"));
      row.classList.add("active");
      loadGame(node.path);
    };
    container.appendChild(row);
  }
}

function filterTree(node) {
  if (node.children) {
    const ch = node.children.map(filterTree).filter(Boolean);
    if (ch.length === 0) return null;
    return { label: node.label, children: ch };
  } else {
    if (filterOpening && openingMap[node.path] !== filterOpening) return null;
    return node;
  }
}
function countFilesAll(n) {
  return n.children ? n.children.reduce((s, c) => s + countFilesAll(c), 0) : 1;
}
function renderTreeData() {
  const root = filterOpening ? filterTree(treeData) : treeData;
  const box = document.getElementById("tree");
  box.innerHTML = "";
  if (root) renderTree(root, box, 0);
  const sel = document.getElementById("openingFilter");
  if (sel) sel.value = filterOpening;
  const total = treeData ? countFilesAll(treeData) : 0;
  const matched = filterOpening ? (countByOpening[filterOpening] || 0) : total;
  const el = document.getElementById("filterCount");
  if (el) el.textContent = matched ? `${matched} 局` : "";
}
async function loadTree() {
  const [tresp, iresp, titresp] = await Promise.all([
    fetch("./api/tree"),
    fetch("./api/index").then(r => r.json()).catch(() => ({ games: [] })),
    fetch("./api/title").then(r => r.json()).catch(() => ({})),
  ]);
  treeData = await tresp.json();
  titleMap = titresp && !titresp.error ? titresp : {};
  const idx = iresp;
  openingMap = {}; countByOpening = {};
  catGames = idx.games || [];
  (idx.games || []).forEach(g => {
    openingMap[g.path] = g.opening;
    countByOpening[g.opening] = (countByOpening[g.opening] || 0) + 1;
  });
  const sel = document.getElementById("openingFilter");
  if (sel) {
    sel.innerHTML = `<option value="">全部开局</option>` +
      (idx.openings || Object.keys(countByOpening)).map(o =>
        `<option value="${o}">${o} (${countByOpening[o] || 0})</option>`).join("");
    sel.onchange = () => { filterOpening = sel.value; renderTreeData(); };
  }
  renderTreeData();
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
  if (v === "lib") renderTreeData();
  else renderCatTree();
}
function renderCatTree() {
  const by1 = {};
  (catGames || []).forEach(g => {
    const l1 = g.opening || "未分类", l2 = g.opening2 || "未分类";
    (by1[l1] = by1[l1] || {})[l2] = (by1[l1][l2] || 0) + 1;
  });
  const box = document.getElementById("tree");
  box.innerHTML = "";
  const l1s = Object.keys(by1).sort((a, b) => orderIdx(a) - orderIdx(b));
  l1s.forEach(l1 => {
    const tot = Object.values(by1[l1]).reduce((s, x) => s + x, 0);
    const row = document.createElement("div");
    row.className = "tree-folder"; row.style.paddingLeft = "10px";
    const toggle = document.createElement("span");
    toggle.className = "tree-toggle"; toggle.textContent = "▸";
    row.appendChild(toggle);
    row.appendChild(document.createTextNode(l1));
    const cnt = document.createElement("span"); cnt.className = "tree-count"; cnt.textContent = String(tot);
    row.appendChild(cnt);
    box.appendChild(row);
    const sub = document.createElement("div");
    sub.className = "tree-node"; sub.style.display = "none";   // 默认收起
    row.onclick = (e) => {
      e.stopPropagation();
      if (sub.style.display === "none") { sub.style.display = "block"; toggle.textContent = "▼"; }
      else { sub.style.display = "none"; toggle.textContent = "▸"; }
    };
    Object.keys(by1[l1]).sort().forEach(l2 => {
      const n = by1[l1][l2];
      const r2 = document.createElement("div");
      r2.className = "tree-file cat2"; r2.style.paddingLeft = "24px";
      r2.innerHTML = `<span>${l2}</span><span class="tree-count">${n}</span>`;
      r2.onclick = (e) => {
        e.stopPropagation();
        document.querySelectorAll(".cat2").forEach(x => x.classList.remove("active"));
        r2.classList.add("active");
        showCatGames(l1, l2);
      };
      sub.appendChild(r2);
    });
    box.appendChild(sub);
  });
}
function showCatGames(l1, l2) {
  const list = (catGames || []).filter(g => g.opening === l1 && (g.opening2 || "未分类") === l2);
  const box = document.getElementById("catList");
  box.innerHTML = `<div class="cat-head">${l1} · ${l2}（${list.length} 局）</div>`;
  list.forEach(g => {
    const r = document.createElement("div"); r.className = "cat-game";
    r.innerHTML = `<span class="cat-g-name">${g.name}</span>` +
      (titleMap[g.path] && titleMap[g.path] !== g.name ? `<span class="cat-g-title">${titleMap[g.path]}</span>` : "") +
      `<span class="cat-g-meta">${g.red || ""}${g.black ? (" vs " + g.black) : ""}</span>`;
    r.onclick = () => {
      document.querySelectorAll(".cat-game").forEach(x => x.classList.remove("active"));
      r.classList.add("active");
      loadGame(g.path);
    };
    box.appendChild(r);
  });
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
// 用户练的一方：红视角练红(0)，黑视角(反转)练黑(1)；系统自动走对方
function userSide() { return viewFlip ? 1 : 0; }
function systemSide() { return viewFlip ? 0 : 1; }
// 系统自动走对手，直到轮到用户方或棋局结束
function autoAdvance() {
  while (moves[cur + 1] && moves[cur + 1].who === systemSide()) goto(cur + 1);
  if (!moves[cur + 1]) memTip("🎉 整局背谱完成！", true);
  else memTip("正确！轮到你走" + (moves[cur + 1].who === 0 ? "红" : "黑") + "方", true);
}
// 进入背谱，startN=从第 startN 步开始背（>=1）：先自动播到前一步，再轮到用户
function enterMem(startN) {
  memMode = true; selPiece = null;
  const b = document.getElementById("btnMem"); if (b) b.classList.add("active");
  if (startN <= 1) goto(-1);
  else goto(startN - 2);
  autoAdvance();
}
function openMemModal() {
  const from = document.getElementById("memFrom"), lim = document.getElementById("memLimit");
  from.value = 1; lim.value = 15;                                // 统一默认 15（短棋谱在确认时按实际步数截断）
  from.disabled = true; lim.disabled = false;                 // 默认随机
  document.getElementById("memRand").checked = true;          // 默认勾选随机
  document.getElementById("memModal").style.display = "flex";
}
function closeMemModal() {
  document.getElementById("memModal").style.display = "none";
}
function startMemFromModal() {
  const rand = document.getElementById("memRand").checked;
  let startN = 1;
  if (rand) {
    let M = parseInt(document.getElementById("memLimit").value, 10) || 15;
    M = Math.max(1, Math.min(M, moves.length));
    startN = 1 + Math.floor(Math.random() * M);   // 1..M 随机
  } else {
    startN = parseInt(document.getElementById("memFrom").value, 10) || 1;
  }
  startN = Math.max(1, Math.min(startN, moves.length));
  closeMemModal();
  enterMem(startN);
}
function onCell(c, rr) {
  if (!memMode || !moves.length) return;
  if (moves[cur + 1] && moves[cur + 1].who !== userSide()) { autoAdvance(); return; }
  const r = viewFlip ? 9 - rr : rr;
  const p = r * 9 + c;
  const next = moves[cur + 1];
  if (!next) { memTip("🎉 整局背谱完成！", true); return; }
  const code = board[p];
  if (code && (code <= 7) === (userSide() === 0)) { selPiece = p; renderPieces(); return; }
  if (selPiece !== null) {
    if (selPiece === next.src && p === next.des) {
      goto(cur + 1);                    // 应用用户这步
      selPiece = null; renderPieces();
      autoAdvance();                    // 系统自动走对手，直到轮到用户
    } else {
      selPiece = null; renderPieces();
      memTip("走错了！原谱第" + (cur + 2) + "步：" + next.text + "，请重走", false);
      showToast("走错了！原谱第" + (cur + 2) + "步：" + next.text);
    }
  }
}

// ---------- 控制 ----------
function bindControls() {
  const $ = id => document.getElementById(id);
  const nav = (fn) => () => { exitMem(); fn(); };   // 导航操作时退出背谱
  $("btnFirst").onclick = nav(() => goto(-1));
  $("btnPrev").onclick = nav(() => goto(cur - 1));
  $("btnNext").onclick = nav(() => goto(cur + 1));
  $("btnLast").onclick = nav(() => goto(moves.length - 1));
  $("btnReset").onclick = () => goto(-1);
  $("btnMem").onclick = () => {
    if (!moves.length) { alert("请先选择一个棋谱再进入背谱"); return; }
    if (memMode) { exitMem(); goto(-1); return; }
    openMemModal();   // 弹框选择起点：指定步数或随机
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
      if (cur >= moves.length - 1) { clearInterval(playTimer); playTimer = null; $("btnPlay").textContent = "▶▶"; return; }
      goto(cur + 1);
    }, 900);
  };
  window.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { exitMem(); goto(cur + 1); }
    else if (e.key === "ArrowLeft") { exitMem(); goto(cur - 1); }
    else if (e.key === "ArrowUp") { exitMem(); goto(cur + 5); }
    else if (e.key === "ArrowDown") { exitMem(); goto(cur - 5); }
  });
}

// ---------- 启动 ----------
function init() {
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  // 透明点击层：9×10 格，每格一个可点击矩形，供背谱模式走子
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
  loadTree();
  // 从地址栏 hash 自动加载棋谱（分享链接直达同一棋谱）
  const hm = location.hash.match(/[#&]path=([^&]+)/);
  if (hm) { const p = decodeURIComponent(hm[1]); setTimeout(() => loadGame(p), 0); }
}
init();
