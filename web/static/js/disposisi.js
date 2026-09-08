// Disposisi Kirim Laporan - JavaScript
(function(){
  var latestBAP = null;
  var semuaBAP = [];
  var halaman = 1;
  var perHalaman = 10;
  var instansiDaftar = [];

  // P4 XSS: escape sebelum innerHTML (data riwayat/instansi dari server).
  function esc(v) {
    return String(v ?? "").replace(/[&<>"'`=]/g, function(c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
              "'": "&#39;", "`": "&#96;", "=": "&#61;"}[c];
    });
  }
  
  // Toast notification
  window.showToast = function(type, title, message) {
    var container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.style.cssText = "position:fixed;top:80px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px";
      document.body.appendChild(container);
    }
    var colors = {success:"#059669",error:"#DC2626",info:"#2563EB"};
    var icons = {success:"✓",error:"✕",info:"ℹ"};
    var toast = document.createElement("div");
    toast.style.cssText = "pointer-events:auto;padding:12px 16px;border-radius:8px;background:#fff;box-shadow:0 4px 16px rgba(0,0,0,.15);border-left:4px solid " + colors[type] + ";display:flex;align-items:center;gap:12px;font-size:13px;min-width:280px;animation:slideIn .3s ease";
    toast.innerHTML = '<span style="font-size:18px;font-weight:700;color:' + colors[type] + '">' + icons[type] + '</span><div style="display:flex;flex-direction:column;flex:1"><span style="font-weight:600;color:#0F172A">' + esc(title) + '</span>' + (message ? '<span style="font-size:11px;color:#64748B;margin-top:2px">' + esc(message) + '</span>' : '') + '</div>';
    container.appendChild(toast);
    setTimeout(function() { toast.style.opacity = "0"; toast.style.transition = "opacity .3s"; setTimeout(function() { toast.remove(); }, 300); }, 4500);
  };
  
  // Load data BAP dari riwayat
  function loadBAPData() {
    // Skeleton loading: baris placeholder berkedip selama fetch
    var tbodyAwal = document.getElementById("bap-table-body");
    if (tbodyAwal) {
      tbodyAwal.innerHTML = Array(3).fill(
        '<tr><td colspan="6" style="padding:10px"><span class="skel" style="width:100%;height:18px"></span></td></tr>'
      ).join("");
    }
    fetch("/api/riwayat")
      .then(function(r) { return r.json(); })
      .then(function(json) {
        var rows = json.data || json;  // support format baru {data, overflow, total_db} dan lama [array]
        semuaBAP = rows;
        if (!rows.length) {
          document.getElementById("bap-count").textContent = "Tidak ada BAP";
          document.getElementById("bap-table-body").innerHTML = '<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--jp-muted)">Belum ada BAP. Simpan deteksi terlebih dahulu<br><a href="/" style="display:inline-block;margin-top:10px;padding:8px 16px;border-radius:6px;background:var(--jp-primary);color:#fff;font-size:12px;font-weight:600;text-decoration:none">Mulai Deteksi</a></td></tr>';
          return;
        }
        document.getElementById("bap-count").textContent = rows.length + " BAP";
        renderTabelBAP();
        pilihBAP(rows[0].id);
      })
      .catch(function(e) { console.log("Gagal load BAP:", e); });
  }
  
  // Render tabel BAP dengan pagination
  function renderTabelBAP() {
    var totalHal = Math.ceil(semuaBAP.length / perHalaman);
    if (halaman > totalHal) halaman = totalHal;
    if (halaman < 1) halaman = 1;
    
    var mulai = (halaman - 1) * perHalaman;
    var sampai = Math.min(mulai + perHalaman, semuaBAP.length);
    var rows = semuaBAP.slice(mulai, sampai);
    
    var tbody = document.getElementById("bap-table-body");
    tbody.innerHTML = rows.map(function(b) {
      var koordinat = (b.lat && b.lon) ? b.lat.toFixed(4) + ', ' + b.lon.toFixed(4) : '-';
      var waktu = new Date(b.waktu).toLocaleString("id-ID", {day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
      return '<tr data-bap-id="' + b.id + '" style="border-bottom:1px solid var(--jp-line);cursor:pointer" onclick="window.pilihBAP(' + b.id + ')">' +
        '<td style="padding:8px"><input type="radio" name="bap-pilih" value="' + b.id + '" ' + (b.id === (latestBAP ? latestBAP.id : semuaBAP[0].id) ? 'checked' : '') + ' style="accent-color:var(--jp-primary)" onclick="event.stopPropagation(); window.pilihBAP(' + b.id + ')"></td>' +
        '<td style="padding:8px;font-family:var(--jp-mono);font-size:12px;font-weight:600;color:var(--jp-ink)">BA-INS/' + b.id + '/BM-KBDG/II/2025</td>' +
        '<td style="padding:8px;color:var(--jp-tx2);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(b.lokasi || '-') + '</td>' +
        '<td style="padding:8px;text-align:center"><span style="padding:2px 6px;border-radius:4px;background:var(--jp-sev-r-bg);font-size:11px;font-weight:600;color:var(--jp-sev-r-tx)">' + esc(b.n_temuan) + '</span></td>' +
        '<td style="padding:8px;font-size:11px;color:var(--jp-muted)">' + esc(waktu) + '</td>' +
        '<td style="padding:8px;text-align:center;min-width:90px">' +
          '<a href="/disposisi/' + b.id + '" onclick="event.stopPropagation()" style="display:inline-block;padding:6px 12px;border-radius:6px;background:var(--jp-primary);color:#fff;font-size:11px;font-weight:600;text-decoration:none;white-space:nowrap">Lihat Detail</a>' +
        '</td>' +
      '</tr>';
    }).join('');
    
    // Pagination controls
    var pagEl = document.getElementById("bap-pagination");
    if (semuaBAP.length > perHalaman) {
      pagEl.style.display = "flex";
      document.getElementById("bap-page-info").textContent = "Menampilkan " + (mulai+1) + "-" + sampai + " dari " + semuaBAP.length;
      document.getElementById("bap-prev").disabled = (halaman === 1);
      document.getElementById("bap-next").disabled = (halaman === totalHal);
      document.getElementById("bap-prev").onclick = function() { halaman--; renderTabelBAP(); };
      document.getElementById("bap-next").onclick = function() { halaman++; renderTabelBAP(); };
    } else {
      pagEl.style.display = "none";
    }
  }
  
  // Pilih BAP
  window.pilihBAP = function(id) {
    var b = semuaBAP.find(function(x) { return x.id === id; });
    if (!b) return;
    latestBAP = b;
    var radios = document.querySelectorAll('input[name="bap-pilih"]');
    radios.forEach(function(r) { r.checked = (parseInt(r.value) === id); });
    // Rekap dihitung dari temuan asli sesi (tabel temuan), bukan
    // perkiraan proporsional dari n_temuan x worst.
    fetch("/api/riwayat/" + id)
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var per = {pothole: 0, alligator_crack: 0, transverse_crack: 0,
                   longitudinal_crack: 0, lain: 0};
        (d.temuan || []).forEach(function(t) {
          if (t.kelas in per) per[t.kelas]++;
          else per.lain++;
        });
        document.getElementById("rekap-lubang").textContent = per.pothole + " Titik";
        document.getElementById("rekap-retak").textContent = per.alligator_crack + " Area";
        // Slot template hanya ada 3: longitudinal digabung ke sini.
        document.getElementById("rekap-melintang").textContent =
          (per.transverse_crack + per.longitudinal_crack) + " Garis";
        document.getElementById("rekap-biaya").textContent = "Rp " + (b.total_rp / 1000000).toFixed(2) + " Jt";
      })
      .catch(function() {
        document.getElementById("rekap-lubang").textContent = "-";
        document.getElementById("rekap-retak").textContent = "-";
        document.getElementById("rekap-melintang").textContent = "-";
      });
    var gpsLat = b.lat, gpsLon = b.lon;
    if (!gpsLat || !gpsLon) { gpsLat = -6.5956; gpsLon = 106.7916; }
    updateInstansiByAPI(gpsLat, gpsLon);
  };
  
  // Preview BAP
  window.previewBAP = function(id) {
    window.open("/laporan/preview/" + id, "_blank");
  };
  
  // Update instansi via API
  function updateInstansiByAPI(lat, lon) {
    fetch("/api/instansi/terdekat?lat=" + lat + "&lon=" + lon)
      .then(function(r) { return r.json(); })
      .then(function(inst) {
        if (inst && inst.nama) {
          document.getElementById("instansi-nama").textContent = inst.nama;
          document.getElementById("instansi-alamat").textContent = inst.alamat || "-";
          window.instansiId = inst.id;
          window.instansiDaerah = inst.daerah;
          window.instansiEmail = inst.email;
        }
      })
      .catch(function(e) { console.log("Gagal load instansi:", e); });
  }
  
  // Load daftar instansi untuk search
  function loadInstansiDaftar() {
    fetch("/api/instansi")
      .then(function(r) { return r.json(); })
      .then(function(data) { instansiDaftar = data; })
      .catch(function() {});
  }
  
  // Search instansi
  var searchInput = document.getElementById("instansi-search");
  var searchList = document.getElementById("instansi-list");
  if (searchInput) {
    searchInput.addEventListener("input", function() {
      var q = searchInput.value.toLowerCase().trim();
      if (!q) { searchList.style.display = "none"; return; }
      var filtered = instansiDaftar.filter(function(i) {
        return (i.nama && i.nama.toLowerCase().includes(q)) || (i.daerah && i.daerah.toLowerCase().includes(q));
      });
      if (!filtered.length) { searchList.style.display = "none"; return; }
      searchList.style.display = "block";
      searchList.innerHTML = filtered.map(function(i) {
        return '<div style="padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--jp-line)" onclick="window.pilihInstansiLain(' + i.id + ')">' +
          '<div style="font-size:12px;font-weight:600;color:var(--jp-ink)">' + esc(i.nama) + '</div>' +
          '<div style="font-size:11px;color:var(--jp-muted)">' + esc(i.alamat || i.daerah || '') + '</div>' +
        '</div>';
      }).join('');
    });
    searchInput.addEventListener("blur", function() {
      setTimeout(function() { searchList.style.display = "none"; }, 200);
    });
  }
  
  window.pilihInstansiLain = function(id) {
    var inst = instansiDaftar.find(function(i) { return i.id === id; });
    if (!inst) return;
    document.getElementById("instansi-nama").textContent = inst.nama;
    document.getElementById("instansi-alamat").textContent = inst.alamat || "-";
    window.instansiId = inst.id;
    window.instansiDaerah = inst.daerah;
    window.instansiEmail = inst.email;
    searchList.style.display = "none";
    searchInput.value = "";
    showToast("success", "Instansi Dipilih", inst.nama);
  };
  
  loadBAPData();
  loadInstansiDaftar();

  // Preview BAP button
  document.getElementById("btn-preview-bap").addEventListener("click", function() {
    if (latestBAP) window.open("/laporan/preview/" + latestBAP.id, "_blank");
    else alert("Belum ada BAP untuk dipreview.");
  });

  // Tombol Kirim Disposisi
  document.getElementById("btn-kirim-disposisi").addEventListener("click", function() {
    if (!latestBAP) { alert("Belum ada BAP."); return; }
    var btn = this;
    var original = btn.innerHTML;
    btn.disabled = true;
    var nama = document.getElementById("instansi-nama").textContent;
    btn.innerHTML = '<span style="width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:jp-spin .8s linear infinite"></span><span>Mentransmisikan ke ' + esc(nama) + '...</span>';
    
    var urgensiEl = document.querySelector('input[name="urgensi"]:checked');
    var data = {
      bap_id: latestBAP.id,
      bap_nomor: "BA-INS/" + latestBAP.id + "/BM-KBDG/II/2025",
      lokasi: latestBAP.lokasi,
      lat: latestBAP.lat,
      lon: latestBAP.lon,
      n_temuan: latestBAP.n_temuan,
      total_rp: latestBAP.total_rp,
      worst: latestBAP.worst,
      instansi_id: window.instansiId || null,
      instansi_nama: nama,
      instansi_daerah: window.instansiDaerah || "-",
      instansi_email: window.instansiEmail || "-",
      urgensi: urgensiEl ? urgensiEl.value : "Rutin",
      catatan: document.getElementById("catatan-disposisi").value
    };
    
    fetch("/api/disposisi", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data)
    })
    .then(function(r) { return r.json(); })
    .then(function(j) {
      btn.innerHTML = original;
      btn.disabled = false;
      if (j.ok) {
        showToast("success", "Disposisi Berhasil Dikirimkan", "ID: " + j.id + " Ke: " + nama + " • SLA 24 Jam");
      } else {
        alert("Gagal: " + (j.error || "Unknown error"));
      }
    })
    .catch(function(e) {
      btn.innerHTML = original;
      btn.disabled = false;
      alert("Gagal mengirim: " + e.message);
    });
  });
})();
