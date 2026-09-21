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
const btnMulai = document.getElementById("mulai");
const btnBerhenti = document.getElementById("berhenti");
let polling = null;
let snapshot = null;

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
const PRESET_SKIP = { halus: "3", seimbang: "2", akurat: "1" };
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
      `Tampil ${s.fps_tampil} FPS · Inferensi ${s.fps_infer} FPS · ${s.unik} titik unik · ${s.deteksi} deteksi · frame ${s.frame} · ${s.source}`;
    // isi KPI cards (jika ada)
    const cards = document.getElementById("stat-cards");
    if (cards) {
      if (document.getElementById("fps-stat"))  document.getElementById("fps-stat").textContent = s.fps_tampil;
      if (document.getElementById("fps-infer-stat")) document.getElementById("fps-infer-stat").textContent = s.fps_infer;
      if (document.getElementById("unik-stat")) document.getElementById("unik-stat").textContent = s.unik;
      if (document.getElementById("deteksi-stat")) document.getElementById("deteksi-stat").textContent = s.deteksi;
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
  // Hentikan stream yang sedang berjalan sebelum mulai yang baru
  if (polling) { clearInterval(polling); polling = null; }
  await fetch("/api/stream/stop", { method: "POST" }).catch(() => {});
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
      const up = await fetch("/api/video", { method: "POST", body: data });
      const jup = await up.json();
      if (!up.ok) throw new Error(jup.error || "Upload gagal.");
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
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Gagal membuka stream.");
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
    await fetch("/api/stream/stop", { method: "POST" }).catch(() => {});
    statusLive.textContent = "Stream berhenti. Ambil snapshot untuk laporan, atau mulai lagi.";
  }
  btnMulai.disabled = false;
  btnBerhenti.disabled = true;
  const cards = document.getElementById("stat-cards");
  if (cards) cards.hidden = true;
  await ambilSnapshot();
}

async function ambilSnapshot() {
  try {
    const res = await fetch("/api/stream/snapshot", { method: "POST" });
    const json = await res.json();
    if (!res.ok) {
      if (!hasilLive.hidden) return;
      statusLive.textContent = json.error || statusLive.textContent;
      return;
    }
    const lokasi = document.getElementById("lokasi").value.trim();
    snapshot = { ...json, namaBerkas: `Live (${lokasi || "tanpa lokasi"})` };
    document.getElementById("total-live-nilai").textContent =
      `Sesi: ${json.rows.length} titik unik · Total estimasi: ${json.total_str}`;
    document.getElementById("tabel-live").innerHTML =
      `<table class="jp-table"><thead><tr><th>TRACK ID</th><th>KELAS KERUSAKAN</th><th>UKURAN</th><th>SEVERITY</th><th>CONF</th><th class="jp-num-right">ESTIMASI</th></tr></thead><tbody>` +
      json.rows.map((r) =>
        `<tr><td class="jp-num">${esc(r.track_id)}</td><td><span class="jp-cell-main">${esc(r.kelas)}</span></td><td class="jp-num">${esc(r.dasar)}</td><td>${badge(r.severity)}</td><td class="jp-num">${esc(confStr(r.conf_max != null ? r.conf_max : r.conf))}</td><td class="jp-num-right">${esc(r.total_str)}</td></tr>`
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
  try {
    const res = await fetch("/api/demo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conf: confLive.value, frame_skip: document.getElementById("skip").value, performa: performaLive(), malam: document.getElementById("malam-live").checked }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Gagal memutar video contoh.");
    slotLive.classList.remove("kosong");
    slotLive.innerHTML = `<img src="/api/stream" alt="Stream video contoh">`;
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
  const res = await fetch("/api/riwayat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sumber: snapshot.namaBerkas,
      lokasi: document.getElementById("lokasi").value.trim(),
      lat, lon, model: snapshot.model,
      rows: snapshot.rows, total: snapshot.total,
      image_b64: snapshot.image_b64,
    }),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    statusLive.textContent = json.error || "Gagal menyimpan.";
    statusLive.classList.add("galat");
    return;
  }
  const amin = peringatanGPS(lat, lon);
  statusLive.classList.toggle("galat", amin !== null);
  statusLive.textContent = amin !== null ? `${amin} (ID ${json.id}).` : `Tersimpan ke riwayat (ID ${json.id}).`;
  } catch (err) {
    statusLive.textContent = `Gagal menyimpan: ${err.message}`;
    statusLive.classList.add("galat");
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
    fetch("/api/stream/anotasi", { method: "POST" })
      .then(function(r) { return r.json(); })
      .then(function(j) {
        if (!j.ok) throw new Error("gagal");
        boxVisible = !!j.anotasi;
        btnBox.style.background = boxVisible ? "var(--jp-primary)" : "var(--jp-container)";
        btnBox.style.color = boxVisible ? "#fff" : "var(--jp-tx2)";
        showToast("Anotasi", boxVisible ? "Bounding box ditampilkan" : "Bounding box disembunyikan", "info");
      })
      .catch(function() {
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

  // Fullscreen
  var btnFull = document.getElementById("btn-fullscreen");
  if (btnFull) btnFull.addEventListener("click", () => {
    var viewer = document.getElementById("viewer-live");
    if (!viewer) return;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else if (viewer.requestFullscreen) viewer.requestFullscreen().catch(() => {});
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
          "frame   : " + s.frame,
          "unik    : " + s.unik,
          "deteksi : " + s.deteksi,
        ].join("\n");
        var a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([baris], { type: "text/plain" }));
        a.download = "jalanpantau_live.log";
        a.click();
        URL.revokeObjectURL(a.href);
        showToast("Log", "Log sesi terunduh.", "success");
      })
      .catch(function() {
        showToast("Log", "Gagal mengambil log dari server.", "galat");
      });
  });

  // Stop stream saat page di-refresh/tutup
  window.addEventListener("beforeunload", function() {
    if (polling) {
      // Gunakan sendBeacon untuk reliable request saat page unload
      navigator.sendBeacon("/api/stream/stop");
      clearInterval(polling);
      polling = null;
    }
  });

  // Expose function to show error state (for live.js error handling)
  window.showCameraError = function(msg) {
    if (errState) errState.style.display = "grid";
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
