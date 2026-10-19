{/* Tab + live stream: start/stop, stats polling, snapshot -> PDF. */}
const tabGambar = document.getElementById("tab-gambar");
const tabLive = document.getElementById("tab-live");
const panelGambar = document.getElementById("panel-gambar");
const panelLive = document.getElementById("panel-live");

function pilihTab(live) {
  tabGambar.classList.toggle("aktif", !live);
  tabLive.classList.toggle("aktif", live);
  tabGambar.setAttribute("aria-selected", String(!live));
  tabLive.setAttribute("aria-selected", String(live));
  panelGambar.hidden = live;
  panelLive.hidden = !live;
}
tabGambar.addEventListener("click", () => pilihTab(false));
tabLive.addEventListener("click", () => pilihTab(true));

const sumber = document.getElementById("sumber");
const confLive = document.getElementById("conf-live");
const confLiveOut = document.getElementById("conf-live-out");
const statusLive = document.getElementById("status-live");
const slotLive = document.getElementById("slot-live");
const hasilLive = document.getElementById("hasil-live");
const dialogTabelLive = document.getElementById("dialog-tabel-live");
const btnMulai = document.getElementById("mulai");
const btnBerhenti = document.getElementById("berhenti");
let polling = null;
let snapshot = null;

// Dialog tabel temuan live (tanpa skor prioritas). Tombol dibiarkan selalu
// tampil di panel live; bila sesi belum punya snapshot, ambil dulu saat diklik.
const btnBukaTabelLive = document.getElementById("buka-tabel-live");
if (btnBukaTabelLive && dialogTabelLive) {
  btnBukaTabelLive.addEventListener("click", async () => {
    if (!snapshot) await ambilSnapshot();
    if (!snapshot) {
      // Pesan mengikuti status terakhir (mis. "Belum ada track terekam…" atau
      // peringatan login dari server) agar tidak menyesatkan.
      const pesan = (statusLive.textContent || "").trim()
        || "Belum ada temuan terekam pada sesi ini.";
      showToast("Tabel Temuan", pesan, "info");
      return;
    }
    document.getElementById("dtl-sub").textContent =
      document.getElementById("total-live-nilai").textContent;
    dialogTabelLive.showModal();
  });
  dialogTabelLive.querySelectorAll("[data-tutup]").forEach((b) =>
    b.addEventListener("click", () => dialogTabelLive.close()));
  dialogTabelLive.addEventListener("click", (e) => { if (e.target === dialogTabelLive) dialogTabelLive.close(); });
}

// Token kepemilikan stream. Server hanya punya SATU StreamManager untuk
// seluruh aplikasi, jadi tanpa token ini tab kedua bisa mematikan atau
// merebut stream milik tab pertama. Diterima dari setiap jawaban start
// yang berhasil, dan dikirim balik pada stop/anotasi/snapshot.
let streamToken = null;

// Bungkus body JSON + token. Wrapper fetch global di base.html sudah
// menambahkan header CSRF untuk metode mutasi, jadi ini hanya body-nya.
function jsonBody(extra) {
  return {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(Object.assign({ token: streamToken }, extra || {})),
  };
}


confLive.addEventListener("input", () => {
  confLiveOut.textContent = Number(confLive.value).toFixed(2).replace(".", ",");
});
sumber.addEventListener("change", () => {
  document.getElementById("in-webcam").hidden = sumber.value !== "webcam";
  document.getElementById("in-ipcam").hidden = sumber.value !== "ipcam";
  document.getElementById("in-file").hidden = sumber.value !== "file";
});

// Mode Performa: selaraskan interval inferensi dengan preset saat dipilih.
const performa = document.getElementById("performa");
const PRESET_SKIP = { halus: "1", seimbang: "1" };
if (performa) performa.addEventListener("change", () => {
  const s = document.getElementById("skip");
  if (s && PRESET_SKIP[performa.value]) s.value = PRESET_SKIP[performa.value];
});
function performaLive() {
  return performa ? performa.value : undefined;
}

function badge(sev) {
  const map = { ringan: "RINGAN", sedang: "SEDANG", berat: "BERAT" };
  const k = String(sev).toLowerCase();
  return `<span class="badge badge-${esc(k)}"><span class="badge-dot"></span>${esc(map[k] || sev)}</span>`;
}
// P4 XSS: escape sebelum innerHTML (rows snapshot dari server).
function esc(v) {
  return String(v ?? "").replace(/[&<>"'`=]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
    "'": "&#39;", "`": "&#96;", "=": "&#61;",
  }[c]));
}
function confStr(c) {
  if (c == null) return "-";
  const v = Number(c);
  return `${String(v.toFixed(2)).replace(".", ",")} (${Math.round(v * 100)}%)`;
}

// Kosongkan kartu KPI live saat sesi baru dimulai agar angka sesi lama tidak
// nyangkut. Kartu sendiri tidak disembunyikan saat sesi berakhir (lihat
// hentikan) supaya angka terakhir sesi tetap terbaca.
function resetKartuLive() {
  ["fps-stat", "fps-infer-stat", "unik-stat", "deteksi-stat"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.textContent = "0";
  });
  // Keterangan dinamis juga dikembalikan ke netral, supaya angka sesi lama
  // tidak tertinggal di baris kecil.
  const set = (id, teks) => {
    const el = document.getElementById(id);
    if (el) el.textContent = teks;
  };
  set("fps-tampil-ket", "Preview");
  set("fps-infer-ket", "Model YOLO");
  set("deteksi-ket", "0 / inferensi");
}

// Tampilkan perangkat + backend live yang benar-benar dipakai, supaya alasan
// perbedaan kecepatan antar mesin terlihat tanpa menebak dari log server.
// Live memakai .pt di GPU dan .onnx di CPU (config `mode_backend`). Nilai di
// kartu sengaja PENDEK ("GPU"/"CPU") karena kartunya kecil; nama GPU lengkap
// ditaruh di tooltip (title) supaya tidak terpotong elipsis.
function isiPerangkat(p) {
  const nilai = document.getElementById("perangkat-stat");
  const ket = document.getElementById("perangkat-ket");
  if (!nilai || !p) return;
  const rinci = `${p.cuda ? (p.gpu || "CUDA") : "tanpa CUDA"} · backend live: ` +
    `${p.backend_live || "-"} · mode: ${p.mode_backend || "auto"}`;
  nilai.textContent = p.cuda ? "GPU" : "CPU";
  if (ket) ket.textContent = `Live: ${p.backend_live || "-"}`;
  nilai.title = rinci;
  if (ket) ket.title = rinci;
}

// Keterangan kecil di kartu KPI. Tujuannya mencegah salah tafsir: "titik unik"
// dan "deteksi aktif" adalah angka KUMULATIF sepanjang sesi, sehingga mode yang
// lebih cepat selalu terlihat lebih besar hanya karena memeriksa lebih banyak
// frame — bukan karena lebih banyak menemukan per frame.
//
// Yang adil dibandingkan adalah:
//   - deteksi per inferensi (rata_deteksi), dan
//   - persentase frame yang benar-benar diperiksa model.
// Keduanya ditampilkan di sini, berdampingan dengan angka kumulatifnya.
function isiMetrik(s) {
  const set = (id, teks) => {
    const el = document.getElementById(id);
    if (el) el.textContent = teks;
  };
  const rata = Number(s.rata_deteksi || 0).toFixed(2).replace(".", ",");
  set("deteksi-ket", `${rata} / inferensi`);
  const persen = s.frame
    ? Math.min(100, Math.round((s.n_inferensi / s.frame) * 100)) : 0;
  set("fps-infer-ket", `diperiksa ${persen}% frame`);
  // Resolusi yang ditampilkan adalah imgsz EFEKTIF (sudah dijepit di backend
  // agar tidak pernah melebihi lebar frame), bukan nilai preset mentah.
  const preset = s.performa || "manual";
  set("fps-tampil-ket", s.imgsz_live ? `${preset} · ${s.imgsz_live}px` : preset);
}

async function refreshStats() {
  try {
    const res = await fetch("/api/stream/stats");
    const s = await res.json();
    if (s.error) {
      statusLive.textContent = `Galat: ${s.error}`;
      statusLive.classList.add("galat");
      if (window.showCameraError) window.showCameraError(`Galat stream: ${s.error}`);
      return hentikan(false);
    }
    if (window.hideCameraError) window.hideCameraError();
    if (s.finished) {
      statusLive.textContent = "Video selesai diputar.";
      return hentikan(false);
    }
    statusLive.classList.remove("galat");
    statusLive.textContent =
      `Tampil ${s.fps_tampil} FPS · Inferensi ${s.fps_infer} FPS · ${s.unik} titik unik (total sesi) · ${s.deteksi} deteksi (total sesi) · ${s.rata_deteksi ?? 0} deteksi/inferensi · terlihat ~${s.tampil ?? 0} · frame ${s.frame} · ${s.source}`;
    // isi KPI cards (jika ada)
    const cards = document.getElementById("stat-cards-wrap");
    if (cards) {
      if (document.getElementById("fps-stat"))  document.getElementById("fps-stat").textContent = s.fps_tampil;
      if (document.getElementById("fps-infer-stat")) document.getElementById("fps-infer-stat").textContent = s.fps_infer;
      if (document.getElementById("unik-stat")) document.getElementById("unik-stat").textContent = s.unik;
      if (document.getElementById("deteksi-stat")) document.getElementById("deteksi-stat").textContent = s.deteksi;
      isiPerangkat(s.perangkat);
      isiMetrik(s);
      cards.hidden = false;
    }
  } catch {
    statusLive.textContent = "Koneksi ke server putus.";
  }
}

async function mulai() {
  btnMulai.disabled = true;
  statusLive.classList.remove("galat");
  statusLive.textContent = "Membuka sumber…";
  hasilLive.hidden = true;
  snapshot = null;
  resetKartuLive();
  // Hentikan stream yang sedang berjalan sebelum mulai yang baru
  if (polling) { clearInterval(polling); polling = null; }
  await fetch("/api/stream/stop", { method: "POST", ...jsonBody() }).catch(() => {});
  try {
    if (sumber.value === "file") {
      const berkas = document.getElementById("video").files[0];
      if (!berkas) throw new Error("Pilih berkas video dulu.");
      statusLive.textContent = "Mengunggah video…";
      const data = new FormData();
      data.append("video", berkas);
      data.append("conf", confLive.value);
      data.append("frame_skip", document.getElementById("skip").value);
      if (performaLive()) data.append("performa", performaLive());
      if (document.getElementById("malam-live").checked) data.append("malam", "1");
      if (streamToken) data.append("token", streamToken);
      const up = await fetch("/api/video", { method: "POST", body: data });
      const jup = await up.json();
      if (!up.ok) throw new Error(jup.error || "Upload gagal.");
      streamToken = jup.token || null;
    } else {
      const target = sumber.value === "webcam"
        ? Number(document.getElementById("webcam-idx").value)
        : document.getElementById("ipcam-url").value;
      const res = await fetch("/api/stream/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: sumber.value, target,
          conf: confLive.value,
          frame_skip: document.getElementById("skip").value,
          performa: performaLive(),
          malam: document.getElementById("malam-live").checked,
          token: streamToken,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Gagal membuka stream.");
      streamToken = json.token || null;
    }
    slotLive.classList.remove("kosong");
    // Cache-buster: timestamp untuk force browser fetch stream baru
    const ts = Date.now();
    slotLive.innerHTML = `<img src="/api/stream?t=${ts}" alt="Stream deteksi live">`;
    btnBerhenti.disabled = false;
    statusLive.textContent = "Stream berjalan…";
    polling = setInterval(refreshStats, 1000);
    refreshStats();
  } catch (err) {
    statusLive.textContent = err.message;
    statusLive.classList.add("galat");
    btnMulai.disabled = false;
  }
}

async function hentikan(manual = true) {
  if (polling) { clearInterval(polling); polling = null; }
  if (manual) {
    await fetch("/api/stream/stop", { method: "POST", ...jsonBody() }).catch(() => {});
    statusLive.textContent = "Stream berhenti. Ambil snapshot untuk laporan, atau mulai lagi.";
  }
  btnMulai.disabled = false;
  btnBerhenti.disabled = true;
  // Kartu KPI live sengaja TIDAK disembunyikan di sini: angka sesi terakhir
  // tetap terbaca setelah video selesai. Direset saat sesi baru dimulai.
  await ambilSnapshot();
}

async function ambilSnapshot() {
  try {
    const res = await fetch("/api/stream/snapshot", { method: "POST", ...jsonBody() });
    const json = await res.json();
    if (!res.ok) {
      if (!hasilLive.hidden) return;
      statusLive.textContent = json.error || statusLive.textContent;
      return;
    }
    const lokasi = document.getElementById("lokasi").value.trim();
    snapshot = { ...json, namaBerkas: `Live (${lokasi || "tanpa lokasi"})` };
    document.getElementById("total-live-nilai").textContent =
      `Sesi: ${json.rows.length} titik unik`;
    document.getElementById("tabel-live").innerHTML =
      `<table class="jp-table"><thead><tr><th>TRACK ID</th><th>KELAS KERUSAKAN</th><th>UKURAN</th><th>SEVERITY</th><th>CONF</th></tr></thead><tbody>` +
      json.rows.map((r) =>
        `<tr><td class="jp-num">${esc(r.track_id)}</td><td><span class="jp-cell-main">${esc(r.kelas)}</span></td><td class="jp-num">${esc(r.dasar)}</td><td>${badge(r.severity)}</td><td class="jp-num">${esc(confStr(r.conf_max != null ? r.conf_max : r.conf))}</td></tr>`
      ).join("") + `</tbody></table>`;
    hasilLive.hidden = false;
  } catch { /* abaikan bila server mati */ }
}

btnMulai.addEventListener("click", mulai);
btnBerhenti.addEventListener("click", () => hentikan(true));

document.getElementById("demo").addEventListener("click", async () => {
  btnMulai.disabled = true;
  statusLive.classList.remove("galat");
  statusLive.textContent = "Memutar video contoh…";
  hasilLive.hidden = true;
  snapshot = null;
  resetKartuLive();
  // Hentikan stream sebelumnya (bila ada) agar video demo selalu mulai dari awal.
  if (polling) { clearInterval(polling); polling = null; }
  await fetch("/api/stream/stop", { method: "POST", ...jsonBody() }).catch(() => {});
  try {
    const res = await fetch("/api/demo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conf: confLive.value, frame_skip: document.getElementById("skip").value, performa: performaLive(), malam: document.getElementById("malam-live").checked, token: streamToken }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Gagal memutar video contoh.");
    streamToken = json.token || null;
    slotLive.classList.remove("kosong");
    // Cache-buster: paksa browser membuka koneksi stream baru (bukan memakai
    // koneksi MJPEG lama yang sudah selesai).
    const ts = Date.now();
    slotLive.innerHTML = `<img src="/api/stream?t=${ts}" alt="Stream video contoh">`;
    btnBerhenti.disabled = false;
    polling = setInterval(refreshStats, 1000);
    refreshStats();
  } catch (err) {
    statusLive.textContent = err.message;
    statusLive.classList.add("galat");
    btnMulai.disabled = false;
  }
});

function bacaKoordinatLive() {
  const num = (id) => {
    const v = document.getElementById(id).value.trim().replace(",", ".");
    return v === "" ? null : Number(v);
  };
  return { lat: num("lat-live"), lon: num("lon-live") };
}

document.getElementById("simpan-live").addEventListener("click", async () => {
  if (!snapshot) return;
  const btn = document.getElementById("simpan-live");
  if (btn.disabled) return;
  btn.disabled = true;
  try {
    const { lat, lon } = bacaKoordinatLive();
    // Kunci idempotensi: satu ref tetap untuk satu aksi simpan.
    const refSimpan = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : ("ref-" + Date.now() + "-" + Math.random().toString(16).slice(2));
    const kirim = (izinkan) => fetch("/api/riwayat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sumber: snapshot.namaBerkas,
        lokasi: document.getElementById("lokasi").value.trim(),
        lat, lon, model: snapshot.model,
        rows: snapshot.rows, total: snapshot.total,
        image_b64: snapshot.image_b64,
        client_ref: refSimpan, izinkan_duplikat: !!izinkan,
      }),
    });
    let res = await kirim(false);
    let json = await res.json().catch(() => ({}));
    // Belum login (atau sesi habis): tawarkan login via modal, lalu ulangi sekali.
    if (res.status === 401 && window.jpButuhLogin) {
      const masuk = await window.jpButuhLogin();
      if (!masuk) {
        statusLive.textContent = "Dibatalkan — masuk untuk menyimpan ke riwayat.";
        statusLive.classList.remove("galat");
        return;
      }
      res = await kirim(false);
      json = await res.json().catch(() => ({}));
    }
    if (res.ok && json.duplikat && json.alasan === "koordinat") {
      const lanjut = await window.jpConfirm("Riwayat Serupa",
        `Sudah ada riwayat di titik ini (ID ${json.id}). Tetap simpan sebagai riwayat baru?`,
        { okText: "Tetap Simpan" });
      if (!lanjut) {
        statusLive.textContent = `Dibatalkan — riwayat serupa sudah ada (ID ${json.id}).`;
        statusLive.classList.remove("galat");
        return;
      }
      res = await kirim(true);
      json = await res.json().catch(() => ({}));
    }
    if (!res.ok) {
      statusLive.textContent = json.error || "Gagal menyimpan.";
      statusLive.classList.add("galat");
      if (window.jpToast) {
        var judulGagal = res.status === 403 ? "Aksi Ditolak (403)" : "Gagal Menyimpan";
        window.jpToast("error", judulGagal, json.error || "Gagal menyimpan ke riwayat.");
      }
      return;
    }
    if (json.duplikat) {
      statusLive.textContent = `Sudah tersimpan sebelumnya (ID ${json.id}).`;
      statusLive.classList.remove("galat");
      if (window.jpToast) window.jpToast("info", "Sudah Ada", "Riwayat ini sudah tersimpan (ID " + json.id + ").");
      return;
    }
    const amin = peringatanGPS(lat, lon);
    statusLive.classList.toggle("galat", amin !== null);
    statusLive.textContent = amin !== null ? `${amin} (ID ${json.id}).` : `Tersimpan ke riwayat (ID ${json.id}).`;
    if (window.jpToast) {
      if (amin !== null) window.jpToast("warning", "Tersimpan Tanpa Titik Peta", amin + " (ID " + json.id + ").");
      else window.jpToast("success", "Tersimpan", "Hasil live tersimpan ke riwayat (ID " + json.id + ").");
    }
  } catch (err) {
    statusLive.textContent = `Gagal menyimpan: ${err.message}`;
    statusLive.classList.add("galat");
    if (window.jpToast) window.jpToast("error", "Gagal Menyimpan", "Gagal menyimpan: " + err.message);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("unduh-live").addEventListener("click", async () => {
  if (!snapshot) return;
  const res = await fetch("/api/laporan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rows: snapshot.rows,
      total: snapshot.total,
      image_b64: snapshot.image_b64,
      source: snapshot.namaBerkas,
      model: snapshot.model,
    }),
  });
  if (!res.ok) {
    statusLive.textContent = "Gagal membuat PDF.";
    statusLive.classList.add("galat");
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "laporan_jalan_live.pdf";
  a.click();
  URL.revokeObjectURL(a.href);
});

/* === Toolbar & Camera Error State === */
(function() {
  // Snapshot button: pakai snapshot live yang sudah ada (ambilSnapshot)
  var btnSnap = document.getElementById("btn-snapshot");
  if (btnSnap) btnSnap.addEventListener("click", () => {
    ambilSnapshot().then(() => {
      showToast("Snapshot", "Snapshot sesi live diperbarui (tabel + total).", "success");
    }).catch(() => {
      showToast("Snapshot", "Gagal mengambil snapshot.", "galat");
    });
  });

  // Toggle Box annotation -> toggle di server (frame berikut tampil polos)
  var btnBox = document.getElementById("btn-toggle-box");
  var boxVisible = true;
  if (btnBox) btnBox.addEventListener("click", () => {
    fetch("/api/stream/anotasi", { method: "POST", ...jsonBody() })
      .then(function(r) { return r.json(); })
      .then(function(j) {
        if (!j.ok) throw new Error(j.error || "gagal");
        boxVisible = !!j.anotasi;
        btnBox.style.background = boxVisible ? "var(--jp-primary)" : "var(--jp-container)";
        btnBox.style.color = boxVisible ? "#fff" : "var(--jp-tx2)";
        showToast("Anotasi", boxVisible ? "Bounding box ditampilkan" : "Bounding box disembunyikan", "info");
      })
.catch(function(e) {
          console.error("[JalanPantau] simpan anotasi live", e);
          showToast("Anotasi", "Server tidak merespons.", "galat");
      });
  });

  // Toggle OSD
  var btnOsd = document.getElementById("btn-toggle-osd");
  var osd = document.getElementById("live-osd");
  var osdVisible = true;
  if (btnOsd && osd) btnOsd.addEventListener("click", () => {
    osdVisible = !osdVisible;
    osd.style.display = osdVisible ? "flex" : "none";
    btnOsd.style.background = osdVisible ? "var(--jp-container)" : "var(--jp-primary)";
    btnOsd.style.color = osdVisible ? "var(--jp-tx2)" : "#fff";
  });

  // Camera error state
  var btnRetry = document.getElementById("btn-retry-cam");
  var btnBackup = document.getElementById("btn-switch-backup");
  var btnLog = document.getElementById("btn-download-log");
  var errState = document.getElementById("camera-error-state");

  if (btnRetry) btnRetry.addEventListener("click", () => {
    // Restart stream sesuai sumber yang sedang dipilih (bukan sekadar toast).
    btnRetry.disabled = true;
    btnRetry.innerHTML = '<span>Menghubungkan...</span>';
    mulai()
      .then(() => {
        if (errState) errState.style.display = "none";
        showToast("Koneksi", "Stream dimulai ulang.", "success");
      })
      .catch(() => {
        showToast("Koneksi", "Gagal menyambung ulang. Coba sumber lain.", "galat");
      })
      .finally(() => {
        btnRetry.disabled = false;
        btnRetry.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg><span>Coba Hubungkan Ulang</span>';
      });
  });

  if (btnBackup) btnBackup.addEventListener("click", () => {
    // Alih ke IP-cam: pilih sumber ipcam di form lalu fokus ke kolom URL.
    sumber.value = "ipcam";
    sumber.dispatchEvent(new Event("change"));
    var urlEl = document.getElementById("ipcam-url");
    if (urlEl) urlEl.focus();
    showToast("Kamera Cadangan", "Mode IP-camera dipilih. Isi URL stream lalu tekan Mulai.", "info");
    if (errState) errState.style.display = "none";
  });

  if (btnLog) btnLog.addEventListener("click", () => {
    // Unduh log sesi (stats + error) sebagai file teks nyata.
    fetch("/api/stream/stats")
      .then(function(r) { return r.json(); })
      .then(function(s) {
        var baris = [
          "JalanPantau - Log Sesi Live",
          "waktu   : " + new Date().toISOString(),
          "sumber  : " + (s.source || "-"),
          "running : " + s.running,
          "finished: " + s.finished,
          "error   : " + (s.error || "-"),
          "fps     : " + s.fps,
          "perangkat: " + (s.perangkat ? (s.perangkat.cuda ? s.perangkat.gpu : "CPU") : "-") +
            " (backend live: " + (s.perangkat ? s.perangkat.backend_live : "-") + ")",
          "performa: " + (s.performa || "-") + " (imgsz efektif " +
            (s.imgsz_live || "-") + " px)",
          "frame   : " + s.frame,
          "diperiksa: " + (s.frame
            ? Math.min(100, Math.round((s.n_inferensi / s.frame) * 100)) : 0) +
            "% frame (" + s.n_inferensi + " inferensi)",
          "unik    : " + s.unik,
          "deteksi : " + s.deteksi,
          "rata    : " + (s.rata_deteksi ?? 0) + " deteksi/inferensi",
        ].join("\n");
        var a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([baris], { type: "text/plain" }));
        a.download = "jalanpantau_live.log";
        a.click();
        URL.revokeObjectURL(a.href);
        showToast("Log", "Log sesi terunduh.", "success");
      })
.catch(function(e) {
          console.error("[JalanPantau] ambil log live", e);
          showToast("Log", "Gagal mengambil log dari server.", "galat");
      });
  });


  // Stop stream saat page di-refresh/tutup
  window.addEventListener("beforeunload", function() {
    if (polling) {
      // fetch keepalive: header CSRF (dipasang wrapper global) tetap terkirim
      try {
        fetch("/api/stream/stop", { method: "POST", keepalive: true, ...jsonBody() });
      } catch (e) { /* abaikan */ }
      clearInterval(polling);
      polling = null;
    }
  });

  // Expose function to show error state (for live.js error handling)
  window.showCameraError = function(msg) {
    if (errState) errState.style.display = "grid";
    // Tampilkan penyebab asli dari server; judul kartu disesuaikan bila
    // bukan galat perangkat (mis. tracker/model gagal) agar tak menyesatkan.
    var diag = document.getElementById("camera-error-diagnosa");
    if (diag && msg) diag.textContent = msg;
    var judul = document.getElementById("camera-error-judul");
    if (judul) {
      judul.textContent = (msg && /tracking|model/i.test(msg))
        ? "Galat Pemrosesan Live"
        : "Koneksi Kamera Inspeksi Terputus";
    }
    if (statusLive) {
      statusLive.textContent = msg || "Koneksi kamera terputus.";
      statusLive.classList.add("galat");
    }
  };
  window.hideCameraError = function() {
    if (errState) errState.style.display = "none";
  };
})();

function showToast(title, message, type) {
  var container = document.getElementById("toast-container");
  if (!container) return;
  var toast = document.createElement("div");
  toast.className = "toast";
  var icons = { info: "i", success: "ok", galat: "!" };
  toast.innerHTML = '<span class="toast-icon">' + esc(icons[type] || icons.info) + '</span><div class="toast-content"><div class="toast-title">' + esc(title) + '</div><div class="toast-message">' + esc(message) + '</div></div>';
  container.appendChild(toast);
  setTimeout(function () { toast.remove(); }, 5000);
}
