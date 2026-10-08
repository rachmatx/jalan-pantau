/* Peta kerapatan kerusakan (indeks internal) untuk dashboard dinas.
   Data: /api/disposisi (per daerah). CATATAN: ini bukan IKJ resmi Bina Marga;
   ini kerapatan temuan per sel dari laporan JalanPantau. */
(function () {
  var daerah = window.__DAERAH__ || "";
  var STEP = 0.01; // ~1,1 km per sisi (lintang)
  var WARNA = ["#ECFDF5", "#A7F3D0", "#FDE68A", "#FCA5A5", "#DC2626"];
  var URUT_SEV = {Ringan: 1, Sedang: 2, Berat: 3};
  var peta = null;
  var layerSel = [];

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"'`=]/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
              "'": "&#39;", "`": "&#96;", "=": "&#61;"}[c];
    });
  }
  function rupiah(n) { return "Rp" + Number(n || 0).toLocaleString("id-ID"); }
  function set(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }
  function selDari(lat, lon) {
    var la = Math.floor(lat / STEP) * STEP, lo = Math.floor(lon / STEP) * STEP;
    return {lat: la, lon: lo, kunci: la.toFixed(2) + "," + lo.toFixed(2)};
  }
  function kuantil(arr, q) {
    if (!arr.length) return 0;
    var s = arr.slice().sort(function (a, b) { return a - b; });
    var i = Math.min(s.length - 1, Math.floor(q * (s.length - 1)));
    return s[i];
  }
  function kelas(nilai, ambang) {
    for (var i = 0; i < ambang.length; i++) { if (nilai <= ambang[i]) return i; }
    return ambang.length;
  }

  function gambar(rows) {
    var sel = {};
    rows.forEach(function (r) {
      if (r.lat == null || r.lon == null) return;
      var s = selDari(Number(r.lat), Number(r.lon));
      if (!sel[s.kunci]) {
        sel[s.kunci] = {lat: s.lat, lon: s.lon, n: 0, temuan: 0, rp: 0, worst: "-"};
      }
      var item = sel[s.kunci];
      item.n += 1;
      item.temuan += Number(r.n_temuan || 0);
      item.rp += Number(r.total_rp || 0);
      if ((URUT_SEV[r.worst] || 0) > (URUT_SEV[item.worst] || 0)) item.worst = r.worst || "-";
    });
    var daftar = Object.keys(sel).map(function (k) { return sel[k]; });
    daftar.sort(function (a, b) { return b.temuan - a.temuan; });

    var temuan = 0, rp = 0, berat = 0;
    daftar.forEach(function (s) {
      temuan += s.temuan; rp += s.rp;
      if (s.worst === "Berat") berat += 1;
    });
    set("an-sel", daftar.length);
    set("an-temuan", temuan);
    set("an-biaya", rupiah(rp));
    set("an-berat", berat);

    if (typeof L === "undefined") {
      set("an-peta-info", "Peta butuh koneksi internet (tile).");
      return;
    }
    if (!peta) {
      peta = L.map("an-peta").setView([-6.9, 107.6], 11);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                  {maxZoom: 19, attribution: "&copy; OpenStreetMap"}).addTo(peta);
    }
    layerSel.forEach(function (l) { peta.removeLayer(l); });
    layerSel = [];

    if (!daftar.length) {
      set("an-peta-info", "Belum ada titik berkoordinat.");
      return;
    }
    var nilai = daftar.map(function (s) { return s.temuan; });
    var ambang = [kuantil(nilai, 0.2), kuantil(nilai, 0.4), kuantil(nilai, 0.6), kuantil(nilai, 0.8)];
    var titik = [];
    daftar.forEach(function (s) {
      var w = WARNA[kelas(s.temuan, ambang)] || WARNA[WARNA.length - 1];
      var rect = L.rectangle([[s.lat, s.lon], [s.lat + STEP, s.lon + STEP]],
                             {color: "#94A3B8", weight: 1, fillColor: w, fillOpacity: 0.55});
      rect.bindPopup("<b>" + s.n + " laporan &bull; " + s.temuan + " temuan</b><br>" +
                     "Terparah: " + esc(s.worst) + "<br>Estimasi: " + rupiah(s.rp));
      rect.addTo(peta);
      layerSel.push(rect);
      titik.push([s.lat, s.lon]);
      titik.push([s.lat + STEP, s.lon + STEP]);
    });
    peta.fitBounds(titik, {padding: [20, 20], maxZoom: 15});
    set("an-peta-info", daftar.length + " sel kerapatan ditampilkan.");
  }

  fetch("/api/disposisi?daerah=" + encodeURIComponent(daerah) + "&exact=1&limit=200")
    .then(function (r) { return r.json(); })
    .then(function (rows) { gambar(rows || []); })
    .catch(function () { set("an-peta-info", "Gagal memuat data."); });
})();
