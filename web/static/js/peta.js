{/* Peta Leaflet: marker per sesi berkoordinat + ringkasan wilayah + Live GPS Tracking + Lokasi Dinamis. */}
/* === Inisialisasi Peta dengan Lokasi Dinamis === */
// Gunakan sistem lokasi dari lokasi_dinamis.js
var lokasiDef = LOKASI.getDefault();
var lokasiAktif = lokasiDef.key;
var defaultLl = lokasiDef.data.ll;
var defaultZoom = lokasiDef.data.zoom;

var map = L.map("map", { zoomControl: false }).setView(defaultLl, defaultZoom);
L.control.zoom({ position: "bottomleft" }).addTo(map);

const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);
const satelit = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19, attribution: "Esri WorldImagery" });
let modeSatelit = false;

let semua = [];
let lapis = L.layerGroup().addTo(map);
const markerPerId = {};

/* === Live GPS Tracking (seperti Google Maps) === */
var gpsMarker = null;
var gpsCircle = null;
var gpsWatchId = null;

function buatMarkerGPS(ll) {
  // Hapus marker lama jika ada
  if (gpsMarker) { try { lapis.removeLayer(gpsMarker); } catch(e){} }
  if (gpsCircle) { try { lapis.removeLayer(gpsCircle); } catch(e){} }
  
  // Marker biru dengan animasi pulse (seperti Google Maps)
  var html = '<div class="gps-marker"><div class="gps-dot"></div><div class="gps-pulse"></div></div>';
  gpsMarker = L.marker(ll, { icon: L.divIcon({ className: "", html: html, iconSize: [24, 24], iconAnchor: [12, 12] }), zIndexOffset: 1000 });
  gpsMarker.bindPopup("<b>Lokasi Anda</b><br>Lat: " + ll[0].toFixed(6) + "<br>Lon: " + ll[1].toFixed(6));
  gpsMarker.addTo(lapis);
  
  // Akurasi circle
  gpsCircle = L.circle(ll, { radius: 50, color: '#006194', fillColor: '#006194', fillOpacity: 0.15, weight: 1, opacity: 0.5 });
  gpsCircle.addTo(lapis);
}

function mulaiLiveGPS() {
  if (!("geolocation" in navigator)) {
    console.log("Browser tidak mendukung geolocation");
    return;
  }
  
  // Hentikan watch sebelumnya jika ada
  if (gpsWatchId !== null) {
    navigator.geolocation.clearWatch(gpsWatchId);
  }
  
  // Live tracking: update posisi setiap 5 detik atau saat bergerak > 10 meter
  gpsWatchId = navigator.geolocation.watchPosition(
    (pos) => {
      var ll = [pos.coords.latitude, pos.coords.longitude];
      var accuracy = pos.coords.accuracy || 50;
      
      // Update atau buat marker
      if (gpsMarker) {
        gpsMarker.setLatLng(ll);
        gpsMarker.setPopupContent("<b>Lokasi Anda</b><br>Lat: " + ll[0].toFixed(6) + "<br>Lon: " + ll[1].toFixed(6) + "<br>Akurasi: ±" + Math.round(accuracy) + "m");
      } else {
        buatMarkerGPS(ll);
        map.setView(ll, 15);
      }
      
      // Update circle akurasi
      if (gpsCircle) {
        gpsCircle.setLatLng(ll);
        gpsCircle.setRadius(accuracy);
      } else {
        gpsCircle = L.circle(ll, { radius: accuracy, color: '#006194', fillColor: '#006194', fillOpacity: 0.15, weight: 1, opacity: 0.5 });
        gpsCircle.addTo(lapis);
      }
      
      console.log("GPS berhasil:", ll, "akurasi:", accuracy, "m");
    },
    (err) => {
      console.log("GPS error:", err.message);
      if (err.code === 1) {
        // Permission denied - tampilkan notifikasi sekali
        if (!document.getElementById("gps-notif")) {
          var notif = document.createElement("div");
          notif.id = "gps-notif";
          notif.style.cssText = "position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:1000;background:rgba(254,242,242,.95);color:#ba1a1a;padding:8px 16px;border-radius:8px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);border-left:4px solid #ba1a1a;max-width:90%;text-align:center";
          notif.innerHTML = "<b>GPS tidak diizinkan</b><br>Aktifkan izin lokasi di browser untuk live tracking.<br>Menggunakan lokasi default: <b>" + (LOKASI.DAERAH[lokasiAktif] || lokasiDef).nama + "</b>";
          document.querySelector(".jp-mapstage").appendChild(notif);
        }
      }
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000, distanceFilter: 10 }
  );
}

// Fungsi untuk mengubah lokasi default
window.gantiLokasiDefault = function(key) {
  if (LOKASI.setDefault(key)) {
    lokasiAktif = key;
    var d = LOKASI.DAERAH[key];
    map.setView(d.ll, d.zoom);
    return true;
  }
  return false;
};

// Update notifikasi GPS error dengan lokasi dinamis
function tampilkanNotifGPS(errorMsg) {
  if (!document.getElementById("gps-notif")) {
    var notif = document.createElement("div");
    notif.id = "gps-notif";
    notif.style.cssText = "position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:1000;background:rgba(254,242,242,.95);color:#ba1a1a;padding:8px 16px;border-radius:8px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);border-left:4px solid #ba1a1a;max-width:90%;text-align:center";
    var d = LOKASI.DAERAH[lokasiAktif];
    notif.innerHTML = "<b>" + errorMsg + "</b><br>Aktifkan izin lokasi di browser.<br>Menggunakan: <b>" + d.nama + "</b>";
    document.querySelector(".jp-mapstage").appendChild(notif);
  }
}

// Jalankan deteksi GPS setelah semua terinisialisasi
setTimeout(mulaiLiveGPS, 100);

function ikon(worst) {
  return L.divIcon({
    className: "",
    html: `<div class="titik titik-${String(worst).toLowerCase()}"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}
function rupiah(n) {
  return "Rp" + Number(n).toLocaleString("id-ID");
}
// P3: escape sebelum innerHTML/bindPopup (t.lokasi dari server bisa berisi HTML).
function esc(v) {
  return String(v ?? "").replace(/[&<>"'`=]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
    "'": "&#39;", "`": "&#96;", "=": "&#61;",
  }[c]));
}
function badgeHtml(worst) {
  const map = { ringan: "RINGAN", sedang: "SEDANG", berat: "BERAT" };
  const k = String(worst).toLowerCase();
  return `<span class="badge badge-${esc(k)}"><span class="badge-dot"></span>${esc(map[k] || worst)}</span>`;
}

function filterAktif() {
  return new Set(
    [...document.querySelectorAll(".f-sev")].filter((c) => c.checked).map((c) => c.value));
}
function kataKunci() {
  return (document.getElementById("peta-cari-jalan").value || "").toLowerCase().trim();
}
function cocok(t, aktif, q) {
  if (!aktif.has(t.worst)) return false;
  if (q && !(t.lokasi || "").toLowerCase().includes(q)) return false;
  return true;
}

function ringkasan(tampil) {
  const hitung = { Berat: 0, Sedang: 0, Ringan: 0 };
  let anggaran = 0;
  for (const t of tampil) {
    if (hitung[t.worst] !== undefined) hitung[t.worst] += 1;
    anggaran += Number(t.total_rp) || 0;
  }
  document.getElementById("peta-total").textContent = tampil.length;
  document.getElementById("peta-anggaran").textContent = rupiah(anggaran);
  document.getElementById("peta-prop-angka").textContent =
    `${hitung.Berat}B • ${hitung.Sedang}S • ${hitung.Ringan}R`;
  const tot = tampil.length || 1;
  document.getElementById("seg-berat").style.width = `${(hitung.Berat / tot) * 100}%`;
  document.getElementById("seg-sedang").style.width = `${(hitung.Sedang / tot) * 100}%`;
  document.getElementById("seg-ringan").style.width = `${(hitung.Ringan / tot) * 100}%`;
  for (const k of ["Berat", "Sedang", "Ringan"]) {
    const legEl = document.getElementById(`leg-${k.toLowerCase()}`);
    if (legEl) legEl.textContent = hitung[k];
    const chip = document.querySelector(`[data-sev-count="${k}"]`);
    if (chip) chip.textContent = semua.filter((t) => t.worst === k).length;
  }
  const top = [...tampil].sort((a, b) => (b.total_rp || 0) - (a.total_rp || 0)).slice(0, 5);
  var prioritasEl = document.getElementById("peta-list-prioritas");
  if (prioritasEl) {
    prioritasEl.innerHTML = top.length
      ? top.map((t) =>
        `<button type="button" class="jp-prio" data-fokus="${t.id}">` +
        `<span class="titik titik-${esc(String(t.worst).toLowerCase())}"></span>` +
        `<span class="jp-prio-teks"><strong>${esc(t.lokasi || "-")}</strong>` +
        `<small>${Number(t.n_temuan) || 0} temuan</small></span>` +
        `<span class="jp-prio-rp">${esc(rupiah(t.total_rp))}</span></button>`
      ).join("")
      : `<p class="jp-hint">Tidak ada titik pada filter ini.</p>`;
  }
  document.querySelectorAll("[data-fokus]").forEach((b) =>
    b.addEventListener("click", () => fokusMarker(Number(b.dataset.fokus))));
}

function fokusMarker(id) {
  const m = markerPerId[id];
  if (!m) return;
  map.setView(m.getLatLng(), Math.max(map.getZoom(), 15));
  m.openPopup();
}

function gambar(aturPandangan) {
  lapis.clearLayers();
  for (const k of Object.keys(markerPerId)) delete markerPerId[k];
  const aktif = filterAktif(), q = kataKunci();
  const tampil = semua.filter((t) => cocok(t, aktif, q));
  document.getElementById("peta-hitung").textContent =
    `${tampil.length} dari ${semua.length} titik tampil`;
  document.getElementById("peta-kosong").hidden = tampil.length > 0;
  const batas = [];
  for (const t of tampil) {
    const m = L.marker([t.lat, t.lon], { icon: ikon(t.worst) }).addTo(lapis);
    markerPerId[t.id] = m;
    const foto = t.ada_gambar
      ? `<br><button type="button" class="jp-linkbtn" data-foto="${t.id}">Lihat foto bukti</button>` : "";
    m.bindPopup(
      `<div class="jp-popup"><strong>${esc(t.lokasi || "-")}</strong><br>` +
      `${badgeHtml(t.worst)}<br>${Number(t.n_temuan) || 0} temuan · ${esc(rupiah(t.total_rp))}${foto}<br>` +
      `<a href="/riwayat">Buka di Riwayat</a></div>`);
    batas.push([t.lat, t.lon]);
  }
  ringkasan(tampil);
  if (aturPandangan && batas.length) map.fitBounds(batas, { padding: [40, 40], maxZoom: 16 });
  setTimeout(() => map.invalidateSize(), 100);
}

function resetFilter() {
  document.querySelectorAll(".f-sev").forEach((c) => { c.checked = true; });
  document.getElementById("peta-cari-jalan").value = "";
  document.getElementById("peta-kosong").hidden = true;
  gambar(true);
}

document.querySelectorAll(".f-sev").forEach((c) => c.addEventListener("change", () => gambar(false)));
document.getElementById("peta-cari-jalan").addEventListener("input", () => gambar(false));
document.getElementById("peta-reset-filter").addEventListener("click", resetFilter);
document.getElementById("chip-tutup").addEventListener("click", () => {
  document.getElementById("peta-kosong").hidden = true;
});
document.getElementById("map-fit").addEventListener("click", () => gambar(true));
document.getElementById("map-satelit").addEventListener("click", (e) => {
  modeSatelit = !modeSatelit;
  if (modeSatelit) { map.removeLayer(osm); satelit.addTo(map); }
  else { map.removeLayer(satelit); osm.addTo(map); }
  e.currentTarget.setAttribute("aria-pressed", String(modeSatelit));
});
document.getElementById("map-lokasi").addEventListener("click", () => {
  if (!("geolocation" in navigator)) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      var ll = [pos.coords.latitude, pos.coords.longitude];
      map.setView(ll, 15);
      // Tandai lokasi user
      L.marker(ll, { icon: L.divIcon({ className: "", html: '<div style="width:16px;height:16px;border-radius:50%;background:#006194;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.3)" />', iconSize: [16, 16], iconAnchor: [8, 8] }) }).addTo(lapis).bindPopup("Lokasi Anda").openPopup();
      // Cari titik terdekat
      cariTerdekat(ll);
    },
    () => { if (window.jpToast) window.jpToast("error", "Gagal Lokasi", "Tidak bisa mengakses lokasi. Pastikan izin lokasi diberikan."); },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

/* === Cari Titik Terdekat === */
var titikTerdekat = null;
function cariTerdekat(userLl) {
  var box = document.getElementById("peta-terdekat-box");
  var info = document.getElementById("peta-terdekat-info");
  if (!box || !info) return;  // P3: template belum render kartu (hindari TypeError)
  if (!semua.length) { titikTerdekat = null; box.style.display = "none"; return; }
  var minDist = Infinity, terdekat = null;
  for (const t of semua) {
    if (t.lat == null || t.lon == null) continue;
    var d = Math.pow(t.lat - userLl[0], 2) + Math.pow(t.lon - userLl[1], 2);
    if (d < minDist) { minDist = d; terdekat = t; }
  }
  titikTerdekat = terdekat;
  if (terdekat) {
    var jarak = (Math.sqrt(minDist) * 111).toFixed(2); // perkiraan km
    info.innerHTML = '<strong>' + esc(terdekat.lokasi || "-") + '</strong><br>' + (Number(terdekat.n_temuan) || 0) + ' temuan • ' + badgeHtml(terdekat.worst) + '<br><span style="font-family:var(--jp-mono);font-size:11px">±' + esc(jarak) + ' km dari lokasi Anda</span>';
    box.style.display = "block";
  } else {
    box.style.display = "none";
  }
}

var btnNavTerdekat = document.getElementById("peta-navigate-terdekat");
if (btnNavTerdekat) btnNavTerdekat.addEventListener("click", () => {
  if (titikTerdekat) fokusMarker(titikTerdekat.id);
});

/* === Search Feedback === */
var searchInput = document.getElementById("peta-cari-jalan");
if (searchInput) searchInput.addEventListener("input", function() {
  var q = kataKunci();
  // Tampilkan feedback pencarian
  var hitung = semua.filter(function(t) { return t.lokasi && t.lokasi.toLowerCase().includes(q); }).length;
  if (q.length > 0) {
    var countEl = document.getElementById("peta-hitung");
    if (countEl) countEl.textContent = hitung + " hasil untuk \"" + q + "\"";
  }
  gambar(false);
});
document.getElementById("toggle-drawer-btn").addEventListener("click", (e) => {
  const body = document.getElementById("drawer-body");
  body.hidden = !body.hidden;
  e.currentTarget.textContent = body.hidden ? "+" : "−";
});
document.getElementById("foto-x").addEventListener("click", () => {
  const dlg = document.getElementById("foto-dialog");
  if (dlg.open) dlg.close();
});
map.on("popupopen", (e) => {
  const btn = e.popup.getElement().querySelector("[data-foto]");
  if (btn) btn.addEventListener("click", () => bukaModalFoto(Number(btn.dataset.foto)));
});

/* === Modal Foto Bukti: gambar + diagnostik dari /api/riwayat/<id> ===
   Sebelumnya handler hanya mengisi src gambar sehingga panel diagnostik
   selalu tampil default kosong ("0 Kerusakan", "Rp 0"). */
var fotoDetail = null;

function bukaModalFoto(id) {
  var dlg = document.getElementById("foto-dialog");
  var img = document.getElementById("foto-img");
  fotoDetail = null;
  // Status memuat agar tidak terlihat seperti "tidak ada kerusakan"
  document.getElementById("foto-jml-kerusakan").textContent = "Memuat…";
  document.getElementById("foto-diag-text").textContent = "Mengambil data diagnostik…";
  document.getElementById("foto-tabel-kerusakan").innerHTML =
    '<p class="jp-hint">Memuat rincian temuan…</p>';
  img.removeAttribute("src");
  img.src = `/api/riwayat/${id}/gambar`;
  if (!dlg.open) dlg.showModal();
  fetch(`/api/riwayat/${id}`)
    .then((r) => { if (!r.ok) throw new Error("detail.bundle"); return r.json(); })
    .then((d) => { fotoDetail = d; isiModalFoto(d); })
    .catch(() => {
      document.getElementById("foto-jml-kerusakan").textContent = "Gagal memuat";
      document.getElementById("foto-diag-text").textContent =
        "Gagal mengambil data diagnostik. Foto tetap ditampilkan.";
      document.getElementById("foto-tabel-kerusakan").innerHTML =
        '<p class="jp-hint">Gagal memuat rincian temuan.</p>';
    });
}

function isiModalFoto(d) {
  const s = d.sesi || {};
  const temuan = d.temuan || [];
  const fmtTgl = (iso) => {
    try {
      return new Date(iso).toLocaleString("id-ID", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch { return iso || "-"; }
  };
  // Header
  document.getElementById("foto-id").textContent = `ID: ${s.id ?? "-"}`;
  document.getElementById("foto-tanggal").textContent = fmtTgl(s.waktu);
  document.getElementById("foto-judul").textContent = s.lokasi || "Foto Bukti Lapangan";
  const prio = document.getElementById("foto-prioritas");
  if (prio) {
    const w = s.worst || "-";
    prio.className = `badge badge-${String(w).toLowerCase()}`;
    prio.innerHTML = `<span class="badge-dot"></span>${esc(w)}`;
  }
  // Meta GPS + model
  const koor = (s.lat != null && s.lon != null)
    ? `${Number(s.lat).toFixed(6)}, ${Number(s.lon).toFixed(6)}` : "-";
  document.getElementById("foto-gps").textContent = koor;
  document.getElementById("foto-infer").textContent = s.model || "-";
  document.getElementById("foto-lat").textContent =
    `LAT: ${s.lat != null ? Number(s.lat).toFixed(6) : "-"}`;
  document.getElementById("foto-lon").textContent =
    `LON: ${s.lon != null ? Number(s.lon).toFixed(6) : "-"}`;
  // Ringkasan diagnostik
  const n = temuan.length;
  const worst = s.worst || "-";
  document.getElementById("foto-kondisi").textContent = `Kondisi ${worst}`;
  document.getElementById("foto-jml-kerusakan").textContent = `${n} Kerusakan`;
  document.getElementById("foto-segmen").textContent = s.sumber || "-";
  const hitung = {};
  temuan.forEach((t) => { hitung[t.kelas] = (hitung[t.kelas] || 0) + 1; });
  const rincian = Object.keys(hitung).map((k) => `${hitung[k]}× ${k}`).join(", ");
  document.getElementById("foto-diag-text").textContent = n
    ? `Terdeteksi ${n} kerusakan (${rincian}). Terparah: ${worst}.`
    : "Tidak ada kerusakan pada sesi ini.";
  // Tabel klasifikasi
  document.getElementById("foto-tabel-kerusakan").innerHTML = n
    ? `<table class="jp-table"><thead><tr><th>NO</th><th>KATEGORI</th>` +
      `<th>SEVERITY</th><th>DIMENSI</th><th class="jp-num-right">ESTIMASI</th>` +
      `</tr></thead><tbody>` +
      temuan.map((t, i) =>
        `<tr><td class="jp-num">${String(i + 1).padStart(2, "0")}</td>` +
        `<td><span class="jp-cell-main">${esc(t.kelas)}</span></td>` +
        `<td>${badgeHtml(t.severity)}</td>` +
        `<td class="jp-num">${esc(t.dasar)}</td>` +
        `<td class="jp-num-right">${esc(t.total_str)}</td></tr>`
      ).join("") + `</tbody></table>`
    : '<p class="jp-hint">Tidak ada temuan pada sesi ini.</p>';
  // Estimasi biaya + rekomendasi (bahan dari temuan terparah)
  document.getElementById("foto-est-biaya").textContent = rupiah(s.total_rp || 0);
  document.getElementById("foto-est-note").textContent = `(${n} temuan)`;
  const urut = { Ringan: 0, Sedang: 1, Berat: 2 };
  const parah = [...temuan].sort((a, b) =>
    (urut[b.severity] ?? -1) - (urut[a.severity] ?? -1))[0];
  document.getElementById("foto-rekomendasi").textContent =
    (parah && parah.bahan) || "-";
}

/* === Aksi footer modal foto === */
document.getElementById("foto-back-map").addEventListener("click", () => {
  const dlg = document.getElementById("foto-dialog");
  if (dlg.open) dlg.close();
});
document.getElementById("foto-img").addEventListener("load", function() {
  const el = document.getElementById("foto-res");
  if (el && this.naturalWidth) el.textContent = `RES: ${this.naturalWidth}×${this.naturalHeight}`;
});
document.getElementById("foto-download-jpg").addEventListener("click", async () => {
  const src = document.getElementById("foto-img").src;
  if (!src) return;
  const id = (fotoDetail && fotoDetail.sesi && fotoDetail.sesi.id) || "bukti";
  try {
    const r = await fetch(src);
    if (!r.ok) throw new Error("unduh");
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `foto-bukti-${id}.jpg`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch { /* abaikan */ }
});
document.getElementById("foto-download-pdf").addEventListener("click", async () => {
  if (!fotoDetail) return;
  const s = fotoDetail.sesi || {};
  let image_b64 = null;
  try {
    const g = await fetch(`/api/riwayat/${s.id}/gambar`);
    if (g.ok) {
      const blob = await g.blob();
      image_b64 = await new Promise((resolve) => {
        const fr = new FileReader();
        fr.onload = () => resolve(String(fr.result).split(",")[1]);
        fr.readAsDataURL(blob);
      });
    }
  } catch { /* PDF tetap dibuat tanpa gambar */ }
  const res = await fetch("/api/laporan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rows: fotoDetail.temuan || [], total: s.total_rp || 0, image_b64,
      source: `${s.sumber || "-"} (${s.lokasi || "-"})`, model: s.model || "-",
    }),
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `laporan_jalan_${s.id ?? "peta"}.pdf`;
  a.click();
  URL.revokeObjectURL(a.href);
});

fetch("/api/peta")
  .then((r) => r.json())
  .then((rows) => { semua = rows; gambar(true); })
  .catch(() => {
    document.getElementById("peta-hitung").textContent = "Gagal memuat titik.";
    document.getElementById("peta-kosong").hidden = false;
  });
