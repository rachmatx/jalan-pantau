"""Uji eksekusi modul JavaScript peta tanpa browser.

Asal bug: `kontraktor_peta.js` punya parameter bernama `opsi` tapi memakai
`opts = opts || {}`. Dalam mode strict, membaca `opts` yang tak pernah
dideklarasikan melempar ReferenceError dan peta tidak pernah terinisialisasi.
Semua 231 test tetap hijau karena tidak ada satu pun test yang benar-benar
menjalankan JavaScript halaman di browser.

Test di bawah menutup celah itu: modul dijalankan di dalam Node dengan DOM dan
Leaflet tiruan, sehingga ReferenceError, galat logika, atau variabel tak
terdeklarasi akan langsung menggagalkan test.

Modul juga wajib gagal dengan pesan yang terlihat. Diam-diam `return null`
(adalah perilaku versi lama) membuat halaman hanya menampilkan kotak kosong
tanpa penjelasan apa pun.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

AKAR = pathlib.Path(__file__).resolve().parent.parent
JS = AKAR / "web" / "static" / "js"
MODUL = JS / "kontraktor_peta.js"

# Harness: tiruan DOM + Leaflet secukupnya untuk menjalankan modul apa adanya.
HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const sumber = fs.readFileSync(process.argv[2], "utf8");

function lingkung(kasus) {
  const wadah = {
    _html: "",
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; },
  };

  const penanda = [];
  const peta = {
    setView() { return this; },
    fitBounds() { return this; },
    getZoom() { return 13; },
    invalidateSize() {},
    addTo() { return this; },
    removeLayer() { return this; },
  };

  const L = {
    map(id) {
      if (kasus === "peta-melemah") throw new Error("leaflet gagal inisialisasi");
      return peta;
    },
    tileLayer: () => ({ addTo() { return this; } }),
    control: { zoom: () => ({ addTo() { return this; } }) },
    layerGroup: () => ({ addTo() { return this; }, clearLayers() {} }),
    marker(ll) {
      const m = {
        latlng: ll,
        addTo() { return this; },
        bindPopup() { return this; },
        getLatLng() { return ll; },
        openPopup() {},
      };
      penanda.push(m);
      return m;
    },
    divIcon: (o) => o,
  };

  const fakeWindow = {
    console,
    document: { getElementById: (id) => (id === "peta" ? wadah : null) },
  };

  const sandbox = {
    window: fakeWindow,
    document: fakeWindow.document,
    console,
    setTimeout: (fn) => { fn(); return 0; },
    clearTimeout: () => {},
  };
  if (kasus !== "tanpa-leaflet") sandbox.L = L;

  const hasil = { kasus: kasus };

  try {
    vm.runInContext(sumber, vm.createContext(sandbox));
    hasil.modulDimuat = typeof fakeWindow.SPKPeta === "object";
  } catch (e) {
    hasil.modulDimuat = false;
    hasil.error = String(e && e.message ? e.message : e);
  }

  if (hasil.modulDimuat) {
    try {
      const titik = kasus === "satu-titik"
        ? [{ id: 1, lat: -6.91, lon: 107.61, lokasi: "Jl. Merdeka",
             bap_nomor: "BAP-001", urgensi: "Tinggi", status: "Menunggu",
             n_temuan: 3, total_rp: 1500000, spk_id: 7,
             spk_nomor: "SPK-2026-001", punya_foto: true }]
        : [];
      const petaApi = fakeWindow.SPKPeta.buatPeta("peta", titik, {
        urlFoto: "/api/kontraktor/spk/",
        urlSpk: "/kontraktor/spk/",
      });
      hasil.adaHandle = petaApi !== null && typeof petaApi === "object";
      hasil.metode = petaApi
        ? ["peta", "sesuaikan", "fokus", "satelit", "jumlahTitik"]
            .filter((k) => typeof petaApi[k] !== "undefined")
        : [];
      hasil.jumlahTitik = petaApi ? petaApi.jumlahTitik() : null;
    } catch (e) {
      hasil.adaHandle = false;
      hasil.error = String(e && e.message ? e.message : e);
    }
  }

  hasil.pesanDiWadah = wadah._html;
  return hasil;
}

const keluar = {};
for (const k of ["normal", "satu-titik", "tanpa-leaflet", "peta-melemah"]) {
  keluar[k] = lingkung(k);
}
process.stdout.write(JSON.stringify(keluar));
"""


def jalankan(kasus_semua=True):
    """Jalankan modul lewat Node; kembalikan dict hasil per kasus."""
    if shutil.which("node") is None:
        raise unittest.SkipTest("Node.js tidak tersedia")
    with tempfile.TemporaryDirectory() as d:
        harness = pathlib.Path(d) / "harness.js"
        harness.write_text(HARNESS, encoding="utf-8")
        p = subprocess.run(
            ["node", str(harness), str(MODUL)],
            capture_output=True, text=True, timeout=60,
        )
        if p.returncode != 0:
            raise AssertionError(f"harness gagal: {p.stderr.strip()}")
        return json.loads(p.stdout)


class TestModulPeta(unittest.TestCase):
    """kontraktor_peta.js harus benar-benar bisa dijalankan."""

    @classmethod
    def setUpClass(cls):
        cls.hasil = jalankan()

    def test_modul_dimuat_tanpa_error(self):
        h = self.hasil["normal"]
        self.assertTrue(
            h.get("modulDimuat"),
            f"Modul gagal dimuat: {h.get('error')}",
        )
        self.assertNotIn("error", h, f"Error saat memuat modul: {h.get('error')}")

    def test_buatpeta_mengembalikan_handle_lengkap(self):
        h = self.hasil["normal"]
        self.assertTrue(
            h.get("adaHandle"),
            f"buatPeta tidak mengembalikan handle: {h.get('error')}",
        )
        self.assertEqual(
            h.get("metode"),
            ["peta", "sesuaikan", "fokus", "satelit", "jumlahTitik"],
            "API peta kehilangan metode",
        )

    def test_titik_membuat_penanda(self):
        h = self.hasil["satu-titik"]
        self.assertTrue(h.get("adaHandle"), h.get("error"))
        self.assertEqual(h.get("jumlahTitik"), 1)

    def test_tanpa_leaflet_menampilkan_pesan(self):
        """Leaflet gagal dimuat harus terlihat, bukan kotak kosong."""
        h = self.hasil["tanpa-leaflet"]
        self.assertFalse(h.get("adaHandle"))
        self.assertIn("koneksi internet", h.get("pesanDiWadah", ""))

    def test_error_leaflet_menampilkan_pesan(self):
        """Exception runtime harus ditangkap dan ditunjukkan ke pengguna."""
        h = self.hasil["peta-melemah"]
        self.assertFalse(h.get("adaHandle"))
        self.assertIn("gagal dimuat", h.get("pesanDiWadah", ""))


class TestSintaksJs(unittest.TestCase):
    """`node --check` harus jadi bagian suite, bukan langkah manual."""

    def test_semua_js_valid(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js tidak tersedia")
        rusak = []
        for p in sorted(JS.rglob("*.js")):
            r = subprocess.run(
                [node, "--check", str(p)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                rusak.append(f"{p.name}: {r.stderr.strip().splitlines()[0]}")
        self.assertEqual(rusak, [], "JS tidak valid: " + "; ".join(rusak))