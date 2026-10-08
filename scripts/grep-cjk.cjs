#!/usr/bin/env node
/* Zero-aksara-asing guard: keluar 1 bila ada karakter non-Latin (CJK, Kana,
 * Hangul, fullwidth, atau Cyrillic) di source.
 *
 *   node scripts/grep-cjk.cjs                  # cek default source tree
 *   node scripts/grep-cjk.cjs <file|dir ...>   # cek target tertentu
 *
 * Seluruh dokumen & komentar proyek ini berbahasa Indonesia/English latin.
 * Aksara CJK atau Cyrillic yang muncul hampir selalu salah ketik yang lolos
 * review, bukan tulisan yang disengaja.
 *
 * Exit codes:
 *   0  bersih
 *   1  ada karakter non-Latin
 *   2  FAIL-CLOSED: tidak ada file yang diperiksa
 */
const fs = require("fs");
const path = require("path");

function isCJK(cp) {
  return (
    (cp >= 0x4e00 && cp <= 0x9fff) ||   // CJK Unified Ideographs
    (cp >= 0x3400 && cp <= 0x4dbf) ||   // Extension A
    (cp >= 0xf900 && cp <= 0xfaff) ||   // Compatibility Ideographs
    (cp >= 0x3040 && cp <= 0x30ff) ||   // Hiragana + Katakana
    (cp >= 0xac00 && cp <= 0xd7af) ||   // Hangul Syllables
    (cp >= 0x3000 && cp <= 0x303f) ||   // CJK Symbols and Punctuation
    (cp >= 0xff00 && cp <= 0xffef)      // Halfwidth and Fullwidth Forms
  );
}

function isCyrillic(cp) {
  return (
    (cp >= 0x0400 && cp <= 0x04ff) ||   // Cyrillic
    (cp >= 0x0500 && cp <= 0x052f)      // Cyrillic Supplement
  );
}

function isAksaraAsing(cp) {
  return isCJK(cp) || isCyrillic(cp);
}

const SKIP_DIR = new Set([
  "node_modules", ".git", ".venv", "venv", "__pycache__",
  "vendor", "artifacts", "backups", ".kilo", ".commandcode",
  "stitch_aplikasi_deteksi_kerusakan_jalan", "Obsidian Vault",
  "data", "runs", "_arsip",
]);

const EXT_OK = new Set([
  ".py", ".js", ".cjs", ".mjs", ".html", ".htm", ".css", ".md",
  ".yaml", ".yml", ".json", ".csv", ".txt", ".sql", ".sh", ".ps1",
]);

const ROOT = path.resolve(__dirname, "..");

function defaultTargets() {
  // Direktori + berkas root. Root .md WAJIB ikut daftar: README.md dan
  // DESIGN.md adalah dokumen yang paling sering diedit, tapi kalau hanya
  // direktori yang dipindai keduanya lolos tanpa pemeriksaan.
  return ["web", "app", "scripts", "config", "tests", "docs", "notebooks",
          "yolov11s-rdd-only", "reports",
          "README.md", "DESIGN.md", "requirements.txt"]
    .map((p) => path.join(ROOT, p));
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
    if (EXT_OK.has(path.extname(target).toLowerCase())) out.push(target);
    return;
  }
  for (const entry of fs.readdirSync(target, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP_DIR.has(entry.name)) continue;
      walk(path.join(target, entry.name), out);
    } else if (EXT_OK.has(path.extname(entry.name).toLowerCase())) {
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

if (files.length === 0) {
  console.error("GAGAL: tidak ada file yang diperiksa. Guard ini fail-closed");
  console.error("       supaya tidak pernah hijau tanpa memeriksa apa pun.");
  process.exit(2);
}

let bad = 0;
for (const f of files) {
  const text = fs.readFileSync(f, "utf8");
  for (let i = 0; i < text.length; i++) {
    const cp = text.codePointAt(i);
    if (cp > 0xffff) i++;
    if (isAksaraAsing(cp)) {
      const line = text.slice(0, i).split("\n").length;
      const rel = path.relative(ROOT, f);
      const glif = String.fromCodePoint(cp);
      const nama = isCyrillic(cp) ? "cyrillic" : "cjk";
      console.error(`[${nama}] ${rel}:${line} U+${cp.toString(16).toUpperCase()} ${JSON.stringify(glif)}`);
      bad++;
    }
  }
}

console.log(`[scanned ${files.length} file]`);
if (bad > 0) {
  console.error(`GAGAL: ${bad} karakter non-Latin ditemukan.`);
  process.exit(1);
}
console.log("OK: 0 karakter non-Latin.");