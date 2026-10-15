/* Helper antarmuka bersama untuk ruang Dinas dan ruang Kontraktor.
 *
 * Isi berkas ini sebelumnya ditulis dua kali, masing-masing dengan empat
 * blok script inline di dashboard/base.html dan kontraktor/base.html.
 * Hampir seluruh barisnya sama persis, sehingga setiap perbaikan harus
 * diulang di dua tempat dan bisa terlewat pada salah satunya.
 *
 * Isi: tempelan token CSRF ke fetch, nomor halaman berpaginasi,
 * helper paginasi, notifikasi toast, dialog konfirmasi, dan menu
 * navigasi untuk layar sempit.
 *
 * Berkas ini dimuat di posisi yang sama dengan blok inline sebelumnya,
 * yaitu setelah isi halaman, supaya menu navigasi tetap menemukan
 * tombolnya di DOM.
 */

(function(){var o=window.fetch;if(!o)return;var M={POST:1,PUT:1,PATCH:1,DELETE:1};function t(){var m=document.querySelector('meta[name="csrf-token"]');return m?m.content:"";}window.fetch=function(i,n){n=n||{};var me=String(n.method||(i&&i.method)||"GET").toUpperCase();var u=(typeof i==="string")?i:((i&&i.url)||"");var so=u.indexOf("http")!==0||u.indexOf(location.origin)===0;if(so&&M[me]){var k=t();if(k){var h=new Headers(n.headers||(i&&i.headers)||{});if(!h.has("X-CSRF-Token"))h.set("X-CSRF-Token",k);n.headers=h;}}return o.call(this,i,n);};})();

/* Laporkan kegagalan request ke konsol.
 *
 * Hampir semua catch lama ditulis `catch(function(){...})` tanpa menerima
 * objek galat, jadi penyebabnya hilang begituRespons tampil ke user. Kalau
 * hanya ada "Kesalahan jaringan.",developer tidak bisa tahu apakah itu
 * 403 CSRF, 500 dari server, atau koneksi putus -- persis seperti bug
 * tombol Terbitkan SPK yang dulu hanya bisa ditebak.
 *
 * `opts.pengguna` diisi kalau kegagalan ini juga perlu terlihat user.
 * Polling tidak boleh mengisinya: toast tiap 30 detik justru jadi gangguan.
 */
window.jpLaporGagal = function(konteks, e, opts) {
  try {
    if (window.console && console.error) {
      console.error("[JalanPantau] " + konteks, e || "(tanpa objek galat)");
    }
  } catch (_) { /* konsol tidak tersedia: jangan gagalkan lagi */ }
  var o = opts || {};
  if (o.pengguna && window.jpToast) {
    window.jpToast("error", o.judul || "Gagal", o.pengguna);
  }
};

/* Versi JP_LaporGagal yang diam-diam diam: batasi satu pesan per jendela.
 *
 * Dipakai polling yang berjalan tiap 30 detik. Kalau server sedang lambat,
 * tanpa pembatas setiap percobaan menambah satu baris ke konsol sampai
 * jadi jauh lebih banyak dari pesan yang berguna.
 */
window.jpLaporGagalSekali = (function() {
  var sudah = {};
  return function(kunci, konteks, e) {
    if (sudah[kunci]) return;
    sudah[kunci] = true;
    window.jpLaporGagal(konteks, e, {});
  };
})();

    // Nomor halaman yang ditampilkan, dengan "..." pada lompatan besar.
  // Dipakai bersama oleh daftar Instansi, Disposisi, dan Beranda Dinas.
  //
  // Kalau semua nomor dirender, jumlah tombol ikut bertambah seiring data
  // bertambah sehingga paginasi jadi lebih lousy dari tabelnya. Sebaliknya
  // elipsis harus dipasang berdasarkan SELISIH antar nomor, bukan tebakan
  // posisi: kalau ditebak, ada nomor yang hilang tanpa penanda sama sekali.
  window.jpNomorHalaman = function(totalHal, aktif) {
    if (totalHal <= 10) {
      var penuh = [];
      for (var a = 1; a <= totalHal; a++) penuh.push(a);
      return penuh;
    }
    var daftar = [1];
    var mulai = Math.max(2, aktif - 1);
    var akhir = Math.min(totalHal - 1, aktif + 1);
    for (var b = mulai; b <= akhir; b++) daftar.push(b);
    daftar.push(totalHal);
    var hasil = [daftar[0]];
    for (var i = 1; i < daftar.length; i++) {
      if (daftar[i] - daftar[i - 1] > 1) hasil.push("...");
      hasil.push(daftar[i]);
    }
    return hasil;
  };

  // Paginasi seragam untuk setiap tabel daftar.
  //
  // Semua baris dirender sekali ke dalam <tbody>, lalu helper ini hanya
  // menyembunyikan baris di luar halaman aktif. Cara ini dipilih supaya
  // setiap tabel cukup menandai barisnya dengan data-jp-row="1" tanpa
  // menulis ulang logika paginasi sendiri. Logika ini sebelumnya ditulis
  // terpisah di beberapa halaman dan akibatnya bug yang sama (tombol
  // halaman salah nomor) muncul di lebih dari satu tempat.
  //
  // Baris tanpa data-jp-row dianggap baris status ("belum ada data") dan
  // TIDAK ikut dipaginasi.
  window.jpPaginasi = function(opsi) {
    var per = opsi.perHalaman || 10;
    var tbody = opsi.tbody;
    // Tanpa tbody tidak ada yang bisa dipaginasi. Rencana semula: banyak
    // halaman memanggil helper ini di dalam IIFE yang sama dengan pemasangan
    // listener tombol, jadi satu TypeError di sini mematikan seluruh skrip
    // halaman -- tombol pun jadi tidak berfungsi tanpa pesan apa pun.
    // Karena itu bail-out dengan objek kosong, bukan melempar.
    if (!tbody) {
      return { segarkan: function() {}, keHalaman: function() {} };
    }
    var bar = opsi.bar || null;
    var info = opsi.info || null;
    var kelasAngka = opsi.kelasAngka || "jp-pag-num";
    var kelasGap = opsi.kelasGap || "inst-pag-gap";
    var label = opsi.label || "baris";
    var hal = 1;

    function dataRows() {
      return Array.prototype.filter.call(tbody.children, function(tr) {
        return tr.dataset.jpRow === "1";
      });
    }

    function gambarBar(totalHal) {
      if (!bar) return;
      if (totalHal <= 1) { bar.style.display = "none"; return; }
      bar.style.display = "flex";
      var html = '<button type="button" class="dash-btn-light jp-pag-prev"'
        + (hal <= 1 ? " disabled" : "") + ">&lsaquo; Sebelumnya</button>";
      window.jpNomorHalaman(totalHal, hal).forEach(function(n) {
        if (n === "...") { html += '<span class="' + kelasGap + '">&hellip;</span>'; return; }
        html += '<button type="button" class="dash-btn-light ' + kelasAngka
          + (n === hal ? " aktif" : "") + '" data-hal="' + n + '">' + n + "</button>";
      });
      html += '<button type="button" class="dash-btn-light jp-pag-next"'
        + (hal >= totalHal ? " disabled" : "") + ">Berikutnya &rsaquo;</button>";
      bar.innerHTML = html;
      // Selalu baca dari data-hal, bukan indeks DOM: elipsis di antaranya
      // membuat indeks tidak lagi sama dengan nomor halaman.
      bar.querySelector(".jp-pag-prev").onclick = function(){ if (hal > 1) { hal--; terapkan(); }};
      bar.querySelector(".jp-pag-next").onclick = function(){ if (hal < totalHal) { hal++; terapkan(); }};
      bar.querySelectorAll("." + kelasAngka).forEach(function(btn) {
        btn.onclick = function(){ hal = Number(btn.dataset.hal); terapkan(); };
      });
    }

    function terapkan() {
      var rows = dataRows();
      var total = rows.length;
      if (!total) {
        rows.forEach(function(tr){ tr.style.display = ""; });
        if (bar) bar.style.display = "none";
        return;
      }
      var totalHal = Math.ceil(total / per);
      // Data bisa berkurang (mis. setelah dihapus) sehingga halaman aktif
      // jatuh di luar jangkauan.
      if (hal > totalHal) hal = totalHal;
      var mulai = (hal - 1) * per;
      var akhir = Math.min(mulai + per, total);
      rows.forEach(function(tr, i) {
        tr.style.display = (i >= mulai && i < akhir) ? "" : "none";
      });
      gambarBar(totalHal);
      if (info) {
        info.textContent = "Menampilkan " + (mulai + 1) + "-" + akhir + " dari "
          + total + " " + label + " (Halaman " + hal + "/" + totalHal + ").";
      }
    }

    return {
      segarkan: terapkan,
      keHalaman: function(h) { hal = h; terapkan(); }
    };
  };

    // Global toast notification
    window.jpToast = function(type, title, message) {
      var container = document.getElementById("toast-container");
      if (!container) return;
      var colors = {success:"#059669", error:"#DC2626", info:"#006194", warning:"#D97706"};
      var icons = {
        success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
        error:   '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        info:    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        warning: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
      };
      var toast = document.createElement("div");
      toast.style.cssText = "pointer-events:auto;padding:12px 16px;border-radius:8px;background:#fff;box-shadow:0 4px 16px rgba(0,0,0,.15);border-left:4px solid " + (colors[type] || colors.info) + ";display:flex;align-items:center;gap:12px;font-size:13px;min-width:280px;max-width:400px;animation:jp-toast-in .3s ease";
      toast.innerHTML = '<span style="font-size:18px;font-weight:700;color:' + (colors[type] || colors.info) + '">' + (icons[type] || icons.info) + '</span>' +
        '<div style="display:flex;flex-direction:column;flex:1"><span style="font-weight:600;color:#0F172A">' + (title || '') + '</span>' + (message ? '<span style="font-size:11px;color:#64748B;margin-top:2px">' + message + '</span>' : '') + '</div>';
      container.appendChild(toast);
      setTimeout(function() {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(20px)";
        toast.style.transition = "all .3s";
        setTimeout(function() { toast.remove(); }, 300);
      }, 4500);
    };

    // Custom confirm modal
    window.jpConfirm = function(title, message, opts) {
      opts = opts || {};
      return new Promise(function(resolve) {
        var existing = document.getElementById("jp-confirm-modal");
        if (existing) existing.remove();
        var overlay = document.createElement("div");
        overlay.id = "jp-confirm-modal";
        overlay.style.cssText = "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5);backdrop-filter:blur(2px);";
        var modal = document.createElement("div");
        modal.style.cssText = "background:#fff;border-radius:12px;padding:24px;max-width:400px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,.2);animation:jp-modal-in .2s ease;";
        var iconColor = opts.type === "danger" ? "#DC2626" : "#006194";
        var icon = opts.type === "danger"
          ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
          : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
        modal.innerHTML =
          '<div style="display:flex;align-items:flex-start;gap:16px">' +
          '<div style="width:40px;height:40px;border-radius:50%;background:' + iconColor + ';color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0">' + icon + '</div>' +
          '<div style="flex:1"><div style="font-size:16px;font-weight:600;color:#0F172A;margin-bottom:4px">' + (title || 'Konfirmasi') + '</div><div style="font-size:13px;color:#64748B">' + (message + '') + '</div></div></div>' +
          '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:20px">' +
          '<button type="button" id="jp-confirm-cancel" style="padding:8px 16px;border:1px solid #E2E8F0;border-radius:8px;background:#fff;color:#64748B;font-size:13px;font-weight:500;cursor:pointer">' + (opts.cancelText || 'Batal') + '</button>' +
          '<button type="button" id="jp-confirm-ok" style="padding:8px 16px;border:none;border-radius:8px;background:' + iconColor + ';color:#fff;font-size:13px;font-weight:500;cursor:pointer">' + (opts.okText || 'Ya, Hapus') + '</button>' +
          '</div>';
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        document.getElementById("jp-confirm-ok").onclick = function() { overlay.remove(); resolve(true); };
        document.getElementById("jp-confirm-cancel").onclick = function() { overlay.remove(); resolve(false); };
        overlay.onclick = function(e) { if (e.target === overlay) { overlay.remove(); resolve(false); } };
      });
    };

    // Pilih penanggung jawab / unit dari daftar kontraktor.
    // Nilai lama di kolom disposisi.penanggung_jawab bisa berupa teks bebas
    // (mis. "Unit TRC") yang tidak ada di daftar kontraktor. Memasang nilai itu
    // langsung ke <select> akan membuat selectedIndex = -1 sehingga isinya
    // hilang begitu tiket disimpan. Karena itu nilai yang tidak cocok disisipkan
    // sebagai opsi bertanda "data lama" supaya tidak ada data yang hilang diam-diam.
    window.jpPilihPenanggungJawab = function(sel, nilai) {
      if (!sel) return;
      var v = String(nilai == null ? "" : nilai).trim();
      // Buang opsi sisa dari pemilihan sebelumnya sebelum memilih yang baru.
      if (sel._jpLama && sel._jpLama.parentNode) sel._jpLama.parentNode.removeChild(sel._jpLama);
      sel._jpLama = null;
      if (!v || v === "-") { sel.selectedIndex = 0; return; }
      for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === v) { sel.selectedIndex = i; return; }
      }
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v + " (data lama)";
      sel.appendChild(opt);
      sel._jpLama = opt;
      sel.selectedIndex = sel.options.length - 1;
    };

  (function(){
    var btn = document.getElementById("nav-toggle");
    var side = document.getElementById("sidebar");
    var scrim = document.getElementById("nav-scrim");
    if (!btn || !side) return;
    function buka(ya){
      side.classList.toggle("dash-sidebar-buka", ya);
      btn.setAttribute("aria-expanded", ya ? "true" : "false");
      btn.setAttribute("aria-label", ya ? "Tutup menu navigasi" : "Buka menu navigasi");
      if (scrim) scrim.hidden = !ya;
    }
    btn.addEventListener("click", function(){ buka(!side.classList.contains("dash-sidebar-buka")); });
    if (scrim) scrim.addEventListener("click", function(){ buka(false); });
    // Pilih menu = tutup overlay, lalu biarkan link navigasi berjalan normal.
    side.addEventListener("click", function(e){
      if (e.target.closest("a") && window.matchMedia("(max-width: 768px)").matches) buka(false);
    });
    document.addEventListener("keydown", function(e){ if (e.key === "Escape") buka(false); });
    // Kembali ke tampilan lebar harus menutup state overlay.
    window.addEventListener("resize", function(){
      if (!window.matchMedia("(max-width: 768px)").matches) buka(false);
    });
  })();
