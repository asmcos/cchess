"use strict";

const CELL = 46;
const PAD = 36;
const NUM_CN = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
const PIECE = {
  1: "车", 2: "马", 3: "相", 4: "仕", 5: "帅", 6: "炮", 7: "兵",
  8: "车", 9: "马", 10: "象", 11: "士", 12: "将", 13: "炮", 14: "卒",
};
const PIECE_IMG = {
  1: "red_rook", 2: "red_knight", 3: "red_bishop", 4: "red_advisor", 5: "red_king", 6: "red_cannon", 7: "red_pawn",
  8: "black_rook", 9: "black_knight", 10: "black_bishop", 11: "black_advisor", 12: "black_king", 13: "black_cannon", 14: "black_pawn",
};

const lead = document.getElementById("lead");
const stepInfo = document.getElementById("stepInfo");
const pathLine = document.getElementById("pathLine");
const plies = document.getElementById("plies");
const svg = document.getElementById("board");
const pageMove = document.body.dataset.move || "炮二平五";
const pageFamily = document.body.dataset.family || pageMove;
const pageOther = document.body.dataset.other || "";

let tree = null;
let root = null;
let mainLine = [];
let path = [];
let cursor = 0;
let board = [];
let lastMove = null;
let partReady = null;
let fillToken = 0;
let openingText = "";
const slices = {};

function plyName(index) {
  const n = index + 1;
  const digit = "一二三四五六七八九";
  if (n < 10) return "第" + digit[n - 1] + "步";
  if (n === 10) return "第十步";
  if (n < 20) return "第十" + digit[n - 11] + "步";
  if (n === 20) return "第二十步";
  return "第" + n + "步";
}

function sideOf(depth) {
  return depth % 2 === 0 ? "red" : "black";
}

function sideName(depth) {
  return depth % 2 === 0 ? "红方" : "黑方";
}

function pct(count, base) {
  if (!base) return "0.00";
  return (count / base * 100).toFixed(2);
}

function num(count) {
  return count.toLocaleString("zh-CN");
}

function standardBoard() {
  const next = new Array(90).fill(0);
  [1, 2, 3, 4, 5, 4, 3, 2, 1].forEach((code, col) => { next[81 + col] = code; });
  [8, 9, 10, 11, 12, 11, 10, 9, 8].forEach((code, col) => { next[col] = code; });
  next[7 * 9 + 1] = next[7 * 9 + 7] = 6;
  next[2 * 9 + 1] = next[2 * 9 + 7] = 13;
  [0, 2, 4, 6, 8].forEach((col) => {
    next[6 * 9 + col] = 7;
    next[3 * 9 + col] = 14;
  });
  return next;
}

function moveText(move, pos) {
  const srcC = move.src % 9;
  const srcR = Math.floor(move.src / 9);
  const desC = move.des % 9;
  const desR = Math.floor(move.des / 9);
  const name = PIECE[move.sc] || "?";
  const srcFile = move.who === 0 ? NUM_CN[9 - srcC] : String(srcC + 1);
  const desFile = move.who === 0 ? NUM_CN[9 - desC] : String(desC + 1);
  const same = [];
  for (let p = 0; p < 90; p++) {
    if (p !== move.src && p % 9 === srcC && pos[p] === move.sc) same.push(p);
  }
  let prefix = "";
  if (same.length) {
    const rows = same.map((p) => Math.floor(p / 9));
    const minR = Math.min(...rows);
    const maxR = Math.max(...rows);
    if (move.who === 0) prefix = srcR === minR ? "前" : (srcR === maxR ? "后" : "中");
    else prefix = srcR === maxR ? "前" : (srcR === minR ? "后" : "中");
  }
  let action;
  if (srcC === desC) {
    const forward = move.who === 0 ? desR < srcR : desR > srcR;
    action = (forward ? "进" : "退") + NUM_CN[Math.abs(desR - srcR)];
  } else {
    const forward = move.who === 0 ? desR < srcR : desR > srcR;
    const oblique = [2, 3, 4, 9, 10, 11].includes(move.sc);
    action = oblique ? (forward ? "进" : "退") + desFile : "平" + desFile;
  }
  return prefix ? prefix + name + action : name + srcFile + action;
}

function fileCol(token) {
  if (/[1-9]/.test(token)) return Number(token) - 1;
  return 8 - "一二三四五六七八九".indexOf(token);
}

function parseStep(text) {
  const matched = text.match(/^(前|中|后)?(车|马|相|象|仕|士|帅|将|炮|兵|卒)([一二三四五六七八九1-9])?(进|退|平)([一二三四五六七八九1-9])$/);
  if (!matched) return null;
  return {
    prefix: matched[1] || "",
    name: matched[2],
    srcFile: matched[3] || "",
    verb: matched[4],
    target: matched[5],
  };
}

function findMove(pos, text, who) {
  const step = parseStep(text);
  if (!step) return [];
  const names = who === 0
    ? { 车: 1, 马: 2, 相: 3, 仕: 4, 帅: 5, 炮: 6, 兵: 7 }
    : { 车: 8, 马: 9, 象: 10, 士: 11, 将: 12, 炮: 13, 卒: 14 };
  const code = names[step.name];
  if (!code) return [];
  let candidates = [];
  for (let p = 0; p < 90; p++) if (pos[p] === code) candidates.push(p);
  if (step.srcFile) {
    const col = fileCol(step.srcFile);
    candidates = candidates.filter((p) => p % 9 === col);
  } else if (step.prefix) {
    candidates = candidates.filter((p) => {
      const col = p % 9;
      const peers = [];
      for (let q = 0; q < 90; q++) if (q !== p && pos[q] === code && q % 9 === col) peers.push(q);
      if (!peers.length) return false;
      const row = Math.floor(p / 9);
      const rows = peers.map((q) => Math.floor(q / 9));
      const minR = Math.min(...rows);
      const maxR = Math.max(...rows);
      const label = who === 0
        ? (row === minR ? "前" : (row === maxR ? "后" : "中"))
        : (row === maxR ? "前" : (row === minR ? "后" : "中"));
      return label === step.prefix;
    });
  }
  const forward = who === 0 ? -1 : 1;
  const hits = [];
  candidates.forEach((src) => {
    const srcC = src % 9;
    const srcR = Math.floor(src / 9);
    let des = -1;
    if (step.verb === "平") {
      des = srcR * 9 + fileCol(step.target);
    } else if ([2, 3, 4, 9, 10, 11].includes(code)) {
      const desC = fileCol(step.target);
      const dc = desC - srcC;
      const dir = step.verb === "进" ? forward : -forward;
      let dr = dir;
      if (code === 2 || code === 9) dr = dir * (Math.abs(dc) === 1 ? 2 : 1);
      else if (code === 3 || code === 10) dr = dir * 2;
      const desR = srcR + dr;
      if (desR >= 0 && desR <= 9) des = desR * 9 + desC;
    } else {
      const dist = "零一二三四五六七八九".indexOf(step.target);
      const dir = step.verb === "进" ? forward : -forward;
      const desR = srcR + dir * dist;
      if (desR >= 0 && desR <= 9) des = desR * 9 + srcC;
    }
    if (des < 0 || des === src) return;
    const occ = pos[des];
    if (occ && (occ <= 7 ? 0 : 1) === who) return;
    const move = { src, des, sc: code, who };
    if (moveText(move, pos) === text) hits.push(move);
  });
  return hits;
}

function replay() {
  board = standardBoard();
  lastMove = null;
  for (let i = 0; i < cursor; i++) {
    const hits = findMove(board, path[i].m, i % 2 === 0 ? 0 : 1);
    if (hits.length !== 1) {
      stepInfo.textContent = path[i].m + " 对不上棋盘。";
      return false;
    }
    const move = hits[0];
    board[move.des] = move.sc;
    board[move.src] = 0;
    lastMove = move;
  }
  return true;
}

function drawBoard() {
  const line = (x1, y1, x2, y2) =>
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#7a4a1f" stroke-width="1.4"/>`;
  let grid = "";
  for (let r = 0; r <= 9; r++) grid += line(PAD, PAD + r * CELL, PAD + 8 * CELL, PAD + r * CELL);
  for (let c = 0; c <= 8; c++) {
    const x = PAD + c * CELL;
    if (c === 0 || c === 8) grid += line(x, PAD, x, PAD + 9 * CELL);
    else {
      grid += line(x, PAD, x, PAD + 4 * CELL);
      grid += line(x, PAD + 5 * CELL, x, PAD + 9 * CELL);
    }
  }
  const diag = (c1, r1, c2, r2) => line(PAD + c1 * CELL, PAD + r1 * CELL, PAD + c2 * CELL, PAD + r2 * CELL);
  grid += diag(3, 0, 5, 2) + diag(5, 0, 3, 2) + diag(3, 7, 5, 9) + diag(5, 7, 3, 9);
  grid += `<text x="${PAD + 2 * CELL}" y="${PAD + 4.62 * CELL}" font-size="18" fill="#7a4a1f" text-anchor="middle">楚 河</text>`;
  grid += `<text x="${PAD + 6 * CELL}" y="${PAD + 4.62 * CELL}" font-size="18" fill="#7a4a1f" text-anchor="middle">汉 界</text>`;
  let marks = "";
  if (lastMove) {
    const sr = Math.floor(lastMove.src / 9);
    const sc = lastMove.src % 9;
    marks = `<circle cx="${PAD + sc * CELL}" cy="${PAD + sr * CELL}" r="12" fill="none" stroke="#e60000" stroke-width="1.8" stroke-dasharray="4 3"/>`;
  }
  const pieces = board.map((code, p) => {
    if (!code) return "";
    const c = p % 9;
    const r = Math.floor(p / 9);
    const x = PAD + c * CELL;
    const y = PAD + r * CELL;
    const s = CELL * 0.9;
    const halo = lastMove && p === lastMove.des
      ? `<circle cx="${x}" cy="${y}" r="${s * 0.52}" fill="rgba(255,215,0,0.28)" stroke="#e60000" stroke-width="2"/>`
      : "";
    return `${halo}<image href="pieces/wood/${PIECE_IMG[code]}.svg" x="${x - s / 2}" y="${y - s / 2}" width="${s}" height="${s}"/>`;
  }).join("");
  svg.innerHTML = grid + marks + pieces;
}

function loadSlice(part, key, kind) {
  const id = kind + ":" + part + ":" + key;
  if (!slices[id]) {
    slices[id] = fetch("api/move-tail?part=" + part + "&key=" + key + "&kind=" + kind)
      .then((response) => response.json());
  }
  return slices[id];
}

async function ensureChildren(node) {
  if (node.c) return node.c;
  if (node.part && partReady) {
    await partReady;
    if (node.c) return node.c;
  }
  if (node.tail) {
    node.c = await loadSlice(root.part, node.tail, "tail");
    return node.c;
  }
  if (node.late) {
    node.c = await loadSlice(root.part, node.late, "late");
    return node.c;
  }
  node.c = [];
  return node.c;
}

function absorbLoaded(node) {
  let current = node;
  while (path.length < 20 && Array.isArray(current.c) && current.c.length) {
    current = current.c[0];
    path.push(current);
  }
}

async function pullUntil(limit) {
  while (path.length < limit) {
    const node = path[path.length - 1];
    const before = path.length;
    if (!Array.isArray(node.c)) await ensureChildren(node);
    absorbLoaded(node);
    if (path.length === before) break;
  }
}

async function extendFirst(node, slots) {
  const out = [];
  let current = node;
  for (let i = 0; i < slots; i++) {
    const kids = await ensureChildren(current);
    if (!Array.isArray(kids) || !kids.length) break;
    current = kids[0];
    out.push(current);
  }
  return out;
}

function renderPath() {
  pathLine.replaceChildren();
  if (!cursor) {
    pathLine.textContent = "棋盘还在开局。点下一步，或点右边的一种着法。";
    return;
  }
  for (let i = 0; i < cursor; i++) {
    if (i) {
      const arrow = document.createElement("span");
      arrow.className = "path-arrow";
      arrow.textContent = "→";
      pathLine.append(arrow);
    }
    const step = document.createElement("span");
    step.className = "path-step " + sideOf(i);
    const tag = document.createElement("i");
    tag.textContent = sideOf(i) === "red" ? "红" : "黑";
    const name = document.createElement("b");
    name.textContent = path[i].m;
    step.append(tag, name);
    pathLine.append(step);
  }
}

function render() {
  const ok = replay();
  drawBoard();
  if (!ok) return;
  const reached = cursor ? path[cursor - 1] : null;
  if (!reached) stepInfo.textContent = "开局局面 · " + pageMove + "共 " + num(root.n) + " 局";
  else {
    const prev = cursor > 1 ? path[cursor - 2].n : tree.total;
    stepInfo.textContent = plyName(cursor - 1) + " " + sideName(cursor - 1) + " " + reached.m
      + " · " + num(reached.n) + " 局 · 占上一步 " + pct(reached.n, prev) + "%";
  }
  renderPath();
  plies.innerHTML = "";
  path.forEach((node, depth) => {
    const block = document.createElement("div");
    block.className = "ply";
    const head = document.createElement("div");
    head.className = "ply-head";
    const who = document.createElement("span");
    who.className = "who " + sideOf(depth);
    who.textContent = sideName(depth);
    head.append(who, document.createTextNode(plyName(depth)));
    if (depth === cursor) head.append(document.createTextNode(" · 接着从这里走"));
    block.append(head);
    const choices = depth === 0 ? [root] : (path[depth - 1].c || []);
    const parentCount = depth === 0 ? tree.total : path[depth - 1].n;
    choices.forEach((choice) => {
      const button = document.createElement("button");
      button.type = "button";
      const chosen = choice === node;
      button.className = "fork " + sideOf(depth)
        + (chosen ? " on" : " dim")
        + (depth === cursor - 1 ? " here" : "");
      const title = document.createElement("b");
      title.textContent = choice.m + (choice === choices[0] ? " · 最常见" : "");
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = num(choice.n) + " 局 · " + pct(choice.n, parentCount) + "%";
      button.append(title, meta);
      button.onclick = () => { choose(depth, choice); };
      block.append(button);
    });
    plies.append(block);
  });
  const tip = path[path.length - 1];
  if (path.length < 20 && tip && !Array.isArray(tip.c)) {
    const note = document.createElement("div");
    note.className = "wait";
    note.textContent = "后面的分叉还在读取。";
    plies.append(note);
  }
}

async function choose(depth, choice) {
  const first = depth === 0 ? root : (path[depth - 1].c || [])[0];
  if (choice !== first) fillToken += 1;
  const token = fillToken;
  if (!choice.c && (choice.tail || choice.late || choice.part)) {
    stepInfo.textContent = "正在读取这一步。";
  }
  const rest = await extendFirst(choice, 19 - depth);
  if (token !== fillToken) return;
  path = path.slice(0, depth).concat(choice, rest);
  cursor = depth + 1;
  render();
}

async function goNext() {
  if (!root) return;
  if (cursor < path.length) {
    cursor += 1;
    render();
    return;
  }
  if (path.length >= 20) return;
  stepInfo.textContent = "正在读取下一步。";
  const token = fillToken;
  await pullUntil(path.length + 1);
  if (token !== fillToken) return;
  if (cursor < path.length) cursor += 1;
  render();
}

async function goEnd() {
  if (!root) return;
  if (path.length < 20) stepInfo.textContent = "正在读取后面的步。";
  const token = fillToken;
  await pullUntil(20);
  if (token !== fillToken) return;
  cursor = path.length;
  render();
}

document.getElementById("btnStart").onclick = () => { cursor = 0; render(); };
document.getElementById("btnPrev").onclick = () => { if (cursor) { cursor -= 1; render(); } };
document.getElementById("btnNext").onclick = () => { goNext(); };
document.getElementById("btnEnd").onclick = () => { goEnd(); };

function writeOpening(data, other) {
  openingText = "标准开局 " + num(data.total) + " 局。";
  if (other) {
    openingText += pageFamily + "共 " + num(root.n + other.n) + " 局，其中" + pageMove + " "
      + num(root.n) + " 局，" + pageOther + " " + num(other.n) + " 局。";
  } else {
    openingText += pageMove + " " + num(root.n) + " 局。";
  }
  openingText += "先走第一步。后面每一层的分叉分步读取，点一种就能在棋盘上试。";
  lead.textContent = openingText;
}

function writeLongest(end) {
  lead.textContent = openingText + "顺着最常见的一路走到" + plyName(mainLine.length - 1)
    + "，这一路还有 " + num(end.n) + " 局，占" + pageMove + " " + pct(end.n, root.n)
    + "%，占全部标准开局 " + pct(end.n, tree.total) + "%。";
}

fetch("move-tree.json")
  .then((response) => response.json())
  .then((data) => {
    tree = data;
    root = data.children.find((item) => item.m === pageMove);
    if (!root) {
      lead.textContent = pageMove + " 不在已经算好的前十种第一步里。";
      return;
    }
    const other = pageOther ? data.children.find((item) => item.m === pageOther) : null;
    path = [root];
    mainLine = path;
    writeOpening(data, other);
    cursor = 0;
    render();
    const token = fillToken;
    partReady = fetch("move-parts/" + root.part + ".json")
      .then((response) => response.json())
      .then(async (rows) => {
        if (token !== fillToken) return;
        root.c = rows;
        absorbLoaded(root);
        mainLine = path.slice();
        render();
        const rest = await extendFirst(root, 19);
        if (token !== fillToken) return;
        mainLine = [root].concat(rest);
        path = mainLine.slice();
        writeLongest(mainLine[mainLine.length - 1]);
        render();
      });
    return partReady;
  })
  .catch(() => {
    lead.textContent = pageMove + "分叉没有加载成功。";
  });
