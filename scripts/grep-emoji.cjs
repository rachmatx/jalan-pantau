#!/usr/bin/env node
/* Zero-emoji guard: exits 1 if any file contains emoji / dingbat unicode.
   Usage: node scripts/grep-emoji.cjs <file> [file ...] */
const fs = require("fs");

// Emoji + dingbats + symbols + arrows + geometric shapes + misc symbols,
// minus legit punctuation used in this project.
const RANGES = [
  [0x1f000, 0x1faff],
  [0x2600, 0x26ff],
  [0x2700, 0x27bf],
  [0x2b00, 0x2bff],
  [0xfe0f, 0xfe0f],
  [0x2049, 0x2049],
  [0x203c, 0x203c],
  [0x2190, 0x21ff],
];

const ALLOW = new Set(["\u2192"]); // → arrow in prose (teks deskripsi alur)

let bad = 0;
for (const path of process.argv.slice(2)) {
  if (!fs.existsSync(path)) { console.error(`[skip] ${path} (tidak ada)`); continue; }
  const text = fs.readFileSync(path, "utf8");
  for (let i = 0; i < text.length; i++) {
    const cp = text.codePointAt(i);
    if (cp > 0xffff) i++;
    const hit = RANGES.some(([lo, hi]) => cp >= lo && cp <= hi);
    if (hit && !ALLOW.has(String.fromCodePoint(cp))) {
      const line = text.slice(0, i).split("\n").length;
      console.error(`[emoji] ${path}:${line} U+${cp.toString(16).toUpperCase()}`);
      bad++;
    }
  }
}
if (bad > 0) { console.error(`GAGAL: ${bad} emoji ditemukan.`); process.exit(1); }
console.log("OK: 0 emoji.");
