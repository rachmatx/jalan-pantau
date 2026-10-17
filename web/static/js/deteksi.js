{/* Deteksi: upload -> /api/detect -> tabel -> /api/laporan (PDF). */}
const form = document.getElementById("form-deteksi");const conf = document.getElementById("conf");
const confOut = document.getElementById("conf-out");
const status = document.getElementById("status");
const tombol = document.getElementById("tombol");
const slot = document.getElementById("slot-gambar");
const hasil = document.getElementById("hasil");
let terakhir = null;
var deteksiRows = [];
var deteksiHalaman = 1;
var deteksiPerHal = 10;
/* Verifikasi operator: hasil mentah AI + koreksi (stateless, backend hitung ulang). */
var barisAsli = null;
var verHapus = new Set();
var verSev = {};
var SEV_OPSI = ["Ringan", "Sedang", "Berat"];

function renderTabelDeteksi() {
  var totalHal = Math.ceil(deteksiRows.length / deteksiPerHal);
  if (deteksiHalaman > totalHal) deteksiHalaman = totalHal;
  if (deteksiHalaman < 1) deteksiHalaman = 1;
  var mulai = (deteksiHalaman - 1) * deteksiPerHal;
  var sampai = Math.min(mulai + deteksiPerHal, deteksiRows.length);
  var rows = deteksiRows.slice(mulai, sampai);
  var tbody = rows.map(function(r, i) {
    var ia = (r.idx_asli != null) ? r.idx_asli : (mulai + i);
    var sumber = r.diubah
      ? `<span class="jp-cell-main">AI*</span><span class="jp-cell-sub">${esc(r.diubah)}</span>`
      : `<span class="jp-cell-main">AI</span><span class="jp-cell-sub">mentah model</span>`;
    var opsi = SEV_OPSI.map(function(s) {
      return `<option value="${s}"${s === r.severity ? " selected" : ""}>${s}</option>`;
    }).join("");
    var aksi = `<select data-sev="${ia}" aria-label="Koreksi severity baris ${mulai + i + 1}" style="height:32px;border:1px solid var(--jp-line);border-radius:8px;background:var(--jp-surface);font-size:12px">${opsi}</select> ` +
      `<button type="button" data-hapus="${ia}" aria-label="Hapus baris ${mulai + i + 1}" style="height:32px;padding:0 10px;border:1px solid var(--jp-line);border-radius:8px;background:var(--jp-surface);font-size:12px;cursor:pointer">Hapus</button>`;
    return `<tr><td class="jp-num">${String(mulai + i + 1).padStart(2, "0")}</td>` +
      `<td><span class="jp-cell-main">${esc(namaKelas(r.kelas))}</span><span class="jp-cell-sub">class: ${esc(r.kelas)}</span></td>` +
      `<td class="jp-num">${esc(r.dasar)}</td><td>${badge(r.severity)}</td>` +
      `<td class="jp-num">${esc(confStr(r.conf))}</td>` +
      `<td>${sumber}</td><td style="white-space:nowrap">${aksi}</td></tr>`;
  }).join("");
  var thead = `<tr><th>#</th><th>JENIS KERUSAKAN</th><th>AREA / DIMENSI ESTIMASI</th><th>TINGKAT KEPARAHAN</th><th>CONFIDENCE</th><th>SUMBER</th><th>VERIFIKASI</th></tr>`;
  document.getElementById("tabel").innerHTML = `<table class="jp-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
  // Pagination
  var pagEl = document.getElementById("deteksi-paginasi");
  if (deteksiRows.length > deteksiPerHal) {
    pagEl.style.display = "flex";
    var btns = '';
    btns += `<button type="button" data-p="prev" style="min-width:36px;height:36px;padding:0 12px;border:1px solid var(--jp-line);border-radius:8px;background:var(--jp-surface);font-size:13px;cursor:pointer">&laquo;</button>`;
    for (var h = 1; h <= totalHal; h++) {
      btns += `<button type="button" data-p="${h}" style="min-width:36px;height:36px;padding:0 12px;border:1px solid ${h === deteksiHalaman ? 'var(--jp-primary)' : 'var(--jp-line)'};border-radius:8px;background:${h === deteksiHalaman ? 'var(--jp-primary)' : 'var(--jp-surface)'};color:${h === deteksiHalaman ? '#fff' : 'var(--jp-ink)'};font-size:13px;cursor:pointer">${h}</button>`;
    }
    btns += `<button type="button" data-p="next" style="min-width:36px;height:36px;padding:0 12px;border:1px solid var(--jp-line);border-radius:8px;background:var(--jp-surface);font-size:13px;cursor:pointer">&raquo;</button>`;
    pagEl.innerHTML = btns;
    pagEl.querySelectorAll('button').forEach(function(b) {
      b.addEventListener('click', function() {
        var p = b.getAttribute('data-p');
        if (p === 'prev') deteksiHalaman--;
        else if (p === 'next') deteksiHalaman++;
        else deteksiHalaman = parseInt(p);
        renderTabelDeteksi();
      });
    });
  } else {
    pagEl.style.display = "none";
  }
}

/* === Verifikasi operator (Fase 1): hapus + koreksi severity via backend === */
async function syncVerifikasi() {
  if (!barisAsli) return;
  const res = await fetch("/api/verifikasi", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows: barisAsli, hapus: [...verHapus], severity: verSev }),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || "Verifikasi gagal.");
  deteksiRows = json.rows;
  deteksiHalaman = 1;
  if (terakhir) {
    terakhir.rows = json.rows;
    terakhir.total = json.total;
    terakhir.info = json.info;
  }
  refreshVerifikasiUI();
}

function teksVerifikasi(info) {
  if (!info || !info.total) return "";
  var bagian = [];
  if (info.hapus) bagian.push(info.hapus + " hapus");
  if (info.severity) bagian.push(info.severity + " koreksi severity");
  return info.total + " perubahan (" + bagian.join(", ") + ")";
}

/* Pesan "tanpa temuan" yang menjelaskan APA yang terjadi. Tanpa ini pengguna
   hanya melihat "tidak ada kerusakan" dan tak bisa membedakan "model memang
   tidak melihat" dari "kandidat ada tapi dibuang penyaring" — pertanyaan yang
   berulang ("conf sudah saya turunkan ke 0,1, kok tetap kosong?").
   Angka diambil apa adanya dari `disaring` balasan /api/detect. */
function pesanKosong(json) {
  var d = json.disaring || {};
  var gugur = [];
  var rusak = Number(d.rusak || 0);
  if (rusak) gugur.push(rusak + " keluaran rusak dari model (diabaikan)");
  if (d.ambang) gugur.push(d.ambang + " di bawah ambang kepercayaan");
  if (d.ukuran) gugur.push(d.ukuran + " ukuran tidak masuk akal");
  if (d.mungil) gugur.push(d.mungil + " terlalu kecil");
  var nGate = (d.gate && d.gate.disaring) || 0;
  if (nGate) gugur.push(nGate + " lubang ditahan gate jalan-basah");
  var sebab = gugur.length
    ? " Kandidat model yang gugur: " + gugur.join(", ") + "."
    : " Model tidak menghasilkan satu kandidat pun.";
  // "Rusak" = box/conf NaN (model mengeluarkan nilai cacat), BUKAN kerusakan
  // yang geometrinya aneh. Tanpa penjelasan ini pengguna menyangka penyaring
  // ukuran yang salah lalu menuntut penyaringnya dilonggarkan.
  var totalGugur = rusak + Number(d.ambang || 0) + Number(d.ukuran || 0) +
    Number(d.mungil || 0) + nGate;
  if (rusak > 0 && rusak >= totalGugur * 0.5) {
    sebab += " \"Keluaran rusak\" berarti model mengembalikan koordinat tak sah" +
      " (NaN) — bukan deteksi berukuran aneh yang ditolak penyaring.";
  }
  var auto = json.teliti_otomatis
    ? " Mode teliti otomatis sudah dicoba karena gambar besar." : "";
  return "Tidak ada temuan pada ambang ini." + sebab + auto + " " +
    saranLanjutan(json);
}

/* Saran yang DISESUAIKAN keadaan. Menyarankan "turunkan confidence" saat
   slider sudah di batas bawah (0,05) hanya membuat pengguna bingung, begitu
   pula "centang mode teliti" saat mode itu sudah berjalan. */
function saranLanjutan(json) {
  var saran = [];
  var diBatasBawah = false;
  try {
    var min = parseFloat(conf.min);
    diBatasBawah = !!conf && conf.value !== "" &&
      parseFloat(conf.value) <= (isFinite(min) ? min : 0) + 1e-9;
  } catch (e) { /* slider tak ada: anggap belum di batas bawah */ }
  if (json.gelap && !json.malam) {
    saran.push("centang \"Pencahayaan Rendah / Malam\" (foto ini gelap)");
  }
  if (!diBatasBawah) saran.push("turunkan confidence");
  if (!json.teliti) saran.push("centang mode teliti");
  saran.push("ambil foto dari jarak lebih dekat", "ambil foto saat siang hari");
  return "Coba " + saran.join(", ") + ".";
}

/* Ukuran piksel gambar terpilih. Dipakai hanya untuk menyetel ekspektasi waktu:
   foto besar (sisi > ~1920 px) dianalisis per bagian oleh server dan bisa
   memakan 15-30 detik; tanpa petunjuk ini pengguna menyangka aplikasi
   menggantung padahal masih bekerja. */
function ukuranGambar(berkas) {
  return new Promise(function (resolve) {
    try {
      var url = URL.createObjectURL(berkas);
      var im = new Image();
      im.onload = function () {
        URL.revokeObjectURL(url);
        resolve({ w: im.naturalWidth, h: im.naturalHeight });
      };
      im.onerror = function () { URL.revokeObjectURL(url); resolve(null); };
      im.src = url;
    } catch (e) {
      console.warn("gagal membaca dimensi gambar:", e);
      resolve(null);
    }
  });
}

function refreshVerifikasiUI() {
  renderTabelDeteksi();
  if (!terakhir) return;
  document.getElementById("lubang-nilai").textContent = String(
      terakhir.rows.filter(function(r) { return /pothole/i.test(r.kelas || ""); }).length);
  document.getElementById("temuan-nilai").textContent = terakhir.rows.length;
  const nBerat = terakhir.rows.filter((r) => r.severity === "Berat").length;
  document.getElementById("berat-nilai").textContent = `Berat (${nBerat})`;
  document.getElementById("tabel-hitung").textContent = `${terakhir.rows.length} Data Tabel`;
  const info = terakhir.info || { total: 0 };
  const label = teksVerifikasi(info);
  document.getElementById("verifikasi-hitung").textContent = label ? `· terverifikasi: ${label}` : "";
  document.getElementById("verifikasi-reset").hidden = !info.total;
  hasil.hidden = false;
  status.classList.remove("galat");
  const mode = terakhir.teliti
    ? (terakhir.teliti_otomatis
      ? " (mode teliti otomatis — gambar besar)"
      : " (mode teliti)")
    : "";
  status.textContent = `${terakhir.rows.length} temuan${mode}.` +
    (label ? ` Terverifikasi operator: ${label}.` : "");
}

document.getElementById("tabel").addEventListener("change", async (e) => {
  const sel = e.target.closest ? e.target.closest("select[data-sev]") : null;
  if (!sel || !barisAsli) return;
  const ia = sel.getAttribute("data-sev");
  const asal = (barisAsli[Number(ia)] || {}).severity;
  if (sel.value && sel.value !== asal) verSev[ia] = sel.value;
  else delete verSev[ia];
  try {
    await syncVerifikasi();
  } catch (err) {
    status.textContent = err.message;
    status.classList.add("galat");
  }
});

document.getElementById("tabel").addEventListener("click", async (e) => {
  const btn = e.target.closest ? e.target.closest("button[data-hapus]") : null;
  if (!btn || !barisAsli) return;
  verHapus.add(btn.getAttribute("data-hapus"));
  try {
    await syncVerifikasi();
  } catch (err) {
    status.textContent = err.message;
    status.classList.add("galat");
  }
});

document.getElementById("verifikasi-reset").addEventListener("click", async () => {
  verHapus = new Set();
  verSev = {};
  try {
    await syncVerifikasi();
  } catch (err) {
    status.textContent = err.message;
    status.classList.add("galat");
  }
});

if (location.protocol === "file:") {
  document.getElementById("status").textContent =
    "Halaman ini dibuka sebagai file — server tidak jalan. Jalankan .\\.venv\\Scripts\\python web/app.py lalu buka http://127.0.0.1:5000.";
  document.getElementById("status").classList.add("galat");
  document.getElementById("tombol").disabled = true;
}

conf.addEventListener("input", () => {
  confOut.textContent = Number(conf.value).toFixed(2).replace(".", ",");
});

function badge(sev) {
  const map = { ringan: "RINGAN", sedang: "SEDANG", berat: "BERAT" };
  const k = String(sev).toLowerCase();
  return `<span class="badge badge-${k}"><span class="badge-dot"></span>${esc(map[k] || sev)}</span>`;
}
// P0 XSS: escape sebelum innerHTML.
function esc(v) {
  return String(v ?? "").replace(/[&<>"'`=]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
    "'": "&#39;", "`": "&#96;", "=": "&#61;",
  }[c]));
}

const NAMA_KELAS = {
  pothole: "Lubang (Pothole)",
  longitudinal_crack: "Retak Memanjang (Longitudinal Crack)",
  transverse_crack: "Retak Melintang (Transverse Crack)",
  alligator_crack: "Retak Kulit Buaya (Alligator Crack)",
  other_corruption: "Kerusakan Lain (Other Corruption)",
};
function namaKelas(k) { return NAMA_KELAS[k] || k; }
function confStr(c) {
  const v = Number(c);
  return `${String(v.toFixed(2)).replace(".", ",")} (${Math.round(v * 100)}%)`;
}

document.getElementById("gambar").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f) {
    if (f.size > 15 * 1048576) {
      e.target.value = "";
      status.textContent = "Ukuran gambar maks 15 MB. Kecilkan resolusi lalu coba lagi.";
      status.classList.add("galat");
      return;
    }
    status.classList.remove("galat");
    document.getElementById("nama-berkas").textContent = `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`;
    const drop = document.getElementById("drop-foto");
    const sub = document.getElementById("drop-sub");
    if (drop) drop.textContent = f.name;
    if (sub) sub.textContent = `${(f.size / 1048576).toFixed(1)} MB · tersimpan siap deteksi`;
    // Pratinjau langsung: tampilkan gambar di viewer begitu dipilih (tanpa menunggu deteksi)
    try {
      if (window.__jpPratinjauUrl) URL.revokeObjectURL(window.__jpPratinjauUrl);
      window.__jpPratinjauUrl = URL.createObjectURL(f);
      slot.classList.remove("kosong");
      slot.innerHTML = `<img src="${window.__jpPratinjauUrl}" alt="Pratinjau ${esc(f.name)}">`;
      hasil.hidden = true; // hasil deteksi lama tidak lagi sesuai gambar baru
    } catch (err) { /* abaikan: deteksi tetap bisa jalan */ }
  }
});

/* Drag & drop: jatuhkan JPG/PNG ke dropzone ATAU viewer */
function terimaBerkas(files) {
  const f = [...(files || [])].find((x) => /^image\/(jpeg|png)$/.test(x.type || ""));
  if (!f) {
    status.textContent = "Format harus JPG atau PNG.";
    status.classList.add("galat");
    return;
  }
  const dt = new DataTransfer();
  dt.items.add(f);
  const inp = document.getElementById("gambar");
  inp.files = dt.files;
  inp.dispatchEvent(new Event("change", { bubbles: true }));
  status.classList.remove("galat");
  status.textContent = "Foto siap. Tekan Deteksi untuk menganalisis.";
}
const dropzone = document.querySelector(".jp-dropzone");
if (dropzone) {
  ["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  }));
  dropzone.addEventListener("drop", (e) => terimaBerkas(e.dataTransfer.files));
}
const viewerGambar = document.getElementById("viewer-gambar");
if (viewerGambar) {
  viewerGambar.addEventListener("dragover", (e) => e.preventDefault());
  viewerGambar.addEventListener("drop", (e) => {
    e.preventDefault();
    terimaBerkas(e.dataTransfer.files);
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const berkas = document.getElementById("gambar").files[0];
  if (!berkas) {
    status.textContent = "Pilih berkas gambar dulu.";
    status.classList.add("galat");
    return;
  }
  tombol.disabled = true;
  var tombolAsli = tombol.innerHTML;
  tombol.innerHTML = '<span style="display:inline-block;width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:jp-spin .8s linear infinite;vertical-align:middle;margin-right:8px"></span><span style="vertical-align:middle">Menganalisis…</span>';
  status.classList.remove("galat");
  status.textContent = "Mendeteksi…";
  hasil.hidden = true;
  slot.classList.add("kosong");
  slot.innerHTML = '<div class="jp-loading"><div class="jp-loading-spinner"></div><p>Menganalisis gambar dengan YOLOv11s…</p></div>';
  // Setel ekspektasi waktu untuk foto besar (tanpa menahan unggahan).
  ukuranGambar(berkas).then(function (dim) {
    if (!dim || Math.max(dim.w, dim.h) < 1920) return;
    const p = slot.querySelector(".jp-loading p");
    if (p) {
      p.textContent = "Gambar " + (dim.w * dim.h / 1e6).toFixed(1).replace(".", ",") +
        " MP — analisis foto besar bisa 15–30 detik…";
    }
  }).catch(function (e) {
    console.warn("petunjuk ukuran gambar gagal:", e);
  });
  try {
    const data = new FormData();
    data.append("gambar", berkas);
    data.append("conf", conf.value);
    if (document.getElementById("malam").checked) data.append("malam", "1");
    const teliti = document.getElementById("teliti") && document.getElementById("teliti").checked;
    if (teliti) data.append("teliti", "1");
    if (teliti) status.textContent = "Mendeteksi (mode teliti — lebih lama)…";
    const res = await fetch("/api/detect", { method: "POST", body: data });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Deteksi gagal.");
    terakhir = { ...json, namaBerkas: berkas.name };
    if (json.model) {
      const nm = document.getElementById("nama-model");
      const nc = document.getElementById("nama-model-chip");
      if (nm) nm.textContent = json.model;
      if (nc) nc.textContent = json.model;
    }
    const sb = document.getElementById("scene-badge");
    if (sb) {
      const sc = json.scene;
      if (sc && sc.label_id) {
        sb.hidden = false;
        sb.classList.toggle("gate", !!sc.gate_aktif);
        sb.textContent = "Kondisi: " + sc.label_id + " (" + Math.round((sc.conf || 0) * 100) + "%)"
          + (sc.gate_aktif ? " · gate anti-false-positive aktif" : "");
      } else {
        sb.hidden = true;
      }
    }
    slot.classList.remove("kosong");
    slot.innerHTML = `<img src="data:image/jpeg;base64,${json.image_b64}" alt="Hasil deteksi ${esc(berkas.name)}">`;
    if (json.gps && json.gps.lat != null && isiKoordinat("lat-gambar", "lon-gambar", json.gps.lat, json.gps.lon)) {
      status.textContent = "Koordinat terisi otomatis dari foto. ";
      status.classList.remove("galat");
    }
    if (!json.rows.length) {
      status.textContent = pesanKosong(json);
      return;
    }
    barisAsli = json.rows;
    verHapus = new Set();
    verSev = {};
    await syncVerifikasi();
    // Simpan ke localStorage dengan timestamp untuk restore saat navigasi/refresh
    try {
      localStorage.setItem("jp_deteksi_terakhir", JSON.stringify({ ...json, namaBerkas: berkas.name }));
      localStorage.setItem("jp_deteksi_time", Date.now().toString());
    } catch (e) {}
  } catch (err) {
    status.textContent = err.message;
    status.classList.add("galat");
  } finally {
    tombol.disabled = false;
    tombol.innerHTML = tombolAsli;
  }
});

function isiKoordinat(latId, lonId, lat, lon, asal) {
  const elLat = document.getElementById(latId);
  const elLon = document.getElementById(lonId);
  if (lat == null || lon == null) return false;
  if (elLat.value.trim() === "") elLat.value = String(lat).replace(".", ",");
  if (elLon.value.trim() === "") elLon.value = String(lon).replace(".", ",");
  return true;
}

function bacaKoordinat(latId, lonId) {
  const num = (id) => {
    const el = document.getElementById(id);
    if (!el) return null;
    const v = el.value.trim().replace(",", ".");
    return v === "" ? null : Number(v);
  };
  return { lat: num(latId), lon: num(lonId) };
}

document.getElementById("simpan").addEventListener("click", async () => {
  if (!terakhir) return;
  const btn = document.getElementById("simpan");
  if (btn.disabled) return;
  btn.disabled = true;
  try {
    const { lat, lon } = bacaKoordinat("lat-gambar", "lon-gambar");
    // Kunci idempotensi: satu ref tetap untuk satu aksi simpan (anti klik-dobel/retry).
    const refSimpan = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : ("ref-" + Date.now() + "-" + Math.random().toString(16).slice(2));
    const kirim = (izinkan) => fetch("/api/riwayat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sumber: `Gambar (${terakhir.namaBerkas})`,
        lokasi: document.getElementById("lokasi-gambar").value.trim(),
        lat, lon, model: terakhir.model,
        rows: terakhir.rows, total: terakhir.total,
        image_b64: terakhir.image_b64,
        client_ref: refSimpan, izinkan_duplikat: !!izinkan,
      }),
    });
    let res = await kirim(false);
    let json = await res.json().catch(() => ({}));
    // Belum login (atau sesi habis): tawarkan login via modal, lalu ulangi sekali.
    if (res.status === 401 && window.jpButuhLogin) {
      const masuk = await window.jpButuhLogin();
      if (!masuk) {
        status.textContent = "Dibatalkan — masuk untuk menyimpan ke riwayat.";
        status.classList.remove("galat");
        return;
      }
      res = await kirim(false);
      json = await res.json().catch(() => ({}));
    }
    // Duplikat koordinat: tanya operator; boleh simpan ulang bila memang inspeksi baru.
    if (res.ok && json.duplikat && json.alasan === "koordinat") {
      const lanjut = await window.jpConfirm("Riwayat Serupa",
        `Sudah ada riwayat di titik ini (ID ${json.id}). Tetap simpan sebagai riwayat baru?`,
        { okText: "Tetap Simpan" });
      if (!lanjut) {
        status.textContent = `Dibatalkan — riwayat serupa sudah ada (ID ${json.id}).`;
        status.classList.remove("galat");
        return;
      }
      res = await kirim(true);
      json = await res.json().catch(() => ({}));
    }
    if (!res.ok) {
      status.textContent = json.error || "Gagal menyimpan.";
      status.classList.add("galat");
      showToast("Gagal", json.error || "Gagal menyimpan ke riwayat.", "galat");
      return;
    }
    if (json.duplikat) {
      status.textContent = `Sudah tersimpan sebelumnya (ID ${json.id}).`;
      status.classList.remove("galat");
      showToast("Sudah Ada", `Riwayat ini sudah tersimpan (ID ${json.id}).`, "info");
      return;
    }
    const amin = peringatanGPS(lat, lon);
    status.classList.toggle("galat", amin !== null);
    status.textContent = amin !== null ? `${amin} (ID ${json.id}).` : `Tersimpan ke riwayat (ID ${json.id}).`;
    // Notifikasi sukses
    showToast("Tersimpan!", `Hasil deteksi berhasil disimpan ke riwayat (ID ${json.id}).`, "success");
  } catch (err) {
    status.textContent = `Gagal menyimpan: ${err.message}`;
    status.classList.add("galat");
    showToast("Gagal", `Gagal menyimpan: ${err.message}`, "galat");
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("unduh").addEventListener("click", async () => {
  if (!terakhir) return;
  status.textContent = "Membuat PDF…";
  const res = await fetch("/api/laporan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rows: terakhir.rows,
      total: terakhir.total,
      image_b64: terakhir.image_b64,
      source: terakhir.namaBerkas,
      model: terakhir.model,
      verifikasi: teksVerifikasi(terakhir.info),
    }),
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    status.textContent = json.error || "Gagal membuat PDF.";
    status.classList.add("galat");
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "laporan_jalan.pdf";
  a.click();
  URL.revokeObjectURL(a.href);
  status.textContent = "PDF terunduh.";
});

/* === Notifikasi Toast === */
function showToast(title, message, type) {
  var container = document.getElementById("toast-container");
  if (!container) return;
  var toast = document.createElement("div");
  toast.className = "toast";
  var icons = {
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    galat: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
  };
  var colors = { info: "#006194", success: "#059669", galat: "#ba1a1a" };
  toast.style.cssText = "background:#fff;border-left:4px solid " + (colors[type] || colors.info) + ";border-radius:8px;padding:12px 16px;box-shadow:0 4px 16px rgba(0,0,0,.15);display:flex;align-items:flex-start;gap:12px;animation:slideIn .3s ease;min-width:280px;max-width:360px";
  toast.innerHTML = '<span style="font-size:18px;color:' + (colors[type] || colors.info) + '">' + (icons[type] || icons.info) + '</span><div style="flex:1"><div style="font-size:13px;font-weight:600;color:#0F172A">' + esc(title) + '</div><div style="font-size:12px;color:#64748B;margin-top:2px">' + esc(message) + '</div></div>';
  container.appendChild(toast);
  setTimeout(function () { toast.style.opacity = "0"; toast.style.transform = "translateX(100%)"; setTimeout(function () { toast.remove(); }, 300); }, 4000);
}

// Restore hasil deteksi dari localStorage dengan TTL 10 detik
// Normal refresh/navigasi dalam 10 detik = data tersimpan
// Hard refresh setelah idle = data hilang
(function restoreDeteksi() {
  try {
    var saved = localStorage.getItem("jp_deteksi_terakhir");
    var savedTime = localStorage.getItem("jp_deteksi_time");
    if (!saved) return;
    // Cek TTL: hapus jika lebih dari 10 detik
    if (savedTime && (Date.now() - parseInt(savedTime)) > 10000) {
      localStorage.removeItem("jp_deteksi_terakhir");
      localStorage.removeItem("jp_deteksi_time");
      return;
    }
    var data = JSON.parse(saved);
    if (!data || !data.rows) return;
    terakhir = data;
    var slot = document.getElementById("slot-gambar");
    var hasil = document.getElementById("hasil");
    var status = document.getElementById("status");
    if (data.image_b64) {
      slot.classList.remove("kosong");
      slot.innerHTML = '<img src="data:image/jpeg;base64,' + data.image_b64 + '" alt="Hasil deteksi ' + esc(data.namaBerkas) + '">';
    }
    if (data.rows && data.rows.length) {
      document.getElementById("lubang-nilai").textContent = String(
        data.rows.filter(function(r) { return /pothole/i.test(r.kelas || ""); }).length);
      document.getElementById("temuan-nilai").textContent = data.rows.length;
      var nBerat = data.rows.filter(function(r) { return r.severity === "Berat"; }).length;
      document.getElementById("berat-nilai").textContent = "Berat (" + nBerat + ")";
      document.getElementById("tabel-hitung").textContent = data.rows.length + " Data Tabel";
      deteksiRows = data.rows;
      deteksiHalaman = 1;
      renderTabelDeteksi();
      hasil.hidden = false;
      if (status) { status.textContent = data.rows.length + " temuan (dipulihkan)."; status.classList.remove("galat"); }
      barisAsli = data.rows;
      verHapus = new Set();
      verSev = {};
      // Gagal sinkronkan verifikasi diam-diam akan menyesatkan: tabel
      // verifikasi di bawah sudah menampilkan hasil deteksi yang BARU,
      // padahal daftar CHECK-nya masih yang lama. User bisa salah menilai
      // tanpa pernah tahu ada yang gagal.
      syncVerifikasi().catch(function(e) {
        console.error("[JalanPantau] sinkronisasi verifikasi setelah deteksi", e);
        if (status) {
          status.textContent = "Temuan diperbarui, tetapi daftar verifikasi gagal disinkronkan. Muat ulang halaman.";
          status.classList.add("galat");
        }
      });
    }
  } catch (e) { /* abaikan */ }
})();

// Update timestamp setiap 3 detik saat page aktif (keep-alive)
setInterval(function() {
  if (localStorage.getItem("jp_deteksi_terakhir")) {
    localStorage.setItem("jp_deteksi_time", Date.now().toString());
  }
}, 3000);

/* === GPS & Reverse Geocoding === */
// Ambil GPS saat ini
var gpsBtn = document.getElementById("gps-sekarang");
if (gpsBtn) {
  gpsBtn.addEventListener("click", function() {
    if (!navigator.geolocation) {
      showToast("GPS Tidak Didukung", "Browser tidak mendukung geolokasi.", "galat");
      return;
    }
    gpsBtn.disabled = true;
    gpsBtn.querySelector("span").textContent = "Mendeteksi lokasi...";
    navigator.geolocation.getCurrentPosition(
      function(pos) {
        var lat = pos.coords.latitude;
        var lon = pos.coords.longitude;
        document.getElementById("lat-gambar").value = lat.toFixed(6);
        document.getElementById("lon-gambar").value = lon.toFixed(6);
        gpsBtn.disabled = false;
        gpsBtn.querySelector("span").textContent = "Ambil GPS Saat Ini";
        // Auto-fill nama jalan dari koordinat
        reverseGeocode(lat, lon);
      },
      function(err) {
        gpsBtn.disabled = false;
        gpsBtn.querySelector("span").textContent = "Ambil GPS Saat Ini";
        showToast("GPS Gagal", "Tidak bisa mengakses GPS: " + err.message + ". Anda bisa mengisi manual.", "galat");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    );
  });
}

// Reverse geocoding: koordinat -> nama jalan (Nominatim/OpenStreetMap)
function reverseGeocode(lat, lon) {
  var lokasiInput = document.getElementById("lokasi-gambar");
  lokasiInput.value = "Mencari nama jalan...";
  fetch("https://nominatim.openstreetmap.org/reverse?format=json&lat=" + lat + "&lon=" + lon + "&zoom=18&addressdetails=1", {
    headers: { "Accept-Language": "id" }
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data && data.display_name) {
      // Ambil nama jalan saja (hapus kelurahan, kota, negara)
      var namaJalan = data.display_name.split(",")[0].trim();
      lokasiInput.value = namaJalan;
      showToast("Lokasi Ditemukan", "Nama jalan: " + namaJalan, "success");
    } else {
      lokasiInput.value = "";
      showToast("Lokasi Tidak Ditemukan", "Tidak bisa menemukan nama jalan. Silakan isi manual.", "info");
    }
  })
.catch(function(e) {
      console.error("[JalanPantau] geocoding lokasi", e);
      lokasiInput.value = "";
    showToast("Lokasi Tidak Ditemukan", "Gagal mengakses layanan geocoding. Silakan isi manual.", "info");
  });
}

// Auto-fill nama jalan saat koordinat diubah manual
var latInput = document.getElementById("lat-gambar");
var lonInput = document.getElementById("lon-gambar");
var geocodeTimeout = null;
function setupGeocodeTrigger(input) {
  input.addEventListener("input", function() {
    clearTimeout(geocodeTimeout);
    geocodeTimeout = setTimeout(function() {
      var lat = parseFloat(latInput.value.replace(",", "."));
      var lon = parseFloat(lonInput.value.replace(",", "."));
      if (!isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
        reverseGeocode(lat, lon);
      }
    }, 1000);
  });
}
if (latInput) setupGeocodeTrigger(latInput);
if (lonInput) setupGeocodeTrigger(lonInput);

// Banner pengingat kalibrasi: tampil bila masih memakai kalibrasi bawaan.
// Bisa ditutup; muncul lagi pada kunjungan berikutnya (sessionStorage).
(function() {
  var banner = document.getElementById("banner-kalibrasi");
  if (!banner) return;
  var tutup = document.getElementById("banner-kalibrasi-tutup");
  if (tutup) tutup.addEventListener("click", function() {
    banner.hidden = true;
    try { sessionStorage.setItem("jp-banner-kalibrasi", "tutup"); } catch (e) {}
  });
  try {
    if (sessionStorage.getItem("jp-banner-kalibrasi") === "tutup") return;
  } catch (e) {}
  fetch("/api/kalibrasi").then(function(r) { return r.json(); }).then(function(st) {
    if (st && (st.metode === "bawaan" || !st.metode)) {
      banner.hidden = false;
    }
  }).catch(function(err) { console.warn("[JalanPantau] banner kalibrasi", err); });
})();
