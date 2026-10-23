function plyName(index) {
  const n = index + 1;
  const digit = "一二三四五六七八九";
  if (n < 10) return "第" + digit[n - 1] + "步";
  if (n === 10) return "第十步";
  if (n < 20) return "第十" + digit[n - 11] + "步";
  if (n === 20) return "第二十步";
  return "第" + n + "步";
}
const cols = document.getElementById("cols");
const pathLine = document.getElementById("pathLine");
const lead = document.getElementById("lead");
let tree = null;
let picked = [];
const tailFiles = {};

function pct(count, base) {
  if (!base) return "0.00";
  return (count / base * 100).toFixed(2);
}

function sideOf(depth) {
  return depth % 2 === 0 ? "red" : "black";
}

function sideName(depth) {
  return depth % 2 === 0 ? "红方" : "黑方";
}

function render() {
  cols.innerHTML = "";
  const trail = [];
  let nodes = tree.children;
  let parent = tree.total;
  const depthLimit = tree.depth || 10;
  for (let depth = 0; depth < depthLimit && nodes && nodes.length; depth++) {
    const chosen = picked[depth];
    const column = document.createElement("div");
    column.className = "col";
    const title = document.createElement("div");
    title.className = "ply";
    const who = document.createElement("span");
    who.className = "who " + sideOf(depth);
    who.textContent = sideName(depth);
    title.append(who, document.createTextNode(plyName(depth)));
    column.appendChild(title);
    let shown = 0;
    nodes.forEach((node) => {
      shown += node.n;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "move " + sideOf(depth)
        + (chosen === node ? " active" : "")
        + (chosen && chosen !== node ? " dim" : "");
      const share = pct(node.n, parent);
      button.innerHTML =
        `<div class="move-name"><b></b><span></span></div><div class="bar"><i></i></div>`;
      button.querySelector("b").textContent = node.m;
      button.querySelector("span").textContent = share + "%";
      button.querySelector("i").style.width = Math.max(1, Math.min(100, Number(share))) + "%";
      button.onclick = () => {
        picked = picked.slice(0, depth).concat(node);
        render();
        const next = cols.children[depth + 1];
        if (next) next.scrollIntoView({ inline: "end", block: "nearest" });
        if ((node.part || node.tail || node.late) && !node.c && !node._loading) {
          node._loading = true;
          const job = node.part
            ? fetch("move-parts/" + node.part + ".json").then((response) => response.json())
            : node.tail
              ? loadTail(picked[0].part, node.tail)
              : loadLate(picked[0].part, node.late);
          job.then((rows) => {
            node.c = rows;
            node._loading = false;
            render();
          }).catch(() => {
            node._loading = false;
            pathLine.textContent = "这一步没有加载成功。";
          });
        }
      };
      column.appendChild(button);
    });
    const rest = parent - shown;
    if (rest > 0) {
      const note = document.createElement("div");
      note.className = "rest";
      note.textContent = `其余 ${rest.toLocaleString("zh-CN")} 局，${pct(rest, parent)}%`;
      column.appendChild(note);
    }
    cols.appendChild(column);
    if (!chosen) break;
    trail.push(chosen.m);
    if ((chosen.part || chosen.tail || chosen.late) && !chosen.c) {
      const wait = document.createElement("div");
      wait.className = "col";
      const waitTitle = document.createElement("div");
      waitTitle.className = "ply";
      const waitWho = document.createElement("span");
      waitWho.className = "who " + sideOf(depth + 1);
      waitWho.textContent = sideName(depth + 1);
      waitTitle.append(waitWho, document.createTextNode("下一步"));
      const waitNote = document.createElement("div");
      waitNote.className = "rest";
      waitNote.textContent = "正在读取这一步。";
      wait.append(waitTitle, waitNote);
      cols.appendChild(wait);
      break;
    }
    parent = chosen.n;
    nodes = chosen.c || [];
    if (!nodes.length) break;
  }
  if (!trail.length) {
    pathLine.textContent = "先点左边的第一步。";
    return;
  }
  const last = picked[picked.length - 1];
  pathLine.replaceChildren();
  trail.forEach((move, index) => {
    if (index) {
      const arrow = document.createElement("span");
      arrow.className = "path-arrow";
      arrow.textContent = "→";
      pathLine.append(arrow);
    }
    const step = document.createElement("span");
    step.className = "path-step " + sideOf(index);
    const tag = document.createElement("i");
    tag.textContent = sideOf(index) === "red" ? "红" : "黑";
    const name = document.createElement("b");
    name.textContent = move;
    step.append(tag, name);
    pathLine.append(step);
  });
  const meta = document.createElement("span");
  meta.className = "path-meta";
  meta.textContent =
    ` · ${last.n.toLocaleString("zh-CN")} 局 · 占上一步 ${pct(last.n, picked.length > 1 ? picked[picked.length - 2].n : tree.total)}% · 占全部开局 ${pct(last.n, tree.total)}%`;
  pathLine.append(meta);
  drawRoute();
}

function drawRoute() {
  const pickedMoves = [...cols.querySelectorAll(".move.active")];
  if (pickedMoves.length < 2) return;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "route-guide");
  svg.setAttribute("width", String(cols.scrollWidth));
  svg.setAttribute("height", String(cols.scrollHeight));
  const box = cols.getBoundingClientRect();
  const points = pickedMoves.map((el) => {
    const rect = el.getBoundingClientRect();
    return {
      x1: rect.right - box.left + cols.scrollLeft,
      x2: rect.left - box.left + cols.scrollLeft,
      y: rect.top + rect.height / 2 - box.top + cols.scrollTop,
    };
  });
  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i];
    const to = points[i + 1];
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const mid = (from.x1 + to.x2) / 2;
    const d = Math.abs(from.y - to.y) < 2
      ? `M ${from.x1} ${from.y} H ${to.x2}`
      : `M ${from.x1} ${from.y} H ${mid} V ${to.y} H ${to.x2}`;
    path.setAttribute("d", d);
    path.setAttribute("class", "route-line");
    svg.appendChild(path);
  }
  cols.appendChild(svg);
}

function loadSlice(part, key, kind) {
  const id = kind + ":" + part + ":" + key;
  if (!tailFiles[id]) {
    tailFiles[id] = fetch("api/move-tail?part=" + part + "&key=" + key + "&kind=" + kind)
      .then((response) => response.json());
  }
  return tailFiles[id];
}

function loadTail(part, key) {
  return loadSlice(part, key, "tail");
}

function loadLate(part, key) {
  return loadSlice(part, key, "late");
}

fetch("move-tree.json")
  .then((response) => response.json())
  .then((data) => {
    tree = data;
    lead.textContent =
      `标准开局 ${data.total.toLocaleString("zh-CN")} 局，往下看到${plyName(data.depth - 1)}。每一层只列出最常见的 ${data.keep} 种着法，点一步，右边出现下一步，都在这一页。`;
    render();
  })
  .catch(() => {
    lead.textContent = "分叉没有加载成功。先在仓库里运行 python3 build_move_tree.py。";
  });
