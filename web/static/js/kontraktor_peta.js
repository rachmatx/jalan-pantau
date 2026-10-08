/* Peta titik pekerjaan di dalam satu SPK (dashboard kontraktor).
 *
 * Berbeda dari peta.js yang menampilkan SELURUH riwayat jalan, modul ini
 * hanya memuat titik milik satu SPK dan mewarnainya berdasarkan status
 * pengerjaan (Menunggu / Dikerjakan / Selesai) supaya kontraktor langsung
 * tahu mana yang belum dikerjakan.
 *
 * Data titik dikirim sebagai argumen dari template (di-render server), bukan
 * fetch, supaya halaman tetap tampil utuh walau JS gagal dimuat.
 */
(function (global) {
  "use strict";

  var PUSAT = [-6.9175, 107.6191]; // Bandung; dipakai bila semua titik tanpa koordinat
  var ZOOM_DEFAULT = 13;

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"'`=]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
               "'": "&#39;", "`": "&#96;", "=": "&#61;" }[c];
    });
  }

  function rupiah(n) {
    return "Rp" + Number(n || 0).toLocaleString("id-ID");
  }

  function kelasUrgensi(u) {
    var k = String(u || "").toLowerCase();
    return k === "kritis" ? "kritis" : k === "tinggi" ? "tinggi" : "rutin";
  }

  function ikon(status) {
    var k = String(status || "Menunggu").toLowerCase();
    return L.divIcon({
      className: "",
      html: '<div class="spk-titik spk-titik-' + esc(k) + '"></div>',
      iconSize: [18, 18],
      iconAnchor: [9, 9],
      popupAnchor: [0, -10],
    });
  }

  function gagal(el, pesan) {
    el.innerHTML = '<div class="dash-empty">' + esc(pesan) + "</div>";
  }

  // Kegagalan peta harus selalu terlihat. Versi lama memakai `return null`
  // diam-diam sehingga ReferenceError (atau error lain) hanya meninggalkan
  // kotak kosong tanpa penjelasan apa pun.
  function buatPeta(elId, titik, opsi) {
    opsi = opsi || {};
    var el = document.getElementById(elId);
    if (!el) return null;
    if (typeof L === "undefined") {
      gagal(el, "Peta membutuhkan koneksi internet.");
      return null;
    }
    try {
      return susun(elId, titik, opsi);
    } catch (e) {
      gagal(el, "Peta gagal dimuat.");
      if (global.console && global.console.error) global.console.error("SPKPeta:", e);
      return null;
    }
  }

  function susun(elId, titik, opsi) {
    var map = L.map(elId, { zoomControl: false, scrollWheelZoom: true })
                .setView(opsi.pusat || PUSAT, ZOOM_DEFAULT);
    L.control.zoom({ position: "bottomleft" }).addTo(map);

    var osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap",
    }).addTo(map);
    var satelit = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Esri WorldImagery" });

    var lapis = L.layerGroup().addTo(map);
    var perTugas = {};
    var batas = [];

    function gambar() {
      lapis.clearLayers();
      perTugas = {};
      batas = [];
      (titik || []).forEach(function (t) {
        if (t.lat == null || t.lon == null) return;
        var m = L.marker([t.lat, t.lon], { icon: ikon(t.status) }).addTo(lapis);
        perTugas[t.id] = m;
        // Foto bukti disimpan per titik dan disimpan di dalam SPK tertentu, jadi
        // URL-nya harus memakai spk_id milik titik itu. Mengarang satu URL
        // global akan salah mengarahkan foto ke SPK lain.
        var foto = "";
        if (t.punya_foto && opsi.urlFoto && t.spk_id) {
          foto = '<br><a target="_blank" rel="noopener" href="' +
            esc(opsi.urlFoto) + t.spk_id + "/tugas/" + t.id + '">' +
            "Lihat foto bukti</a>";
        } else if (t.punya_foto) {
          foto = '<br><span style="color:#64748B">' +
            "Foto bukti tersedia di detail SPK</span>";
        } else {
          foto = '<br><span style="color:#64748B">Belum ada foto bukti</span>';
        }

        // Tautan ke SPK asal titik. Hanya dibuat bila titik tahu SPK-nya,
        // supaya halaman peta utama tidak membuat tautan ke URL kontraktor.
        var asal = "";
        if (t.spk_id && opsi.urlSpk) {
          asal = '<br><a href="' + esc(opsi.urlSpk) + t.spk_id + '">' +
            esc(t.spk_nomor || "Buka SPK") + '</a>';
        }

        m.bindPopup(
          '<div style="font-size:12px;line-height:1.55">' +
          '<strong>' + esc(t.lokasi || "-") + '</strong><br>' +
          '<span class="dash-tiket">' + esc(t.bap_nomor || "-") + '</span><br>' +
          '<span class="urgency urgency-' + kelasUrgensi(t.urgensi) + '">' +
          esc(t.urgensi || "-") + '</span> &middot; ' +
          esc(t.status || "Menunggu") + '<br>' +
          Number(t.n_temuan || 0) + ' temuan &middot; ' + rupiah(t.total_rp) +
          foto + asal + '</div>');
        batas.push([t.lat, t.lon]);
      });

      if (batas.length > 1) map.fitBounds(batas, { padding: [36, 36], maxZoom: 16 });
      else if (batas.length === 1) map.setView(batas[0], Math.max(map.getZoom(), 15));
      setTimeout(function () { map.invalidateSize(); }, 120);
    }

    gambar();

    return {
      peta: map,
      sesuaikan: function () {
        if (batas.length > 1) map.fitBounds(batas, { padding: [36, 36], maxZoom: 16 });
        else if (batas.length === 1) map.setView(batas[0], Math.max(map.getZoom(), 15));
        setTimeout(function () { map.invalidateSize(); }, 60);
      },
      fokus: function (tugasId) {
        var m = perTugas[tugasId];
        if (!m) return;
        map.setView(m.getLatLng(), Math.max(map.getZoom(), 16));
        m.openPopup();
      },
      satelit: function (nyala) {
        if (nyala) { map.removeLayer(osm); satelit.addTo(map); }
        else { map.removeLayer(satelit); osm.addTo(map); }
      },
      jumlahTitik: function () { return batas.length; },
    };
  }

  global.SPKPeta = { buatPeta: buatPeta, esc: esc, rupiah: rupiah };
})(window);