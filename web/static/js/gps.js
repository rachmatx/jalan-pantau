/* GPS: minta izin sekali saat halaman dibuka, isi otomatis, peringatan bila ditolak. */
window.__gps = { state: ("geolocation" in navigator) ? "pending" : "unsupported" };

function isiOtomatis(lat, lon) {
  const pasang = [["lat-gambar", "lon-gambar"], ["lat-live", "lon-live"]];
  for (const [latId, lonId] of pasang) {
    const elLat = document.getElementById(latId);
    const elLon = document.getElementById(lonId);
    if (elLat && elLat.value.trim() === "") elLat.value = String(lat).replace(".", ",");
    if (elLon && elLon.value.trim() === "") elLon.value = String(lon).replace(".", ",");
  }
}

function peringatanGPS(lat, lon) {
  const ada = lat != null && lon != null && !Number.isNaN(lat) && !Number.isNaN(lon);
  if (ada) return null;
  if (window.__gps.state === "denied")
    return "Izin lokasi ditolak — hasil tersimpan TANPA titik peta. Izinkan lokasi di peramban, lalu simpan ulang bila perlu koordinat.";
  return "Lokasi belum tersedia — hasil tersimpan TANPA titik peta.";
}

if (window.__gps.state === "pending") {
  mintaGPS();
}

function mintaGPS() {
  if (!("geolocation" in navigator)) {
    window.__gps.state = "unsupported";
    return;
  }
  window.__gps.state = "pending";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      window.__gps.state = "ok";
      isiOtomatis(pos.coords.latitude.toFixed(6), pos.coords.longitude.toFixed(6));
    },
    (err) => {
      window.__gps.state = err.code === err.PERMISSION_DENIED ? "denied" : "unavailable";
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
  );
}

const btnGps = document.getElementById("gps-sekarang");
if (btnGps) btnGps.addEventListener("click", mintaGPS);
