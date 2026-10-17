/* Halaman Segmen: daftar + detail SDI-visual per segmen jalan. */
(function() {
  "use strict";

  function esc(s) {
    return String(s === null || s === undefined ? "-" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function badgeKat(kat) {
    var warna = {
      "Baik": "#15803d", "Sedang": "#a16207",
      "Rusak Ringan": "#c2410c", "Rusak Berat": "#b91c1c"
    };
    var c = warna[kat] || "#64748b";
    return '<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
      + 'font-size:12px;font-weight:700;color:#fff;background:' + c + '">'
      + esc(kat || "-") + "</span>";
  }

  function fmtSDI(v) {
    return (v === null || v === undefined) ? "-" : String(v);
  }

  async function muat() {
    const res = await fetch("/api/segmen");
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("kpi-segmen").textContent = data.length;
    // Visual distribusi kategori.
    var hit = { "Baik": 0, "Sedang": 0, "Rusak Ringan": 0, "Rusak Berat": 0 };
    data.forEach(function(g) {
      var k = (g.sdi || {}).kategori;
      if (hit[k] !== undefined) hit[k]++;
    });
    document.getElementById("kat-baik").textContent = hit["Baik"];
    document.getElementById("kat-sedang").textContent = hit["Sedang"];
    document.getElementById("kat-ringan").textContent = hit["Rusak Ringan"];
    document.getElementById("kat-berat").textContent = hit["Rusak Berat"];
    const tb = document.getElementById("tbl-segmen");
    if (!data.length) {
      tb.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--jp-muted)">'
        + "Belum ada segmen. Buat segmen 100 m lalu masukkan sesi foto ke dalamnya.</td></tr>";
      return;
    }
    tb.innerHTML = data.map(function(g) {
      const sdi = g.sdi || {};
      const manual = g.sdi_manual;
      const selisih = (manual === null || manual === undefined)
        ? "-" : Math.abs(Number(manual) - Number(sdi.sdi_total || 0)).toFixed(0);
      return "<tr>" +
        '<td><button type="button" class="jp-link" data-lihat="' + g.id + '">' + esc(g.nama) + "</button></td>" +
        "<td>" + esc(g.jalan) + "</td>" +
        '<td class="jp-num-right">' + esc(g.panjang_m) + " m</td>" +
        '<td class="jp-num-right">' + esc(g.n_sesi) + "</td>" +
        '<td class="jp-num-right" style="font-weight:700">' + fmtSDI(sdi.sdi_total) + "</td>" +
        "<td>" + badgeKat(sdi.kategori) + "</td>" +
        '<td class="jp-num-right">' + fmtSDI(manual) + "</td>" +
        '<td class="jp-num-right">' + esc(selisih) + "</td>" +
        '<td style="white-space:nowrap">' +
          '<button type="button" class="jp-btn-light" data-lihat="' + g.id + '">Detail</button> ' +
          '<button type="button" class="jp-btn-light" data-hapus="' + g.id + '">Hapus</button>' +
        "</td></tr>";
    }).join("");
    tb.querySelectorAll("[data-lihat]").forEach(function(b) {
      b.onclick = function() { bukaDetail(Number(b.getAttribute("data-lihat"))); };
    });
    tb.querySelectorAll("[data-hapus]").forEach(function(b) {
      b.onclick = function() { hapusSegmen(Number(b.getAttribute("data-hapus"))); };
    });
  }

  function barisSDI(label, nilai, ket) {
    return "<tr><td>" + esc(label) + "</td>" +
      '<td class="jp-num-right" style="font-weight:700">' + fmtSDI(nilai) + "</td>" +
      "<td>" + esc(ket || "-") + "</td></tr>";
  }

  /* Bilah skala SDI 0-200 dengan penanda nilai visual & manual. */
  function skalaSDI(total, manual) {
    var pos = function(v) {
      return Math.max(0, Math.min(200, Number(v) || 0)) / 200 * 100;
    };
    var ticks = [0, 50, 100, 150, 200].map(function(t) {
      return '<span class="sdi-tick" style="left:' + (t / 200 * 100) + '%">' + t + "</span>";
    }).join("");
    var marks = "";
    if (total !== null && total !== undefined) {
      marks += '<div class="sdi-mark" style="left:' + pos(total) + '%"><span>'
        + esc(total) + "</span></div>";
    }
    if (manual !== null && manual !== undefined && manual !== "") {
      marks += '<div class="sdi-mark manual" style="left:' + pos(manual) + '%"><span>manual '
        + esc(manual) + "</span></div>";
    }
    return '<div class="sdi-scale">' + ticks + marks + "</div>" +
      '<div class="sdi-legend">' +
      '<span><i style="background:#15803d"></i>Baik &lt;50</span>' +
      "<span><i style=\"background:#a16207\"></i>Sedang 50–100</span>" +
      "<span><i style=\"background:#c2410c\"></i>Rusak Ringan 100–150</span>" +
      "<span><i style=\"background:#b91c1c\"></i>Rusak Berat &gt;150</span></div>";
  }

  async function bukaDetail(id) {
    const res = await fetch("/api/segmen/" + id);
    if (!res.ok) return;
    const g = await res.json();
    const sdi = g.sdi || {};
    const tanpa = sdi.n_tanpa_dimensi
      ? '<p style="font-size:12px;color:var(--jp-muted)">' + sdi.n_tanpa_dimensi
        + " temuan tanpa data dimensi tidak masuk perhitungan.</p>" : "";
    const manual = g.sdi_manual;
    const selisih = (manual === null || manual === undefined) ? "-"
      : "Selisih vs manual: <b>" + Math.abs(Number(manual) - Number(sdi.sdi_total || 0)).toFixed(0) + "</b>";
    const anggota = (g.anggota || []).map(function(s) {
      return "<tr><td>#" + s.id + "</td><td>" + esc(s.waktu) + "</td>" +
        "<td>" + esc(s.lokasi) + "</td>" +
        '<td class="jp-num-right">' + esc(s.n_temuan) + "</td>" +
        '<td><button type="button" class="jp-btn-light" data-keluar="' + s.id + '">Keluarkan</button></td></tr>';
    }).join("") || '<tr><td colspan="5" style="color:var(--jp-muted)">Belum ada sesi anggota.</td></tr>';
    const bebas = (g.tanpa_segmen || []).map(function(s) {
      return "<tr><td>#" + s.id + "</td><td>" + esc(s.waktu) + "</td>" +
        "<td>" + esc(s.lokasi) + "</td>" +
        '<td class="jp-num-right">' + esc(s.n_temuan) + "</td>" +
        '<td><button type="button" class="jp-btn-light" data-masuk="' + s.id + '">Masukkan</button></td></tr>';
    }).join("") || '<tr><td colspan="5" style="color:var(--jp-muted)">Semua sesi sudah ber-segmen.</td></tr>';

    document.getElementById("dg-judul").textContent = "Segmen: " + g.nama;
    document.getElementById("dg-isi").innerHTML =
      '<div class="dg-grid">' +
      "<div>" +
        "<h3 style='font-size:14px;margin:0 0 8px'>SDI-VISUAL</h3>" +
        '<table class="jp-table" style="width:100%"><tbody>' +
        barisSDI("SDI1 - luas retak", sdi.sdi1, sdi.sdi1_ket) +
        barisSDI("SDI2 - lebar retak", sdi.sdi2, sdi.sdi2_ket) +
        barisSDI("SDI3 - jumlah lubang", sdi.sdi3, sdi.sdi3_ket) +
        barisSDI("SDI4 - bekas roda", sdi.sdi4, sdi.sdi4_ket) +
        "</tbody></table>" +
        '<p style="font-size:16px;font-weight:700;margin:10px 0 2px">SDI total: '
          + fmtSDI(sdi.sdi_total) + " " + badgeKat(sdi.kategori) + "</p>" +
        '<p style="font-size:12px;color:var(--jp-muted);margin:0 0 4px">' + selisih + "</p>" + tanpa +
        '<p style="font-size:12px;color:var(--jp-muted)">' + esc(sdi.varian || "") + "</p>" +
        "<h3 style='font-size:14px;margin:14px 0 4px'>Posisi pada skala Bina Marga</h3>" +
        skalaSDI(sdi.sdi_total, manual) +
      "</div>" +
      "<div>" +
        "<h3 style='font-size:14px;margin:0 0 8px'>DATA SEGMEN</h3>" +
        '<div style="display:grid;gap:8px">' +
        '<div><label class="jp-caps">NAMA</label><input id="e-nama" class="jp-input" value="' + esc(g.nama) + '" maxlength="120"></div>' +
        '<div><label class="jp-caps">RUAS</label><input id="e-jalan" class="jp-input" value="' + esc(g.jalan) + '" maxlength="160"></div>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">' +
          '<div><label class="jp-caps">PANJANG (m)</label><input id="e-panjang" class="jp-input" type="number" min="1" step="any" value="' + esc(g.panjang_m) + '"></div>' +
          '<div><label class="jp-caps">LEBAR (m)</label><input id="e-lebar" class="jp-input" type="number" min="1" step="any" value="' + esc(g.lebar_m) + '"></div>' +
        "</div>" +
        '<div><label class="jp-caps">SDI MANUAL (LAPANGAN, OPSIONAL)</label><input id="e-manual" class="jp-input" type="number" min="0" step="any" value="' + (manual === null || manual === undefined ? "" : esc(manual)) + '" placeholder="cth: 25"></div>' +
        '<div><label class="jp-caps">CATATAN</label><input id="e-catatan" class="jp-input" value="' + esc(g.catatan || "") + '" maxlength="500"></div>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
          '<button type="button" class="jp-btn-save" id="e-simpan" style="padding:8px 16px">Simpan Perubahan</button>' +
          '<button type="button" class="jp-btn-light" id="e-pdf" style="padding:8px 16px">Unduh PDF</button>' +
        "</div>" +
        "</div>" +
      "</div>" +
      "</div>" +
      '<h3 style="font-size:14px;margin:16px 0 8px">SESI ANGGOTA (' + (g.anggota || []).length + ")</h3>" +
      '<div style="overflow-x:auto"><table class="jp-table" style="width:100%">' +
      "<thead><tr><th>ID</th><th>Waktu</th><th>Lokasi</th><th>Temuan</th><th></th></tr></thead>" +
      "<tbody>" + anggota + "</tbody></table></div>" +
      '<h3 style="font-size:14px;margin:16px 0 8px">SESI TANPA SEGMEN</h3>' +
      '<div style="overflow-x:auto;max-height:260px;overflow-y:auto"><table class="jp-table" style="width:100%">' +
      "<thead><tr><th>ID</th><th>Waktu</th><th>Lokasi</th><th>Temuan</th><th></th></tr></thead>" +
      "<tbody>" + bebas + "</tbody></table></div>";

    document.getElementById("e-simpan").onclick = async function() {
      const manualVal = document.getElementById("e-manual").value;
      const res2 = await fetch("/api/segmen/" + id, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nama: document.getElementById("e-nama").value,
          jalan: document.getElementById("e-jalan").value,
          panjang_m: document.getElementById("e-panjang").value,
          lebar_m: document.getElementById("e-lebar").value,
          sdi_manual: manualVal === "" ? null : manualVal,
          catatan: document.getElementById("e-catatan").value,
        }),
      });
      if (res2.ok) { bukaDetail(id); muat(); }
    };
    document.getElementById("e-pdf").onclick = function() {
      window.location.href = "/api/segmen/" + id + "/pdf";
    };
    document.querySelectorAll("[data-keluar]").forEach(function(b) {
      b.onclick = async function() {
        const r = await fetch("/api/segmen/" + id + "/anggota/" + b.getAttribute("data-keluar"), { method: "DELETE" });
        if (r.ok) { bukaDetail(id); muat(); }
      };
    });
    document.querySelectorAll("[data-masuk]").forEach(function(b) {
      b.onclick = async function() {
        const r = await fetch("/api/segmen/" + id + "/anggota", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sesi_id: Number(b.getAttribute("data-masuk")) }),
        });
        if (r.ok) { bukaDetail(id); muat(); }
      };
    });
    document.getElementById("dlg-segmen").showModal();
  }

  function hapusSegmen(id) {
    window.jpConfirm("Hapus Segmen", "Hapus segmen ini? Sesi anggotanya tidak ikut terhapus.", { type: "danger" })
      .then(async function(yakin) {
        if (!yakin) return;
        const res = await fetch("/api/segmen/" + id, { method: "DELETE" });
        if (res.ok) muat();
      });
  }

  document.getElementById("btn-buat").onclick = function() {
    document.getElementById("dlg-buat").showModal();
  };
  document.getElementById("b-batal").onclick = function() {
    document.getElementById("dlg-buat").close();
  };
  async function simpanBaru() {
    const nama = document.getElementById("b-nama").value.trim();
    if (!nama) { document.getElementById("b-nama").focus(); return; }
    const res = await fetch("/api/segmen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nama: nama,
        jalan: document.getElementById("b-jalan").value,
        panjang_m: document.getElementById("b-panjang").value,
        lebar_m: document.getElementById("b-lebar").value,
        catatan: document.getElementById("b-catatan").value,
      }),
    });
    if (res.ok) {
      document.getElementById("dlg-buat").close();
      document.getElementById("b-nama").value = "";
      document.getElementById("b-jalan").value = "";
      document.getElementById("b-catatan").value = "";
      document.getElementById("b-panjang").value = "100";
      document.getElementById("b-lebar").value = "6";
      muat();
    }
  }
  document.getElementById("b-simpan").onclick = simpanBaru;
  document.getElementById("dlg-buat").addEventListener("keydown", function(ev) {
    if (ev.key === "Enter" && ev.target.tagName === "INPUT") { ev.preventDefault(); simpanBaru(); }
  });
  document.getElementById("dg-tutup").onclick = function() {
    document.getElementById("dlg-segmen").close();
  };

  muat();
})();
