{/* Mode Kamera (panel Gambar Statis): getUserMedia -> jepret via canvas ->
   File JPEG -> terimaBerkas() yang sama dengan pilih file / drag & drop.
   Penanda versi: KAMERA v1 (31 Okt 2026).

   Satu API untuk dua dunia (permintaan user: harus jalan di mobile DAN
   desktop):
   - Mobile: constraint facingMode "environment" = kamera belakang HP;
     tombol ganti muncul bila perangkat punya >1 kamera.
   - Desktop: webcam tidak punya facingMode "environment", jadi rantai
     constraint turun bertahap sampai video:true — webcam USB/bawaan
     laptop tetap kebuka. Label chip dibaca dari track yang BENAR-BENAR
     jalan (getSettings), bukan dari yang diminta.
   getUserMedia hanya tersedia di konteks aman (HTTPS / localhost) —
   app.rachmatx.me sudah HTTPS. Stream WAJIB dimatikan saat mode ditutup,
   pindah tab, atau halaman ditinggalkan, supaya lampu kamera tidak
   menggantung dan kamera tidak terkunci aplikasi lain. */}
(function () {
  "use strict";
  const btnMode = document.getElementById("btn-mode-kamera");
  const btnModeTeks = document.getElementById("btn-mode-kamera-teks");
  const lapis = document.getElementById("lapis-kamera");
  const video = document.getElementById("video-kamera");
  const fotoImg = document.getElementById("foto-kamera");
  const chip = document.getElementById("chip-kamera");
  const chipInfo = document.getElementById("chip-kamera-info");
  const petunjuk = document.getElementById("petunjuk-kamera");
  const kontrolLive = document.getElementById("kontrol-kamera-live");
  const kontrolFoto = document.getElementById("kontrol-kamera-foto");
  const btnJepret = document.getElementById("btn-jepret");
  const btnGanti = document.getElementById("btn-ganti-kamera");
  const btnUlang = document.getElementById("btn-foto-ulang");
  const btnPakai = document.getElementById("btn-foto-pakai");
  const galatBox = document.getElementById("galat-kamera");
  const statusEl = document.getElementById("status");
  const inputGambar = document.getElementById("gambar");
  if (!btnMode || !lapis || !video) return;

  let stream = null;            // MediaStream yang sedang jalan
  let berkasJepret = null;      // File hasil jepretan terakhir
  let urlFoto = null;           // object URL pratinjau jepretan
  let menghadapDiminta = "environment";
  let sedangMembuka = false;
  let suntikSendiri = false;    // change dari "Gunakan Foto" bukan dari user

  function setStatus(teks, galat) {
    if (!statusEl) return;
    statusEl.textContent = teks;
    statusEl.classList.toggle("galat", !!galat);
    if (!galat) statusEl.classList.remove("kosong");
  }

  function didukung() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  }

  /* Rantai constraint untuk SATU arah hadap. Kegagalan Overconstrained /
     NotFound turun ke kandidat berikutnya; izin ditolak (NotAllowed /
     Security) langsung berhenti — mengulang tidak akan mengubah izin. */
  function kandidatKamera(hadap) {
    return [
      { audio: false, video: { facingMode: { exact: hadap }, width: { ideal: 1920 }, height: { ideal: 1080 } } },
      { audio: false, video: { facingMode: { ideal: hadap }, width: { ideal: 1920 }, height: { ideal: 1080 } } },
      { audio: false, video: { width: { ideal: 1280 }, height: { ideal: 720 } } },
      { audio: false, video: true },
    ];
  }

  async function mintaStream(hadap) {
    let galatTerakhir = null;
    for (const c of kandidatKamera(hadap)) {
      try {
        return await navigator.mediaDevices.getUserMedia(c);
      } catch (e) {
        galatTerakhir = e;
        if (e && (e.name === "NotAllowedError" || e.name === "SecurityError")) throw e;
      }
    }
    throw galatTerakhir || new Error("Kamera tidak tersedia.");
  }

  function pesanGalat(e) {
    if (!window.isSecureContext) {
      return "Akses kamera butuh koneksi aman. Buka aplikasi lewat " +
        "https://app.rachmatx.me atau localhost, bukan alamat http biasa.";
    }
    switch (e && e.name) {
      case "NotAllowedError":
        return "Izin kamera ditolak. Izinkan akses kamera untuk situs ini " +
          "di pengaturan browser, lalu buka Mode Kamera lagi.";
      case "NotFoundError":
      case "OverconstrainedError":
        return "Tidak ada kamera yang ditemukan di perangkat ini.";
      case "NotReadableError":
        return "Kamera sedang dipakai aplikasi lain. Tutup aplikasi itu, lalu coba lagi.";
      default:
        return "Kamera tidak bisa dibuka: " + ((e && e.message) || "galat tidak dikenal") + ".";
    }
  }

  function tampilLive() {
    video.hidden = false;
    fotoImg.hidden = true;
    kontrolLive.hidden = false;
    kontrolFoto.hidden = true;
    galatBox.hidden = true;
  }
  function tampilFoto() {
    video.hidden = true;
    fotoImg.hidden = false;
    kontrolLive.hidden = true;
    kontrolFoto.hidden = false;
    galatBox.hidden = true;
  }
  function tampilGalat(pesan) {
    video.hidden = true;
    fotoImg.hidden = true;
    kontrolLive.hidden = true;
    kontrolFoto.hidden = true;
    galatBox.hidden = false;
    galatBox.textContent = pesan;
  }

  function matikanStream() {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
    video.srcObject = null;
  }

  function tutupKamera() {
    matikanStream();
    berkasJepret = null;
    if (urlFoto) { URL.revokeObjectURL(urlFoto); urlFoto = null; }
    fotoImg.removeAttribute("src");
    lapis.hidden = true;
    btnModeTeks.textContent = "Mode Kamera";
    btnMode.setAttribute("aria-pressed", "false");
    btnMode.classList.remove("aktif");
  }

  /* Info kamera dari track yang benar-benar jalan: label arah + resolusi
     + jumlah kamera (untuk tombol ganti). enumerateDevices memberi label
     penuh hanya SETELAH izin diberikan, jadi dipanggil di sini. */
  async function perbaruiInfoKamera() {
    const track = stream && stream.getVideoTracks()[0];
    if (!track) return;
    const s = track.getSettings ? track.getSettings() : {};
    if (chip) {
      chip.textContent =
        s.facingMode === "environment" ? "KAMERA BELAKANG" :
        s.facingMode === "user" ? "KAMERA DEPAN" :
        (track.label || "KAMERA PERANGKAT");
    }
    const w = s.width || video.videoWidth, h = s.height || video.videoHeight;
    if (chipInfo) chipInfo.textContent = w && h ? w + "x" + h : "";
    if (btnGanti && navigator.mediaDevices.enumerateDevices) {
      try {
        const alat = await navigator.mediaDevices.enumerateDevices();
        const n = alat.filter((a) => a.kind === "videoinput").length;
        btnGanti.classList.toggle("jp-kam-tak-terlihat", n < 2);
      } catch (e) {
        console.warn("[JalanPantau] enumerateDevices kamera", e);
      }
    }
  }

  async function bukaKamera() {
    if (sedangMembuka) return;
    lapis.hidden = false;
    btnModeTeks.textContent = "Tutup Kamera";
    btnMode.setAttribute("aria-pressed", "true");
    btnMode.classList.add("aktif");
    if (!didukung()) {
      tampilGalat(pesanGalat(null));
      setStatus("Browser tidak mendukung akses kamera.", true);
      return;
    }
    sedangMembuka = true;
    btnMode.disabled = true;
    tampilLive();
    petunjuk.textContent = "Membuka kamera...";
    try {
      stream = await mintaStream(menghadapDiminta);
      video.srcObject = stream;
      try { await video.play(); } catch (e) { console.warn("[JalanPantau] video kamera play", e); }
      tampilLive();
      await perbaruiInfoKamera();
      petunjuk.textContent = "Arahkan kamera ke permukaan jalan";
      setStatus("Kamera aktif. Arahkan ke permukaan jalan, lalu jepret.");
    } catch (e) {
      console.error("[JalanPantau] membuka kamera", e);
      matikanStream();
      tampilGalat(pesanGalat(e));
      setStatus("Kamera tidak bisa dibuka.", true);
    } finally {
      sedangMembuka = false;
      btnMode.disabled = false;
    }
  }

  /* GPS ditempel saat jepret (pengganti EXIF yang hilang dari canvas):
     isi hanya bila kolomnya masih kosong, persis pola EXIF di deteksi.js. */
  function tempelGPS() {
    if (!navigator.geolocation) return;
    const latEl = document.getElementById("lat-gambar");
    const lonEl = document.getElementById("lon-gambar");
    if (!latEl || !lonEl || latEl.value.trim() !== "" || lonEl.value.trim() !== "") return;
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        if (typeof isiKoordinat === "function") {
          isiKoordinat("lat-gambar", "lon-gambar", pos.coords.latitude, pos.coords.longitude);
        }
      },
      function (e) { console.warn("[JalanPantau] GPS saat jepret kamera", e); },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 300000 }
    );
  }

  function namaBerkasKamera() {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    return "kamera-" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) +
      "-" + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()) + ".jpg";
  }

  btnMode.addEventListener("click", () => {
    if (lapis.hidden) bukaKamera();
    else tutupKamera();
  });

  btnJepret.addEventListener("click", () => {
    if (!stream || !video.videoWidth) return;
    const kanvas = document.createElement("canvas");
    kanvas.width = video.videoWidth;
    kanvas.height = video.videoHeight;
    kanvas.getContext("2d").drawImage(video, 0, 0);
    kanvas.toBlob((blob) => {
      if (!blob) {
        setStatus("Gagal mengambil foto dari kamera.", true);
        return;
      }
      berkasJepret = new File([blob], namaBerkasKamera(),
        { type: "image/jpeg", lastModified: Date.now() });
      if (urlFoto) URL.revokeObjectURL(urlFoto);
      urlFoto = URL.createObjectURL(blob);
      fotoImg.src = urlFoto;
      tampilFoto();
      petunjuk.textContent = "Foto diambil — periksa dulu sebelum dipakai";
      setStatus("Foto diambil. Gunakan foto ini, atau foto ulang.");
      tempelGPS();
    }, "image/jpeg", 0.92);
  });

  btnUlang.addEventListener("click", () => {
    berkasJepret = null;
    tampilLive();
    petunjuk.textContent = "Arahkan kamera ke permukaan jalan";
    setStatus("Kamera aktif. Arahkan ke permukaan jalan, lalu jepret.");
  });

  btnPakai.addEventListener("click", () => {
    if (!berkasJepret) return;
    const f = berkasJepret;
    tutupKamera();
    // Masuk ke alur yang sama persis dengan pilih file / drag & drop:
    // terimaBerkas menaruh File ke #gambar + memicu pratinjau & status.
    suntikSendiri = true;
    if (typeof terimaBerkas === "function") terimaBerkas([f]);
    suntikSendiri = false;
  });

  btnGanti.addEventListener("click", async () => {
    if (!stream || sedangMembuka) return;
    menghadapDiminta = menghadapDiminta === "environment" ? "user" : "environment";
    sedangMembuka = true;
    matikanStream();
    tampilLive();
    petunjuk.textContent = "Mengganti kamera...";
    try {
      stream = await mintaStream(menghadapDiminta);
      video.srcObject = stream;
      try { await video.play(); } catch (e) { console.warn("[JalanPantau] video ganti kamera play", e); }
      await perbaruiInfoKamera();
      petunjuk.textContent = "Arahkan kamera ke permukaan jalan";
    } catch (e) {
      console.error("[JalanPantau] mengganti kamera", e);
      tampilGalat(pesanGalat(e));
      setStatus("Kamera tidak bisa dibuka.", true);
    } finally {
      sedangMembuka = false;
    }
  });

  /* Kebersihan stream: pilih file manual / pindah ke tab Live / tinggalkan
     halaman -> kamera mati. Suntikan "Gunakan Foto" dikecualikan karena
     tutupKamera() sudah dipanggil lebih dulu di sana. */
  if (inputGambar) {
    inputGambar.addEventListener("change", () => {
      if (!suntikSendiri && !lapis.hidden) tutupKamera();
    });
  }
  const tabLive = document.getElementById("tab-live");
  if (tabLive) tabLive.addEventListener("click", () => { if (!lapis.hidden) tutupKamera(); });
  window.addEventListener("pagehide", matikanStream);
})();
