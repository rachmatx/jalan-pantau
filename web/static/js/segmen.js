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

  var dataSegmen = [];
  var halamanSegmen = 1;
  var PER_HALAMAN_SEGMEN = 10;

  async function muat() {
    const res = await fetch("/api/segmen");
    if (!res.ok) return;
    const data = await res.json();
    dataSegmen = data;
    halamanSegmen = 1;
    document.getElementById("kpi-segmen").textContent = data.length;
    var hitung = document.getElementById("tabel-hitung");
    if (hitung) hitung.textContent = data.length ? data.length + " segmen" : "";
    // Visual distribusi kategori (seluruh data, bukan cuma halaman aktif).
    var hit = { "Baik": 0, "Sedang": 0, "Rusak Ringan": 0, "Rusak Berat": 0 };
    data.forEach(function(g) {
      var k = (g.sdi || {}).kategori;
      if (hit[k] !== undefined) hit[k]++;
    });
    document.getElementById("kat-baik").textContent = hit["Baik"];
    document.getElementById("kat-sedang").textContent = hit["Sedang"];
    document.getElementById("kat-ringan").textContent = hit["Rusak Ringan"];
    document.getElementById("kat-berat").textContent = hit["Rusak Berat"];
    renderTabelSegmen();
  }

  function barisSegmen(g) {
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
      '<td><div class="jp-rowact">' +
        '<button type="button" data-act="detail" data-lihat="' + g.id + '">Detail</button>' +
        '<button type="button" data-act="hapus" data-hapus="' + g.id + '">Hapus</button>' +
      "</div></td></tr>";
  }

  function renderTabelSegmen() {
    const data = dataSegmen;
    const tb = document.getElementById("tbl-segmen");
    var pag = document.getElementById("segmen-paginasi");
    if (!data.length) {
      tb.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--jp-muted)">'
        + "Belum ada segmen. Buat segmen 100 m lalu masukkan sesi foto ke dalamnya.</td></tr>";
      if (pag) { pag.style.display = "none"; pag.innerHTML = ""; }
      return;
    }
    var totalHal = Math.max(1, Math.ceil(data.length / PER_HALAMAN_SEGMEN));
    if (halamanSegmen > totalHal) halamanSegmen = totalHal;
    if (halamanSegmen < 1) halamanSegmen = 1;
    var start = (halamanSegmen - 1) * PER_HALAMAN_SEGMEN;
    var pageRows = data.slice(start, start + PER_HALAMAN_SEGMEN);
    tb.innerHTML = pageRows.map(barisSegmen).join("");
    tb.querySelectorAll("[data-lihat]").forEach(function(b) {
      b.onclick = function() { bukaDetail(Number(b.getAttribute("data-lihat"))); };
    });
    tb.querySelectorAll("[data-hapus]").forEach(function(b) {
      b.onclick = function() { hapusSegmen(Number(b.getAttribute("data-hapus"))); };
    });
    renderPaginasiSegmen(totalHal, start, pageRows.length);
  }

  function renderPaginasiSegmen(totalHal, start, n) {
    var pag = document.getElementById("segmen-paginasi");
    if (!pag) return;
    if (dataSegmen.length <= PER_HALAMAN_SEGMEN) {
      pag.style.display = "none";
      pag.innerHTML = "";
      return;
    }
    pag.style.display = "flex";
    var html = '<button type="button" id="seg-pag-prev"' + (halamanSegmen <= 1 ? " disabled" : "") + ">\u2039 Sebelumnya</button>";
    for (var i = 1; i <= totalHal; i++) {
      html += '<button type="button" class="pag-num' + (i === halamanSegmen ? " aktif" : "") + '" data-seghal="' + i + '">' + i + "</button>";
    }
    html += '<button type="button" id="seg-pag-next"' + (halamanSegmen >= totalHal ? " disabled" : "") + ">Berikutnya \u203a</button>";
    html += '<span class="jp-hint" style="margin-left:8px">Menampilkan ' + (start + 1) + "\u2013" + (start + n) + " dari " + dataSegmen.length + " segmen (terbaru dulu)</span>";
    pag.innerHTML = html;
    document.getElementById("seg-pag-prev").onclick = function() {
      if (halamanSegmen > 1) { halamanSegmen--; renderTabelSegmen(); }
    };
    document.getElementById("seg-pag-next").onclick = function() {
      if (halamanSegmen < totalHal) { halamanSegmen++; renderTabelSegmen(); }
    };
    var nums = pag.querySelectorAll("[data-seghal]");
    for (var j = 0; j < nums.length; j++) {
      (function(idx) {
        nums[idx].onclick = function() { halamanSegmen = idx + 1; renderTabelSegmen(); };
      })(j);
    }
  }

  function barisSDI(label, nilai, ket) {
    return "<tr><td>" + esc(label) + "</td>" +
      '<td class="jp-num-right" style="font-weight:700">' + fmtSDI(nilai) + "</td>" +
      "<td>" + esc(ket || "-") + "</td></tr>";
  }

  function barisUkur(label, nilai) {
    return "<tr><td>" + esc(label) + "</td>" +
      '<td class="jp-num-right" style="font-weight:700">' + esc(nilai) + "</td></tr>";
  }

  function fmtUkur(v, satuan) {
    return (v === null || v === undefined) ? "-" : (v + (satuan || ""));
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
    const komp = sdi.komp || {};
    const manual = g.sdi_manual;
    const selisih = (manual === null || manual === undefined) ? "-"
      : "Selisih vs manual: <b>" + Math.abs(Number(manual) - Number(sdi.sdi_total || 0)).toFixed(0) + "</b>";
    const anggota = (g.anggota || []).map(function(s) {
      return "<tr><td>#" + s.id + "</td><td>" + esc(s.waktu) + "</td>" +
        "<td>" + esc(s.lokasi) + "</td>" +
        '<td class="jp-num-right">' + esc(s.n_temuan) + "</td>" +
        '<td><div class="jp-rowact"><button type="button" data-act="hapus" data-keluar="' + s.id + '">Keluarkan</button></div></td></tr>';
    }).join("") || '<tr><td colspan="5" style="color:var(--jp-muted)">Belum ada sesi anggota.</td></tr>';
    const bebas = (g.tanpa_segmen || []).map(function(s) {
      return "<tr><td>#" + s.id + "</td><td>" + esc(s.waktu) + "</td>" +
        "<td>" + esc(s.lokasi) + "</td>" +
        '<td class="jp-num-right">' + esc(s.n_temuan) + "</td>" +
        '<td><div class="jp-rowact"><button type="button" data-act="detail" data-masuk="' + s.id + '">Masukkan</button></div></td></tr>';
    }).join("") || '<tr><td colspan="5" style="color:var(--jp-muted)">Semua sesi sudah ber-segmen.</td></tr>';

    document.getElementById("dg-judul").textContent = "Segmen: " + g.nama;
    document.getElementById("dg-sub").textContent = [
      g.jalan,
      (g.panjang_m ? g.panjang_m + " m" : null),
      ((g.anggota || []).length + " sesi anggota"),
    ].filter(Boolean).join(" · ");
    document.getElementById("dg-isi").innerHTML =
      '<div class="jp-sdi-hero">' +
        '<div class="jp-sdi-hero-num"><span>SDI-VISUAL</span><b>' + fmtSDI(sdi.sdi_total) + "</b></div>" +
        '<div class="jp-sdi-hero-meta">' + badgeKat(sdi.kategori) +
          "<p>" + selisih + "</p>" +
          (sdi.n_tanpa_dimensi
            ? "<p>" + sdi.n_tanpa_dimensi + " temuan tanpa data dimensi tidak masuk perhitungan.</p>"
            : "") +
        "</div>" +
      "</div>" +
      '<div class="dg-grid" style="margin-top:16px">' +
        "<div>" +
          "<h3>Komponen SDI</h3>" +
          '<div class="jp-table-scroll"><table class="jp-table" style="width:100%"><tbody>' +
            barisSDI("SDI1 - luas retak", sdi.sdi1, sdi.sdi1_ket) +
            barisSDI("SDI2 - lebar retak", sdi.sdi2, sdi.sdi2_ket) +
            barisSDI("SDI3 - jumlah lubang", sdi.sdi3, sdi.sdi3_ket) +
            barisSDI("SDI4 - bekas roda", sdi.sdi4, sdi.sdi4_ket) +
          "</tbody></table></div>" +
          (sdi.varian ? '<p style="font-size:12px;color:var(--jp-muted);margin:8px 0 0">' + esc(sdi.varian) + "</p>" : "") +
        "</div>" +
        "<div>" +
          "<h3>Data segmen</h3>" +
          '<div style="display:grid;gap:10px">' +
            '<div><label class="jp-caps">NAMA</label><input id="e-nama" class="jp-input" value="' + esc(g.nama) + '" maxlength="120"></div>' +
            '<div><label class="jp-caps">RUAS</label><input id="e-jalan" class="jp-input" value="' + esc(g.jalan) + '" maxlength="160"></div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
              '<div><label class="jp-caps">PANJANG (m)</label><input id="e-panjang" class="jp-input" type="number" min="1" step="any" value="' + esc(g.panjang_m) + '"></div>' +
              '<div><label class="jp-caps">LEBAR (m)</label><input id="e-lebar" class="jp-input" type="number" min="1" step="any" value="' + esc(g.lebar_m) + '"></div>' +
            "</div>" +
            '<div><label class="jp-caps">SDI MANUAL (LAPANGAN, OPSIONAL)</label><input id="e-manual" class="jp-input" type="number" min="0" step="any" value="' + (manual === null || manual === undefined ? "" : esc(manual)) + '" placeholder="cth: 25"></div>' +
            '<div><label class="jp-caps">CATATAN</label><input id="e-catatan" class="jp-input" value="' + esc(g.catatan || "") + '" maxlength="500" placeholder="opsional"></div>' +
          "</div>" +
        "</div>" +
      "</div>" +
      "<h3>Data pengukuran agregat (bahan baku SDI)</h3>" +
      '<div class="jp-table-scroll"><table class="jp-table" style="width:100%"><tbody>' +
        barisUkur("Retak linier", fmtUkur(komp.n_retak_linier, " temuan")) +
        barisUkur("Retak buaya", fmtUkur(komp.n_retak_buaya, " temuan")) +
        barisUkur("Lubang", fmtUkur(komp.n_lubang, " temuan") + " → " + fmtUkur(komp.lubang_per_km, "/km")) +
        barisUkur("Luas retak", fmtUkur(komp.luas_retak_m2, " m²") + " (" + fmtUkur(komp.luas_retak_pct, "%") + " dari luas segmen)") +
        barisUkur("Rata-rata lebar retak", fmtUkur(komp.lebar_retak_mm, " mm")) +
      "</tbody></table></div>" +
      '<p style="font-size:12px;color:var(--jp-muted)">Lima angka inilah yang dimasukkan ke rumus SDI1–SDI4 pada tabel Komponen SDI di atas — mis. 26 lubang pada segmen 800 m → 32,5/km → SDI3 +75.</p>' +
      "<h3>Posisi pada skala Bina Marga</h3>" +
      skalaSDI(sdi.sdi_total, manual) +
      "<h3>Sesi anggota (" + (g.anggota || []).length + ")</h3>" +
      '<div class="jp-table-scroll"><table class="jp-table" style="width:100%">' +
        '<thead><tr><th>ID</th><th>Waktu</th><th>Lokasi</th><th class="jp-num-right">Temuan</th><th style="text-align:right">Aksi</th></tr></thead>' +
        "<tbody>" + anggota + "</tbody></table></div>" +
      "<h3>Sesi tanpa segmen</h3>" +
      '<div class="jp-table-scroll" style="max-height:260px;overflow-y:auto"><table class="jp-table" style="width:100%">' +
        '<thead><tr><th>ID</th><th>Waktu</th><th>Lokasi</th><th class="jp-num-right">Temuan</th><th style="text-align:right">Aksi</th></tr></thead>' +
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
  // Tutup dialog: tombol X/footer bertanda [data-tutup], klik backdrop, atau Esc.
  document.querySelectorAll("[data-tutup]").forEach(function(b) {
    b.addEventListener("click", function() {
      var d = b.closest("dialog");
      if (d) d.close();
    });
  });
  ["dlg-segmen", "dlg-buat"].forEach(function(id) {
    var d = document.getElementById(id);
    if (d) d.addEventListener("click", function(e) { if (e.target === d) d.close(); });
  });

  muat();
})();
