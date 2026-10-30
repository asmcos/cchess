"use strict";

const CELL = 46;
const PAD = 36;
const PAGE = 30;
const NUM_CN = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
const PIECE = {
  1: "车", 2: "马", 3: "相", 4: "仕", 5: "帅", 6: "炮", 7: "兵",
  8: "车", 9: "马", 10: "象", 11: "士", 12: "将", 13: "炮", 14: "卒",
};
const PIECE_IMG = {
  1: "red_rook", 2: "red_knight", 3: "red_bishop", 4: "red_advisor", 5: "red_king", 6: "red_cannon", 7: "red_pawn",
  8: "black_rook", 9: "black_knight", 10: "black_bishop", 11: "black_advisor", 12: "black_king", 13: "black_cannon", 14: "black_pawn",
};
const MASK = (1n << 64n) - 1n;

function splitmix(x) {
  x = (x + 0x9E3779B97F4A7C15n) & MASK;
  let z = x;
  z = ((z ^ (z >> 30n)) * 0xBF58476D1CE4E5B9n) & MASK;
  z = ((z ^ (z >> 27n)) * 0x94D049BB133111EBn) & MASK;
  return (z ^ (z >> 31n)) & MASK;
}

const KEYS = [];
for (let i = 0; i < 14 * 90; i++) KEYS.push(splitmix(BigInt(i + 1)));
const SIDE_KEY = splitmix(BigInt(14 * 90 + 1));

const stepInfo = document.getElementById("stepInfo");
const pathLine = document.getElementById("pathLine");
const result = document.getElementById("result");
const svg = document.getElementById("board");

let board = standardBoard();
let side = 0;
let past = [];
let selected = -1;
let offset = 0;
let queryToken = 0;
let lastMove = null;

function signed(value) {
  value &= MASK;
  return value >= (1n << 63n) ? value - (1n << 64n) : value;
}

function hashBoard(pos, who) {
  let value = 0n;
  for (let square = 0; square < 90; square++) {
    const code = pos[square];
    if (code) value ^= KEYS[(code - 1) * 90 + square];
  }
  if (who) value ^= SIDE_KEY;
  return signed(value).toString();
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

function onBoard(col, row) {
  return col >= 0 && col <= 8 && row >= 0 && row <= 9;
}

function owner(code) {
  return code <= 7 ? 0 : 1;
}

function inPalace(col, row, who) {
  if (col < 3 || col > 5) return false;
  return who === 0 ? row >= 7 : row <= 2;
}

function kingsFace(pos, src, des) {
  const next = pos.slice();
  next[des] = next[src];
  next[src] = 0;
  let red = -1;
  let black = -1;
  for (let i = 0; i < 90; i++) {
    if (next[i] === 5) red = i;
    else if (next[i] === 12) black = i;
  }
  if (red < 0 || black < 0 || red % 9 !== black % 9) return false;
  const col = red % 9;
  const top = Math.floor(black / 9);
  const bottom = Math.floor(red / 9);
  for (let row = top + 1; row < bottom; row++) if (next[row * 9 + col]) return false;
  return true;
}

function destinations(pos, src) {
  const code = pos[src];
  if (!code) return [];
  const who = owner(code);
  const kind = who === 0 ? code : code - 7;
  const sc = src % 9;
  const sr = Math.floor(src / 9);
  const out = [];
  const put = (col, row) => {
    if (!onBoard(col, row)) return;
    const occ = pos[row * 9 + col];
    if (occ && owner(occ) === who) return;
    out.push(row * 9 + col);
  };
  if (kind === 5) {
    [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dc, dr]) => {
      const col = sc + dc;
      const row = sr + dr;
      if (inPalace(col, row, who)) put(col, row);
    });
  } else if (kind === 4) {
    [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([dc, dr]) => {
      const col = sc + dc;
      const row = sr + dr;
      if (inPalace(col, row, who)) put(col, row);
    });
  } else if (kind === 3) {
    [[2, 2], [2, -2], [-2, 2], [-2, -2]].forEach(([dc, dr]) => {
      const col = sc + dc;
      const row = sr + dr;
      if (!onBoard(col, row)) return;
      if (who === 0 && row < 5) return;
      if (who === 1 && row > 4) return;
      if (pos[(sr + dr / 2) * 9 + (sc + dc / 2)]) return;
      put(col, row);
    });
  } else if (kind === 2) {
    [[1, 2, 0, 1], [-1, 2, 0, 1], [1, -2, 0, -1], [-1, -2, 0, -1],
      [2, 1, 1, 0], [-2, 1, -1, 0], [2, -1, 1, 0], [-2, -1, -1, 0]].forEach(([dc, dr, lc, lr]) => {
      const col = sc + dc;
      const row = sr + dr;
      if (!onBoard(col, row)) return;
      if (pos[(sr + lr) * 9 + (sc + lc)]) return;
      put(col, row);
    });
  } else if (kind === 1 || kind === 6) {
    [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dc, dr]) => {
      let col = sc + dc;
      let row = sr + dr;
      let jumped = false;
      while (onBoard(col, row)) {
        const occ = pos[row * 9 + col];
        if (kind === 1) {
          if (!occ) out.push(row * 9 + col);
          else {
            if (owner(occ) !== who) out.push(row * 9 + col);
            break;
          }
        } else if (!jumped) {
          if (!occ) out.push(row * 9 + col);
          else jumped = true;
        } else if (occ) {
          if (owner(occ) !== who) out.push(row * 9 + col);
          break;
        }
        col += dc;
        row += dr;
      }
    });
  } else if (kind === 7) {
    const forward = who === 0 ? -1 : 1;
    put(sc, sr + forward);
    const crossed = who === 0 ? sr <= 4 : sr >= 5;
    if (crossed) {
      put(sc - 1, sr);
      put(sc + 1, sr);
    }
  }
  return out.filter((des) => !kingsFace(pos, src, des));
}

function num(count) {
  return count.toLocaleString("zh-CN");
}

function esc(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
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
  const targets = selected >= 0 ? destinations(board, selected) : [];
  let marks = "";
  targets.forEach((des) => {
    const c = des % 9;
    const r = Math.floor(des / 9);
    const x = PAD + c * CELL;
    const y = PAD + r * CELL;
    marks += board[des]
      ? `<circle cx="${x}" cy="${y}" r="16" fill="none" stroke="#b4332a" stroke-width="2.4"/>`
      : `<circle cx="${x}" cy="${y}" r="6" fill="rgba(180,51,42,.55)"/>`;
  });
  if (selected >= 0) {
    const c = selected % 9;
    const r = Math.floor(selected / 9);
    marks += `<circle cx="${PAD + c * CELL}" cy="${PAD + r * CELL}" r="20" fill="none" stroke="#8d6b32" stroke-width="2"/>`;
  }
  if (lastMove) {
    const sr = Math.floor(lastMove.src / 9);
    const sc = lastMove.src % 9;
    marks += `<circle cx="${PAD + sc * CELL}" cy="${PAD + sr * CELL}" r="12" fill="none" stroke="#e60000" stroke-width="1.8" stroke-dasharray="4 3"/>`;
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
  let clicks = "";
  for (let p = 0; p < 90; p++) {
    const c = p % 9;
    const r = Math.floor(p / 9);
    clicks += `<rect data-sq="${p}" x="${PAD + c * CELL - CELL / 2}" y="${PAD + r * CELL - CELL / 2}" width="${CELL}" height="${CELL}" fill="transparent"/>`;
  }
  svg.innerHTML = grid + marks + pieces + clicks;
}

function writePath() {
  if (!past.length) {
    pathLine.textContent = "还没走子。";
    return;
  }
  pathLine.innerHTML = past.map((move, index) => {
    const who = index % 2 === 0 ? "red" : "black";
    const label = who === "red" ? "红" : "黑";
    const arrow = index ? '<span class="path-arrow">→</span>' : "";
    return `${arrow}<span class="path-step ${who}"><i>${label}</i><b>${esc(move.text)}</b></span>`;
  }).join("");
}

function play(src, des) {
  const code = board[src];
  const text = moveText({ src, des, sc: code, who: side }, board);
  past.push({ src, des, cap: board[des], side, text });
  board[des] = code;
  board[src] = 0;
  side ^= 1;
  selected = -1;
  lastMove = { src, des };
  drawBoard();
  writePath();
  stepInfo.textContent = (side === 0 ? "轮到红方" : "轮到黑方");
  lookup(false);
}

function onSquare(square) {
  const code = board[square];
  if (selected < 0) {
    if (code && owner(code) === side) {
      selected = square;
      drawBoard();
    }
    return;
  }
  if (square === selected) {
    selected = -1;
    drawBoard();
    return;
  }
  if (destinations(board, selected).includes(square)) {
    play(selected, square);
    return;
  }
  if (code && owner(code) === side) {
    selected = square;
    drawBoard();
  }
}

function undo() {
  const move = past.pop();
  if (!move) return;
  board[move.src] = board[move.des];
  board[move.des] = move.cap;
  side = move.side;
  selected = -1;
  lastMove = past.length ? { src: past[past.length - 1].src, des: past[past.length - 1].des } : null;
  drawBoard();
  writePath();
  stepInfo.textContent = side === 0 ? "轮到红方" : "轮到黑方";
  lookup(false);
}

function reset() {
  board = standardBoard();
  side = 0;
  past = [];
  selected = -1;
  lastMove = null;
  drawBoard();
  writePath();
  stepInfo.textContent = "轮到红方";
  lookup(false);
}

function playText(text) {
  const hits = findMove(board, text, side);
  if (hits.length !== 1) {
    stepInfo.textContent = text + " 对不上棋盘。";
    return;
  }
  play(hits[0].src, hits[0].des);
}

function paint(data, append) {
  if (data.error) {
    result.innerHTML = `<p class="wait">${esc(data.error)}</p>`;
    return;
  }
  if (!append) result.innerHTML = "";
  if (!append) {
    const who = side === 0 ? "红方" : "黑方";
    const box = document.createElement("div");
    if (!data.n) {
      box.innerHTML = `<p class="stat">库里没有走到这个局面的棋谱。</p><p class="ended">轮到${who}。可以退回上一步。</p>`;
      result.appendChild(box);
      return;
    }
    const continued = data.moves.reduce((sum, row) => sum + row.n, 0);
    const ended = data.n - continued;
    let html = `<p class="stat">${num(data.n)} 局走到这里</p>`;
    html += `<p class="ply-head"><span class="who ${side === 0 ? "red" : "black"}">${who}</span>下一步</p>`;
    if (!data.moves.length) html += `<p class="ended">这些棋谱都在这里结束。</p>`;
    data.moves.forEach((row) => {
      const pct = (row.n / data.n * 100).toFixed(2);
      html += `<button type="button" class="fork on ${side === 0 ? "red" : "black"}" data-move="${esc(row.m)}"><b>${esc(row.m)}</b><span class="meta">${num(row.n)} 局 · ${pct}%</span></button>`;
    });
    if (ended > 0 && data.moves.length) html += `<p class="ended">另有 ${num(ended)} 局在这里结束。</p>`;
    html += `<p class="ply-head">对上的棋谱</p><div class="games" id="games"></div>`;
    box.innerHTML = html;
    result.appendChild(box);
  }
  const games = document.getElementById("games");
  data.games.forEach((game) => {
    const link = document.createElement("a");
    link.href = "/qipu#path=" + encodeURIComponent(game.path);
    link.innerHTML = `${esc(game.name)}<small>${game.ply ? "走到第 " + game.ply + " 步" : "开局"}</small>`;
    games.appendChild(link);
  });
  const old = document.getElementById("moreGames");
  if (old) old.remove();
  offset = data.offset + data.games.length;
  if (offset < data.total) {
    const button = document.createElement("button");
    button.type = "button";
    button.id = "moreGames";
    button.className = "more";
    button.textContent = "再看一些棋谱";
    button.onclick = () => lookup(true);
    games.after(button);
  }
}

async function lookup(append) {
  const token = ++queryToken;
  const hash = hashBoard(board, side);
  if (!append) {
    offset = 0;
    result.innerHTML = `<p class="wait">正在查找这个局面。</p>`;
  }
  const response = await fetch("api/pos?hash=" + encodeURIComponent(hash) + "&offset=" + offset + "&limit=" + PAGE);
  const data = await response.json();
  if (token !== queryToken) return;
  paint(data, append);
}

svg.addEventListener("click", (event) => {
  const node = event.target.closest("[data-sq]");
  if (!node) return;
  onSquare(Number(node.getAttribute("data-sq")));
});
document.getElementById("btnPrev").onclick = undo;
document.getElementById("btnReset").onclick = reset;
result.addEventListener("click", (event) => {
  const button = event.target.closest("[data-move]");
  if (!button) return;
  playText(button.getAttribute("data-move"));
});

drawBoard();
lookup(false);
