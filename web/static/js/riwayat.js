/* Riwayat civic: KPI agregat + filter -> tabel aksi -> modal audit -> PDF/CSV/hapus + pagination. */
const daftar = document.getElementById("daftar");
const detail = document.getElementById("detail");
let aktif = null;
let barisTerakhir = [];
let halaman = 1;
const PER_HALAMAN = 10;

// Pagination state untuk tabel temuan di modal detail
let halamanTemuan = 1;
const PER_HALAMAN_TEMUAN = 10;

function badge(sev) {
  const map = { ringan: "RINGAN", sedang: "SEDANG", berat: "BERAT" };
  const k = String(sev).toLowerCase();
  return `<span class="badge badge-${k}"><span class="badge-dot"></span>${esc(map[k] || sev)}</span>`;
}
// P0 XSS: semua string dari server/user harus lewat esc() sebelum innerHTML.
function esc(v) {
  return String(v ?? "").replace(/[&<>"'`=]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
    "'": "&#39;", "`": "&#96;", "=": "&#61;",
  }[c]));
}
function rupiah(n) {
  return "Rp" + Number(n).toLocaleString("id-ID");
}
function tanggal(iso) {
  return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}
function koordinat(s) {
  if (s.lat == null || s.lon == null) return "-";
  const f = (v) => String(Number(v).toFixed(6)).replace(".", ",");
  return `${f(s.lat)}, ${f(s.lon)}`;
}

function perbaruiKpi(rows, total_db) {
  let temuan = 0, rupiahTot = 0;
  const sev = { Ringan: 0, Sedang: 0, Berat: 0 };
  for (const r of rows) {
    temuan += Number(r.n_temuan) || 0;
    rupiahTot += Number(r.total_rp) || 0;
    if (sev[r.worst] !== undefined) sev[r.worst] += 1;
  }
  document.getElementById("kpi-sesi").textContent = total_db ?? rows.length;
  document.getElementById("kpi-temuan").textContent = temuan;
  document.getElementById("kpi-berat").textContent = sev.Berat;
  document.getElementById("kpi-sedang").textContent = sev.Sedang;
  document.getElementById("kpi-rupiah").textContent = rupiah(rupiahTot);
}

function renderPaginasi(total) {
  var totalHal = Math.ceil(total / PER_HALAMAN);
  var pagEl = document.getElementById("riwayat-paginasi");
  if (!pagEl) return;
  if (totalHal <= 1) { pagEl.style.display = "none"; return; }
  pagEl.style.display = "flex";
  var html = '<button type="button" id="pag-prev"' + (halaman <= 1 ? " disabled" : "") + ">‹ Sebelumnya</button>";
  for (var i = 1; i <= totalHal; i++) {
    html += '<button type="button" class="pag-num' + (i === halaman ? " aktif" : "") + '" data-hal="' + i + '">' + i + "</button>";
  }
  html += '<button type="button" id="pag-next"' + (halaman >= totalHal ? " disabled" : "") + ">Berikutnya ›</button>";
  pagEl.innerHTML = html;
  var btnPrev = document.getElementById("pag-prev");
  var btnNext = document.getElementById("pag-next");
  if (btnPrev) btnPrev.onclick = function() { if (halaman > 1) { halaman--; renderTabel(); }};
  if (btnNext) btnNext.onclick = function() { if (halaman < totalHal) { halaman++; renderTabel(); }};
  var nums = document.querySelectorAll(".pag-num");
  for (var j = 0; j < nums.length; j++) {
    (function(idx) {
      nums[j].onclick = function() { halaman = idx + 1; renderTabel(); };
    })(j);
  }
}

function renderTabel() {
  var rows = barisTerakhir;
  if (!rows.length) {
    daftar.innerHTML = '<div class="jp-empty">' +
      '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--jp-muted)" stroke-width="1.5" style="margin-bottom:8px"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>' +
      '<strong>Belum ada riwayat inspeksi</strong>' +
      '<p>Mulai deteksi kerusakan jalan, lalu simpan hasilnya ke riwayat.</p>' +
      '<a href="/" class="jp-btn-primary-sm" style="margin-top:8px">Mulai Deteksi</a>' +
    '</div>';
    document.getElementById("f-info").textContent = "Tidak ada catatan inspeksi.";
    renderPaginasi(0);
    return;
  }
  var start = (halaman - 1) * PER_HALAMAN;
  var end = start + PER_HALAMAN;
  var pageRows = rows.slice(start, end);
  var tbody = pageRows.map(function(r) {
    return '<tr><td><a href="#" data-act="detail" data-id="' + r.id + '" class="jp-idlink">#' + r.id + '</a>' +
      '<span class="jp-cell-sub">' + esc(tanggal(r.waktu)) + '</span></td>' +
      '<td>' + esc(r.sumber) + '</td>' +
      '<td><span class="jp-cell-main">' + esc(r.lokasi) + '</span><span class="jp-cell-sub">' + esc(koordinat(r)) + '</span></td>' +
      '<td>' + badge(r.worst) + '</td><td class="jp-num">' + esc(r.n_temuan) + '</td>' +
      '<td class="jp-num-right">' + esc(rupiah(r.total_rp)) + '</td>' +
      '<td><span class="jp-rowact">' +
      '<button type="button" data-act="detail" data-id="' + r.id + '" title="Lihat detail">Detail</button>' +
      '<button type="button" data-act="pdf" data-id="' + r.id + '" title="Unduh PDF">PDF</button>' +
      '<button type="button" data-act="hapus" data-id="' + r.id + '" title="Hapus">Hapus</button>' +
      '</span></td></tr>';
  }).join("");
  var thead = '<tr><th>WAKTU &amp; ID</th><th>SUMBER</th><th>LOKASI &amp; GEOTAG</th><th>SEVERITY</th><th>TEMUAN</th><th class="jp-num-right">TOTAL</th><th>AKSI</th></tr>';
  daftar.innerHTML = '<table class="jp-table"><thead>' + thead + '</thead><tbody>' + tbody + '</tbody></table>';
  var btns = daftar.querySelectorAll("[data-act]");
  for (var i = 0; i < btns.length; i++) {
    (function(b) {
      b.onclick = function(e) {
        e.preventDefault();
        var id = Number(b.dataset.id), act = b.dataset.act;
        if (act === "detail") bukaDetail(id);
        else if (act === "pdf") unduhPdfId(id);
        else if (act === "hapus") hapusId(id);
      };
    })(btns[i]);
  }
  document.getElementById("f-info").textContent =
    "Menampilkan " + (start + 1) + "-" + Math.min(end, rows.length) + " dari " + rows.length + " catatan (Halaman " + halaman + "/" + (Math.ceil(rows.length / PER_HALAMAN) || 1) + ").";
  renderPaginasi(rows.length);
}

async function muat() {
  // Skeleton loading saat fetch
  var daftarEl = document.getElementById("daftar");
  daftarEl.innerHTML = Array(5).fill(
    '<tr><td colspan="7" style="padding:12px"><span class="skel" style="width:100%;height:18px"></span></td></tr>'
  ).join("").replace(/tr>/g, "div>").replace(/td/g, "div");
  // Tampilkan sebagai skeleton cards
  daftarEl.innerHTML = '<div style="display:flex;flex-direction:column;gap:8px">' +
    Array(5).fill('<div style="height:60px;border-radius:8px;background:linear-gradient(90deg,var(--jp-container) 25%,var(--jp-container-low) 50%,var(--jp-container) 75%);background-size:200% 100%;animation:jp-skeleton 1.5s infinite"></div>').join("") +
  '</div>';

  var q = new URLSearchParams({
    dari: document.getElementById("f-dari").value,
    sampai: document.getElementById("f-sampai").value,
    severity: document.getElementById("f-sev").value,
    q: document.getElementById("f-q").value.trim(),
  });
  var res = await fetch("/api/riwayat?" + q);
  var json = await res.json();
  var rows = json.data || [];
  barisTerakhir = rows;
  halaman = 1;
  perbaruiKpi(rows, json.total_db);
  renderTabel();
  tampilkanPeringatanOverflow(json.overflow, json.total_db, rows.length);
}

function tampilkanPeringatanOverflow(overflow, totalDB, jumlahTampil) {
  var infoEl = document.getElementById("f-info");
  if (!infoEl) return;
  if (overflow) {
    infoEl.innerHTML = '<span style="color:var(--jp-sev-h-tx);font-weight:600">⚠ Menampilkan ' + jumlahTampil + ' dari ' + totalDB + ' catatan.</span> Gunakan filter tanggal/severity untuk mempersempit, atau ekspor CSV untuk data lengkap.';
    infoEl.style.background = 'rgba(220,100,0,.08)';
    infoEl.style.padding = '8px 12px';
    infoEl.style.borderRadius = '6px';
  } else {
    infoEl.style.background = '';
    infoEl.style.padding = '';
  }
}

// Render tabel temuan di modal detail dengan pagination
function renderTabelTemuan() {
  var temuan = aktif.temuan || [];
  var tabelEl = document.getElementById("d-tabel");
  var pagEl = document.getElementById("d-paginasi");
  var infoEl = document.getElementById("d-page-info");

  if (!temuan.length) {
    tabelEl.innerHTML = '<p class="jp-hint">Tidak ada temuan.</p>';
    pagEl.style.display = "none";
    infoEl.textContent = "";
    return;
  }

  var start = (halamanTemuan - 1) * PER_HALAMAN_TEMUAN;
  var end = Math.min(start + PER_HALAMAN_TEMUAN, temuan.length);
  var pageRows = temuan.slice(start, end);

  tabelEl.innerHTML =
    `<table class="jp-table"><thead><tr><th>NO</th><th>KATEGORI KERUSAKAN</th>` +
    `<th>TINGKAT KEPARAHAN</th><th>DIMENSI</th><th>REKOMENDASI</th><th class="jp-num-right">ESTIMASI</th></tr></thead><tbody>` +
    pageRows.map((r) =>
      `<tr><td class="jp-num">${esc(String(r.idx).padStart(2, "0"))}</td>` +
      `<td><span class="jp-cell-main">${esc(r.kelas)}</span><span class="jp-cell-sub">Kode: -</span></td>` +
      `<td>${badge(r.severity)}</td><td class="jp-num">${esc(r.dasar)}</td>` +
      `<td style="font-size:12px;color:var(--jp-tx2)">-</td>` +
      `<td class="jp-num-right">${esc(r.total_str)}</td></tr>`
    ).join("") + `</tbody></table>`;

  // Render pagination
  var totalHal = Math.ceil(temuan.length / PER_HALAMAN_TEMUAN);
  if (totalHal <= 1) {
    pagEl.style.display = "none";
    infoEl.textContent = "";
  } else {
    pagEl.style.display = "flex";
    var html = '<button type="button" class="jp-btn-light" id="d-pag-prev"' + (halamanTemuan <= 1 ? " disabled" : "") + ">‹ Sebelumnya</button>";
    for (var i = 1; i <= totalHal; i++) {
      html += '<button type="button" class="jp-btn-light d-pag-num' + (i === halamanTemuan ? " aktif" : "") + '" data-hal="' + i + '">' + i + "</button>";
    }
    html += '<button type="button" class="jp-btn-light" id="d-pag-next"' + (halamanTemuan >= totalHal ? " disabled" : "") + ">Berikutnya ›</button>";
    pagEl.innerHTML = html;
    document.getElementById("d-pag-prev").onclick = function() { if (halamanTemuan > 1) { halamanTemuan--; renderTabelTemuan(); }};
    document.getElementById("d-pag-next").onclick = function() { if (halamanTemuan < totalHal) { halamanTemuan++; renderTabelTemuan(); }};
    var nums = document.querySelectorAll(".d-pag-num");
    for (var j = 0; j < nums.length; j++) {
      (function(idx) { nums[j].onclick = function() { halamanTemuan = idx + 1; renderTabelTemuan(); }; })(j);
    }
    infoEl.textContent = "Menampilkan " + (start + 1) + "-" + end + " dari " + temuan.length + " temuan (Halaman " + halamanTemuan + "/" + totalHal + ").";
  }
}

async function bukaDetail(id) {
  const res = await fetch(`/api/riwayat/${id}`);
  if (!res.ok) return;
  aktif = await res.json();
  const s = aktif.sesi;
  document.getElementById("d-judul").textContent = `Detail Inspeksi #${s.id} — ${s.lokasi}`;
  document.getElementById("d-subjudul").innerHTML =
    `<span>Sektor ${esc(s.lokasi || '-')}</span><span style="color:var(--jp-outline)">•</span>` +
    `<span>Klasifikasi Jalan: -</span><span style="color:var(--jp-outline)">•</span>` +
    `<span>Konstruksi: -</span>`;
  document.getElementById("d-nomor").textContent = `BA #${s.id}`;
  document.getElementById("d-hash").textContent = (s.model || "-").slice(0, 12) + "...";
  document.getElementById("d-meta").innerHTML =
    `<div><span>WAKTU AUDIT</span><b>${esc(tanggal(s.waktu))}</b></div>` +
    `<div><span>SUMBER</span><b>${esc(s.sumber)}</b></div>` +
    `<div><span>KOORDINAT</span><b class="mono">${esc(koordinat(s))}</b></div>` +
    `<div><span>SEVERITY TERPARAH</span><b>${badge(s.worst)}</b></div>`;
  document.getElementById("d-frame").textContent = `Frame #${s.id} / Sesi`;
  // Lazy load gambar: tampilkan spinner dulu, load gambar setelah modal terbuka
  var fotoEl = document.getElementById("d-foto");
  if (aktif.ada_gambar) {
    fotoEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;gap:10px;padding:40px;color:var(--jp-muted)"><span class="jp-spinner" style="width:20px;height:20px;border-width:2px"></span><span>Memuat gambar...</span></div>';
    var img = new Image();
    img.onload = function() {
      fotoEl.innerHTML = '';
      img.style.cssText = "display:block;width:100%;max-height:380px;object-fit:contain;background:#020617;border-radius:8px";
      img.alt = "Bukti " + esc(s.sumber);
      fotoEl.appendChild(img);
    };
    img.onerror = function() {
      fotoEl.innerHTML = '<div style="padding:40px;text-align:center;color:var(--jp-muted)">Gagal memuat gambar.</div>';
    };
    // Load gambar setelah 50ms agar modal sempat render dulu
    setTimeout(function() { img.src = "/api/riwayat/" + id + "/gambar"; }, 50);
  } else {
    fotoEl.innerHTML = '<div style="aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;color:#64748B;font-family:var(--jp-mono);font-size:11px">Foto bukti tidak tersedia</div>';
  }
  // Reset halaman temuan ke 1 saat buka detail
  halamanTemuan = 1;
  renderTabelTemuan();
  var dTotal = document.getElementById("d-total");
  if (dTotal) dTotal.textContent = rupiah(s.total_rp);
  var dTtd = document.getElementById("d-ttd");
  if (dTtd) dTtd.innerHTML =
    `<div style="display:flex;flex-direction:column;align-items:center;gap:8px"><div style="font-size:11px;font-weight:600;letter-spacing:.05em;color:var(--jp-muted)">PETUGAS SURVEYOR</div><div style="height:40px"></div><div style="font-size:13px;font-weight:700;color:var(--jp-ink)">Operator JalanPantau</div></div>` +
    `<div style="display:flex;flex-direction:column;align-items:center;gap:8px"><div style="font-size:11px;font-weight:600;letter-spacing:.05em;color:var(--jp-muted)">PEJABAT PEMBUAT KOMITMEN</div><div style="height:40px"></div><div style="font-size:13px;font-weight:700;color:var(--jp-ink)">-</div></div>` +
    `<div style="display:flex;flex-direction:column;align-items:center;gap:8px"><div style="font-size:11px;font-weight:600;letter-spacing:.05em;color:var(--jp-muted)">MENGETAHUI</div><div style="height:40px"></div><div style="font-size:13px;font-weight:700;color:var(--jp-ink)">Kepala Seksi Preservasi</div></div>`;
  const st = document.getElementById("d-status");
  if (st) st.hidden = false;
  detail.showModal();
}

async function unduhPdfId(id) {
  const res = await fetch(`/api/riwayat/${id}`);
  if (!res.ok) return;
  await unduhPdf(await res.json());
}

async function unduhPdf(data) {
  const s = data.sesi;
  let image_b64 = null;
  if (data.ada_gambar) {
    const g = await fetch(`/api/riwayat/${s.id}/gambar`);
    if (g.ok) {
      const blob = await g.blob();
      image_b64 = await new Promise((resolve) => {
        const fr = new FileReader();
        fr.onload = () => resolve(String(fr.result).split(",")[1]);
        fr.readAsDataURL(blob);
      });
    }
  }
  const res = await fetch("/api/laporan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rows: data.temuan, total: s.total_rp, image_b64,
      source: `${s.sumber} (${s.lokasi})`, model: s.model,
    }),
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `laporan_jalan_${s.id}.pdf`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function hapusId(id) {
  // Custom confirm modal untuk aksi destruktif
  window.jpConfirm("Hapus Riwayat", "Apakah Anda yakin ingin menghapus riwayat #" + id + "? Tindakan ini tidak bisa dibatalkan.", {type:"danger"}).then(function(yakin){
    if (!yakin) return;
    fetch(`/api/riwayat/${id}`, { method: "DELETE" })
      .then(function(r){ return r.json().then(function(j){ return {ok: r.ok, j: j, status: r.status}; }); })
      .then(function(res){
        if (!res.ok) {
          if (res.status === 401) {
            window.jpToast("error", "Login Diperlukan", "Silakan login sebagai admin dinas untuk menghapus riwayat.");
          } else {
            window.jpToast("error", "Gagal Menghapus", "Tidak dapat menghapus riwayat.");
          }
          return;
        }
        if (aktif && aktif.sesi.id === id && detail.open) detail.close();
        aktif = null;
        muat();
        window.jpToast("success", "Berhasil", "Riwayat #" + id + " telah dihapus.");
      })
      .catch(function(){ window.jpToast("error", "Gagal", "Gagal menghapus riwayat."); });
  });
}

function eksporCsv() {
  const head = "id;waktu;sumber;lokasi;lat;lon;worst;n_temuan;total_rp\n";
  const isi = barisTerakhir.map((r) =>
    [r.id, r.waktu, r.sumber, r.lokasi, r.lat ?? "", r.lon ?? "",
     r.worst, r.n_temuan, r.total_rp].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(";")
  ).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([head + isi], { type: "text/csv" }));
  a.download = "riwayat_jalanpantau.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

document.getElementById("filter").addEventListener("submit", (e) => {
  e.preventDefault();
  if (detail.open) detail.close();
  muat();
});
document.getElementById("f-reset").addEventListener("click", () => {
  document.getElementById("f-dari").value = "";
  document.getElementById("f-sampai").value = "";
  document.getElementById("f-sev").value = "";
  document.getElementById("f-q").value = "";
  muat();
});
document.getElementById("btn-export-csv").addEventListener("click", eksporCsv);
document.getElementById("btn-cetak").addEventListener("click", () => window.print());
document.getElementById("d-pdf").addEventListener("click", async () => {
  if (aktif) await unduhPdf(aktif);
});
document.getElementById("d-hapus").addEventListener("click", async () => {
  if (aktif) await hapusId(aktif.sesi.id);
});
document.getElementById("d-tutup").addEventListener("click", () => {
  if (detail.open) detail.close();
});
document.getElementById("d-x").addEventListener("click", () => {
  if (detail.open) detail.close();
});

muat();
