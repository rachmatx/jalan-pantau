#!/usr/bin/env node
/* Zero-emoji guard: exits 1 if any file contains emoji / dingbat unicode.
 *
 *   node scripts/grep-emoji.cjs                 # cek default source tree
 *   node scripts/grep-emoji.cjs <file|dir ...>  # cek target tertentu
 *
 * Exit codes:
 *   0  bersih
 *   1  ada pelanggaran
 *   2  FAIL-CLOSED: tidak ada file yang diperiksa (gate tidak boleh hijau hampa)
 */
const fs = require("fs");
const path = require("path");

// Emoji + dingbats + symbols + arrows + geometric shapes + misc symbols.
const RANGES = [
  [0x1f000, 0x1faff],
  [0x2600, 0x26ff],
  [0x2700, 0x27bf],
  [0x2b00, 0x2bff],
  [0xfe0f, 0xfe0f],
  [0x2049, 0x2049],
  [0x203c, 0x203c],
  [0x2139, 0x2139], // INFORMATION SOURCE — dipakai sebagai ikon di base.html
  [0x2190, 0x21ff],
];

const ALLOW = new Set(["→"]); // → arrow in prose (teks deskripsi alur)

// Direktori yang tidak boleh dipindai (vendor pihak ketiga).
const SKIP_DIR = new Set([
  "node_modules", ".git", ".venv", "venv", "__pycache__",
  "vendor", "artifacts", "backups", ".kilo", ".commandcode",
  "stitch_aplikasi_deteksi_kerusakan_jalan",
]);

const EXT_OK = new Set([".html", ".htm", ".js", ".cjs", ".mjs", ".css", ".py"]);

// File pihak ketiga yang ikut ter-*vendor*. Bukan milik proyek; aturan
// "no emoji as icons" hanya berlaku pada kode yang kita kendalikan.
const SKIP_FILE = new Set(["pico.min.css"]);

const ROOT = path.resolve(__dirname, "..");

// Default: seluruh permukaan UI + python yang dirender ke UI.
function defaultTargets() {
  return ["web", "app", "scripts", "config", "tests"].map((p) => path.join(ROOT, p));
}

function walk(target, out) {
  let st;
  try {
    st = fs.statSync(target);
  } catch {
    console.error(`[skip] ${target} (tidak ada)`);
    return;
  }
  if (st.isFile()) {
    if (SKIP_FILE.has(path.basename(target))) return;
    if (EXT_OK.has(path.extname(target).toLowerCase())) out.push(target);
    return;
  }
  for (const entry of fs.readdirSync(target, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP_DIR.has(entry.name)) continue;
      walk(path.join(target, entry.name), out);
    } else if (!SKIP_FILE.has(entry.name)
               && EXT_OK.has(path.extname(entry.name).toLowerCase())) {
      out.push(path.join(target, entry.name));
    }
  }
}

const args = process.argv.slice(2);
const files = [];
for (const t of args.length ? args : defaultTargets()) {
  walk(path.resolve(t), files);
}
files.sort();

// FAIL-CLOSED: tanpa file yang diperiksa = gate tidak boleh lolos.
if (files.length === 0) {
  console.error("GAGAL: tidak ada file yang diperiksa. Guard ini fail-closed");
  console.error("       supaya tidak pernah hijau tanpa memeriksa apa pun.");
  process.exit(2);
}

let bad = 0;
const shown = new Set();
for (const f of files) {
  const text = fs.readFileSync(f, "utf8");
  for (let i = 0; i < text.length; i++) {
    const cp = text.codePointAt(i);
    if (cp > 0xffff) i++;
    const hit = RANGES.some(([lo, hi]) => cp >= lo && cp <= hi);
    if (hit && !ALLOW.has(String.fromCodePoint(cp))) {
      const line = text.slice(0, i).split("\n").length;
      const rel = path.relative(ROOT, f);
      const key = `${rel}:${line}:${cp}`;
      if (shown.has(key)) continue;
      shown.add(key);
      console.error(`[emoji] ${rel}:${line} U+${cp.toString(16).toUpperCase()}`);
      bad++;
    }
  }
}

console.log(`[scanned ${files.length} file]`);
if (bad > 0) {
  console.error(`GAGAL: ${bad} emoji ditemukan.`);
  process.exit(1);
}
console.log("OK: 0 emoji.");