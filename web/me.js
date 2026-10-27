"use strict";

const KEY = "xqbook.me";
const PIECES = ["帅", "车", "马", "炮", "相", "仕", "兵", "将", "卒"];
const COLORS = ["#b4332a", "#221910", "#8d6b32", "#6b4124", "#8d261f", "#4a3b2d"];
const nameInput = document.getElementById("name");
const avatar = document.getElementById("avatar");
const saved = document.getElementById("saved");

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw);
  } catch (err) {
    return null;
  }
  return null;
}

function store(profile) {
  localStorage.setItem(KEY, JSON.stringify(profile));
}

function paint(profile) {
  const piece = PIECES[profile.seed % PIECES.length];
  const color = COLORS[Math.floor(profile.seed / PIECES.length) % COLORS.length];
  avatar.textContent = piece;
  avatar.style.background = color;
  nameInput.value = profile.name;
}

function freshSeed() {
  const span = PIECES.length * COLORS.length;
  return Math.floor(Math.random() * span);
}

let profile = load();
if (!profile || typeof profile.seed !== "number" || typeof profile.name !== "string") {
  profile = { name: "棋友", seed: freshSeed() };
  store(profile);
}
paint(profile);

function rememberName() {
  const next = nameInput.value.trim() || "棋友";
  profile.name = next;
  nameInput.value = next;
  store(profile);
  saved.textContent = "已存在这台浏览器。";
}

document.getElementById("save").onclick = rememberName;
nameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") rememberName();
});

avatar.onclick = () => {
  let seed = freshSeed();
  if (seed === profile.seed) seed = (seed + 1) % (PIECES.length * COLORS.length);
  profile.seed = seed;
  store(profile);
  paint(profile);
  saved.textContent = "头像已换，存在这台浏览器。";
};
