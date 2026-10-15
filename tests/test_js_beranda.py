"""Jalankan JavaScript inline Beranda Dinas di Node tanpa browser.

Asal bug yang belum tertangkap tes manapun: halaman detail SPK kontraktor
memiliki kotak KPI "Progres Titik" yang id-nya tidak pernah diisi JavaScript,
jadi nilainya selalu tanda hubung. Ratusan test tetap hijau karena tidak ada
test yang benar-benar MENJALANKAN JavaScript halaman -- hanya memeriksa
sintaksnya.

Test di bawah menutup celah itu untuk Beranda Dinas: skrip diambil dari
hasil render Flask (bukan dari berkas template, supaya seluruh ekspresi Jinja
sudah selesai), lalu dijalankan di Node dengan DOM dan fetch tiruan. Setelah
itu angka KPI dibaca kembali dari DOM.

Kalau ada galat ReferenceError, variabel tak terdeklarasi, atau pemanggilan
fungsi yang tidak jadi terjadi, test ini gagal dengan pesan yang menyebut
baris sumbernya.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())

AKAR = pathlib.Path(__file__).resolve().parent.parent
NODE = shutil.which("node")

# Jumlah per status sengaja dibuat berbeda-beda, jadi kalau KPI ternyata
# tidak diperbarui, angkanya pasti salah dan tidak kebetulan cocok.
BARIS = [
    {"id": 1, "bap_nomor": "BA-UJI/1", "waktu": "2026-10-01T08:00:00",
     "lokasi": "Jl. Satu", "urgensi": "Kritis", "status": "Terkirim",
     "n_temuan": 3, "total_rp": 1_000_000, "lat": -6.9, "lon": 107.6,
     "instansi_nama": "Dinas Uji"},
    {"id": 2, "bap_nomor": "BA-UJI/2", "waktu": "2026-10-01T09:00:00",
     "lokasi": "Jl. Dua", "urgensi": "Tinggi", "status": "Terkirim",
     "n_temuan": 2, "total_rp": 500_000, "lat": -6.91, "lon": 107.61,
     "instansi_nama": "Dinas Uji"},
    {"id": 3, "bap_nomor": "BA-UJI/3", "waktu": "2026-10-02T10:00:00",
     "lokasi": "Jl. Tiga", "urgensi": "Rutin", "status": "Diproses",
     "n_temuan": 1, "total_rp": 250_000, "lat": -6.92, "lon": 107.62,
     "instansi_nama": "Dinas Uji"},
    {"id": 4, "bap_nomor": "BA-UJI/4", "waktu": "2026-10-03T11:00:00",
     "lokasi": "Jl. Empat", "urgensi": "Tinggi", "status": "Diproses",
     "n_temuan": 4, "total_rp": 2_000_000, "lat": -6.93, "lon": 107.63,
     "instansi_nama": "Dinas Uji"},
    {"id": 5, "bap_nomor": "BA-UJI/5", "waktu": "2026-10-04T12:00:00",
     "lokasi": "Jl. Lima", "urgensi": "Kritis", "status": "Diproses",
     "n_temuan": 2, "total_rp": 750_000, "lat": -6.94, "lon": 107.64,
     "instansi_nama": "Dinas Uji"},
    {"id": 6, "bap_nomor": "BA-UJI/6", "waktu": "2026-10-05T13:00:00",
     "lokasi": "Jl. Enam", "urgensi": "Rutin", "status": "Selesai",
     "n_temuan": 1, "total_rp": 300_000, "lat": -6.95, "lon": 107.65,
     "instansi_nama": "Dinas Uji"},
    {"id": 7, "bap_nomor": "BA-UJI/7", "waktu": "2026-10-06T14:00:00",
     "lokasi": "Jl. Tujuh", "urgensi": "Tinggi", "status": "Selesai",
     "n_temuan": 5, "total_rp": 4_000_000, "lat": -6.96, "lon": 107.66,
     "instansi_nama": "Dinas Uji"},
    {"id": 8, "bap_nomor": "BA-UJI/8", "waktu": "2026-10-07T15:00:00",
     "lokasi": "Jl. Delapan", "urgensi": "Kritis", "status": "Selesai",
     "n_temuan": 3, "total_rp": 1_500_000, "lat": -6.97, "lon": 107.67,
     "instansi_nama": "Dinas Uji"},
    {"id": 9, "bap_nomor": "BA-UJI/9", "waktu": "2026-10-08T16:00:00",
     "lokasi": "Jl. Sembilan", "urgensi": "Rutin", "status": "Selesai",
     "n_temuan": 2, "total_rp": 900_000, "lat": -6.98, "lon": 107.68,
     "instansi_nama": "Dinas Uji"},
    {"id": 10, "bap_nomor": "BA-UJI/10", "waktu": "2026-10-09T17:00:00",
     "lokasi": "Jl. Sepuluh", "urgensi": "Kritis", "status": "Selesai",
     "n_temuan": 1, "total_rp": 100_000, "lat": -6.99, "lon": 107.69,
     "instansi_nama": "Dinas Uji"},
    {"id": 11, "bap_nomor": "BA-UJI/11", "waktu": "2026-10-09T18:00:00",
     "lokasi": "Jl. Sebelas", "urgensi": "Tinggi", "status": "Selesai",
     "n_temuan": 1, "total_rp": 200_000, "lat": -7.00, "lon": 107.70,
     "instansi_nama": "Dinas Uji"},
    {"id": 12, "bap_nomor": "BA-UJI/12", "waktu": "2026-10-09T19:00:00",
     "lokasi": "Jl. Dua Belas", "urgensi": "Rutin", "status": "Selesai",
     "n_temuan": 1, "total_rp": 300_000, "lat": -7.01, "lon": 107.71,
     "instansi_nama": "Dinas Uji"},
]
TOTAL_BARIS = len(BARIS)
# 12 baris (melebihi 10 per halaman) supaya jalur paginator ikut dibangun.
HARAP = {
    "baru": 2,          # Terkirim
    "proses": 3,        # Diproses
    "selesai": 7,       # Selesai
    "total": 12,
}
# 11.200.000 + 100.000 + 200.000 + 300.000 = 11.800.000 -> "Rp11,80 Jt"
HARAP_BIAYA = "Rp11,80 Jt"

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const sumber = fs.readFileSync(process.argv[2], "utf8");
const inti = fs.readFileSync(process.argv[4], "utf8");
const baris = JSON.parse(process.argv[3]);
const totalDb = baris.length;

function buatElemen(id) {
  const el = {
    id: id,
    _teks: "",
    textContent: "",
    innerHTML: "",
    title: "",
    value: "",
    hidden: false,
    disabled: false,
    style: {},
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    children: [],
    addEventListener() {},
    removeEventListener() {},
    appendChild(c) { this.children.push(c); return c; },
    remove() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    setAttribute() {},
    getAttribute() { return null; },
    click() {},
    focus() {},
    getBoundingClientRect() { return { width: 800, height: 400, top: 0, left: 0 }; },
  };
  return el;
}

const elemen = {};
function ambil(id) {
  if (!elemen[id]) elemen[id] = buatElemen(id);
  return elemen[id];
}

// Jam virtual: satu_FRAME langsung melewati durasi animasi, sehingga
// animasiCounter selesai dalam satu langkah dan nilai akhirnya terlihat.
let jam = 0;

const petaStub = {
  setView() { return this; }, fitBounds() { return this; },
  invalidateSize() {}, removeLayer() {}, addTo() { return this; },
};
const L = {
  map: () => petaStub,
  tileLayer: () => ({ addTo() { return this; } }),
  layerGroup: () => ({ addTo() { return this; }, clearLayers() {} }),
  control: { zoom: () => ({ addTo() { return this; } }) },
  marker: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
  divIcon: (o) => o,
};

function jsonRespon(data) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
}

const catatan = [];
const doc = {
  hidden: false,
  getElementById: (id) => ambil(id),
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => {
    const e = buatElemen("baru-" + tag);
    e.click = () => {};
    e.href = "";
    return e;
  },
  addEventListener() {},
  removeEventListener() {},
  body: { appendChild() {} },
};

const sandbox = {
  console,
  document: doc,
  L: L,
  location: { href: "http://localhost/pupr-bandung/dashboard", origin: "http://localhost", reload() {} },
  performance: { now: () => jam },
  requestAnimationFrame: (fn) => { jam += 1000; fn(jam); return 1; },
  cancelAnimationFrame: () => {},
  setTimeout: () => 0,
  clearTimeout: () => {},
  setInterval: () => 0,          // jangan sampai penyegaran otomatis berjalan
  clearInterval: () => {},
  Blob: function(parts, opt) { this.parts = parts; },
  URL: { createObjectURL: () => "blob:x", revokeObjectURL: () => {} },
  Intl,
  Promise,
  Date,
  Math,
  JSON,
  parseInt,
  parseFloat,
  isNaN,
  encodeURIComponent,
  navigator: { userAgent: "node", language: "id" },
  fetch: (url) => {
    catatan.push(url);
    if (url.indexOf("/api/disposisi/stats") !== -1) {
      return jsonRespon({ total: totalDb, baru: 2, diproses: 3, selesai: 4 });
    }
    return jsonRespon(baris);
  },
};
sandbox.window = sandbox;
sandbox.window.addEventListener = function () {};
sandbox.window.matchMedia = () => ({ matches: false });

const hasil = { dipanggil: catatan };

try {
  // Helper bersama harus dimuat lebih dulu, sama seperti di peramban.
  // Kalau tidak, skrip halaman akan gagal dengan
  // "window.jpNomorHalaman is not a function".
  vm.runInContext(inti, vm.createContext(sandbox));
  hasil.intiDimuat = typeof sandbox.window.jpNomorHalaman === "function";
  vm.runInContext(sumber, vm.createContext(sandbox));
  hasil.error = null;
} catch (e) {
  hasil.error = String(e && e.stack ? e.stack.split("\n")[0] : e);
}

// Tunggu sampai tabel DAN seluruh KPI terisi. Urutan muatData() adalah
// renderTabel -> updateKPI -> renderTren -> renderDonat, jadi tabel siap
// duluan. Kalau hanya menunggu tabel, angka KPI masih kosongketika dibaca.
function siap() {
  const tbody = elemen["dash-tabel-body"];
  if (!tbody || String(tbody.innerHTML).indexOf("BA-UJI/") === -1) return false;
  return ["kpi-total", "kpi-baru", "kpi-proses", "kpi-selesai", "kpi-biaya"]
    .every(function (k) {
      // Elemen yang belum pernah diambil bernilai undefined. Kalau ditulis
      // `elemen[k] && elemen[k].textContent`, hasilnya string "undefined"
      // yang panjangnya bukan nol, sehingga pemeriksaan selalu lulus.
      const e = elemen[k];
      return !!e && String(e.textContent).length > 0;
    });
}
const MULAI = Date.now();
(function tunggu() {
  if (siap() || Date.now() - MULAI > 3000) {
    const baca = {};
    for (const k of ["kpi-baru", "kpi-proses", "kpi-selesai", "kpi-total",
                     "kpi-biaya", "dash-count", "dash-tabel-body",
                     "dash-paginasi", "urg-kritis", "urg-tinggi", "urg-rutin"]) {
      if (elemen[k]) baca[k] = String(elemen[k].textContent || elemen[k].innerHTML || "");
    }
    hasil.dom = baca;
    hasil.semuaId = Object.keys(elemen);
    process.stdout.write(JSON.stringify(hasil));
    return;
  }
  setTimeout(tunggu, 10);
})();
"""


def _skrip_beranda():
    """Ambil skrip inline Beranda dari hasil render Flask."""
    from tests.test_routes import _app

    app = _app()
    with app.app_context():
        # modul database hanya bisa diimpor setelah web.app dimuat.
        from database import AKUN_DEMO, init_admin
        init_admin()
        akun = AKUN_DEMO

    c = app.test_client()
    c.post("/login", data={"username": akun[0], "password": akun[1]})
    r = c.get("/pupr-bandung/dashboard")
    html = r.get_data(as_text=True)

    import re
    blok = []
    for m in re.finditer(r"(?s)<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html):
        if m.group(1).strip():
            blok.append(m.group(1))
    assert blok, "tidak ada skrip inline di Beranda"
    return r.status_code, "\n".join(blok), html


@unittest.skipIf(NODE is None, "node tidak tersedia")
class TestSkripBerandaJalan(unittest.TestCase):
    """Skrip Beranda harus benar-benar jalan dan mengisi angka di DOM."""

    @classmethod
    def setUpClass(cls):
        cls.status, skrip, cls.html = _skrip_beranda()
        inti = (AKAR / "web" / "static" / "js" / "jp_core.js").read_text(
            encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            fjs = os.path.join(d, "beranda.js")
            fcore = os.path.join(d, "jp_core.js")
            fh = os.path.join(d, "harness.js")
            pathlib.Path(fjs).write_text(skrip, encoding="utf-8")
            pathlib.Path(fcore).write_text(inti, encoding="utf-8")
            pathlib.Path(fh).write_text(HARNESS, encoding="utf-8")
            p = subprocess.run(
                [NODE, fh, fjs, json.dumps(BARIS), fcore],
                capture_output=True, text=True, timeout=90)
        cls.stderr = p.stderr
        try:
            cls.keluar = json.loads(p.stdout) if p.stdout.strip() else {}
        except json.JSONDecodeError:
            cls.keluar = {}

    def test_halaman_beranda_render(self):
        self.assertEqual(self.status, 200)
        self.assertIn("kpi-baru", self.html)

    def test_tidak_ada_galat_saat_berjalan(self):
        """Referensi tak terdeclare harus menggagalkan test ini."""
        self.assertIsNone(self.keluar.get("error"),
                          "skrip Beranda berhenti: %s\n%s"
                          % (self.keluar.get("error"), self.stderr[:600]))

    def test_keempat_kpi_diisi_dari_data(self):
        """Kotak KPI harus berubah setelah data dimuat.

        Inilah yang membuat bug "Progres Titik" lolos: kotaknya ada di
        markup, tapi tidak pernah diisi, dan tidak ada yang memeriksanya.
        """
        dom = self.keluar.get("dom", {})
        for kunci, harapan in HARAP.items():
            with self.subTest(kpi=kunci):
                nilai = dom.get("kpi-" + kunci, "")
                self.assertEqual(nilai.strip(), str(harapan),
                                 "kpi-%s tidak terisi benar (dapat %r)" % (kunci, nilai))

    def test_kpi_biaya_dihitung(self):
        dom = self.keluar.get("dom", {})
        self.assertEqual(dom.get("kpi-biaya", "").strip(), HARAP_BIAYA)

    def test_jumlah_laporan_tertampil(self):
        dom = self.keluar.get("dom", {})
        self.assertIn(str(TOTAL_BARIS), dom.get("dash-count", ""))

    def test_tabel_terisi_tiket(self):
        """Nomor tiket harus benar-benar masuk ke <tbody>."""
        isi = self.keluar.get("dom", {}).get("dash-tabel-body", "")
        # Urutan bawaan dari yang terbaru, jadi halaman pertama memuat
        # BA-UJI/12 sampai BA-UJI/3; dua baris tertua ada di halaman dua.
        # Dicari sampai tanda "<" supaya "BA-UJI/1" tidak ikut cocok dengan
        # "BA-UJI/12".
        def tiket(nomor):
            return 'class="dash-tiket">BA-UJI/%d<' % nomor

        self.assertIn(tiket(12), isi)
        self.assertIn(tiket(3), isi)
        self.assertNotIn(tiket(1), isi)
        self.assertNotIn(tiket(2), isi)

    def test_paginator_dibangun(self):
        """Dua halaman data harus memunculkan tombol berpindah halaman."""
        isi = self.keluar.get("dom", {}).get("dash-paginasi", "")
        self.assertIn('id="dash-pag-next"', isi)
        self.assertIn('id="dash-pag-prev"', isi)
        self.assertIn("dash-pag-num", isi)

    def test_komposisi_urgensi_dihitung(self):
        dom = self.keluar.get("dom", {})
        self.assertEqual(dom.get("urg-kritis", "").strip(), "4")
        self.assertEqual(dom.get("urg-tinggi", "").strip(), "4")
        self.assertEqual(dom.get("urg-rutin", "").strip(), "4")


class TestUrutanMuatHelper(unittest.TestCase):
    """Helper bersama harus dimuat sebelum skrip halaman.

    Skrip Beranda memanggil window.jpNomorHalaman dari paginator. Kalau
    jp_core.js dimuat terlambat, halaman gagal dengan
    "jpNomorHalaman is not a function" dan tabel tidak pernah terisi --
    tanpa galat yang terlihat, karena pesan galatnya ditelan handler
    .catch di dalam skrip halaman.
    """

    HALAMAN = [
        "/pupr-bandung/dashboard",
        "/pupr-bandung/dashboard/verifikasi",
        "/pupr-bandung/dashboard/spk",
    ]

    def _html(self, url):
        from tests.test_routes import _app

        app = _app()
        with app.app_context():
            from database import AKUN_DEMO, init_admin
            init_admin()
            akun = AKUN_DEMO
        c = app.test_client()
        c.post("/login", data={"username": akun[0], "password": akun[1]})
        return c.get(url).get_data(as_text=True)

    def test_helper_dimuat_terlebih_dulu(self):
        import re
        for url in self.HALAMAN:
            with self.subTest(halaman=url):
                html = self._html(url)
                pos_helper = html.find("jp_core.js")
                self.assertNotEqual(pos_helper, -1,
                                    "jp_core.js tidak dirujuk di %s" % url)
                # Blok <script> inline pertama milik halaman.
                inline = [m for m in re.finditer(
                    r"(?s)<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html)
                    if m.group(1).strip()]
                self.assertTrue(inline, "tidak ada skrip inline di %s" % url)
                self.assertLess(pos_helper, inline[0].start(),
                                "jp_core.js harus dimuat sebelum skrip halaman "
                                "di %s" % url)


if __name__ == "__main__":
    unittest.main()