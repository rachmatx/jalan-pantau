"""Koreksi dimensi operator + istilah batas atas (Opsi B, 1 Nov 2026).

Akar masalah: yang dilaporkan sistem adalah SISI BOUNDING BOX, bukan ukuran
kerusakan. Pada retak miring/berkelok sisi pendek box mengukur simpangan lateral
+ padding, sehingga satu foto lapangan menghasilkan "lebar retak 370,7 mm" untuk
retak nyata ~10-12 cm, dan garis retak 3-8 mm menjadi "85 mm" + severity Berat.
Dua hal dikunci di sini:
1. operator bisa menimpa panjang/lebar satu temuan, dan luas + severity + bahan
   + skor dihitung ulang dari angka itu;
2. istilah jejak audit menyebut sumber angkanya (kotak = batas atas, manual =
   hasil ukur) supaya tidak lagi mengaku mengukur lebar bukaan retak.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "web"), str(ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

DETEKSI_JS = str(ROOT / "web" / "static" / "js" / "deteksi.js")
APP_PY = str(ROOT / "web" / "app.py")
CIVIC_CSS = str(ROOT / "web" / "static" / "css" / "civic.css")


def _teks(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _fungsi(js, nama):
    m = re.search(r"(?:async\s+)?function\s+%s\([^)]*\)\s*\{(.*?)\n\}" % nama,
                  js, re.S)
    if m is None:
        raise AssertionError("fungsi %s tidak ditemukan" % nama)
    return m.group(1)


def _cfg():
    from severity import load_config
    return load_config(str(ROOT / "config" / "severity.yaml"))


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        from database import (migrasi_admin_v2, migrasi_sesi_v2, init_admin)
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()
    return app


def _retak(severity="Berat"):
    """Satu temuan retak yang sisi box-nya jauh lebih lebar dari kenyataannya."""
    return {"kelas": "transverse_crack", "conf": 0.6, "severity": severity,
            "box": [0, 0, 400, 200], "idx_asli": 0,
            "panjang_cm": 17.3, "lebar_cm": 8.6, "luas_cm2": 148.8,
            "bahan": "b", "skor_prioritas": 100, "dasar": "d"}


class TestDiagnoseCm(unittest.TestCase):
    """Jalur manual memakai ambang yang sama dengan jalur box."""

    def test_severity_dan_luas_dari_angka_manual(self):
        from severity import diagnose_cm
        d = diagnose_cm("transverse_crack", 40.0, 0.5, _cfg())
        self.assertEqual(d["severity"], "Ringan")   # 5 mm < 10 mm
        self.assertEqual((d["panjang_cm"], d["lebar_cm"]), (40.0, 0.5))
        self.assertEqual(d["luas_cm2"], 20.0)

    def test_sisi_dinormalkan_panjang_tetap_lebih_besar(self):
        from severity import diagnose_cm
        d = diagnose_cm("transverse_crack", 1.0, 12.0, _cfg())
        self.assertEqual((d["panjang_cm"], d["lebar_cm"]), (12.0, 1.0))
        self.assertEqual(d["severity"], "Sedang")   # 10 mm <= lebar < 75 mm

    def test_jejak_audit_sebut_hasil_ukur(self):
        from severity import diagnose_cm
        d = diagnose_cm("transverse_crack", 40.0, 0.5, _cfg())
        self.assertIn("lebar retak 5 mm (manual)", d["dasar"])

    def test_diagnose_box_bertulis_lebar_kotak(self):
        """Angka dari box tidak boleh lagi mengaku sebagai lebar retak."""
        from severity import diagnose
        cfg = _cfg()
        ppc = cfg["pixels_per_cm"]
        d = diagnose("transverse_crack", 0, 0, 100 * ppc, 0.5 * ppc, cfg)
        self.assertIn("lebar kotak 5 mm", d["dasar"])
        self.assertNotIn("lebar retak", d["dasar"])
        self.assertEqual(d["severity"], "Ringan")

    def test_lubang_dan_luasan_jalur_manual(self):
        from severity import diagnose_cm
        cfg = _cfg()
        d = diagnose_cm("pothole", 30.0, 25.0, cfg)
        self.assertEqual(d["severity"], "Sedang")   # bin diameter 20-45 cm
        self.assertIn("manual", d["dasar"])
        self.assertIn("kelas ukuran", d["dasar"])
        a = diagnose_cm("alligator_crack", 30.0, 5.0, cfg)
        self.assertEqual(a["luas_cm2"], 150.0)
        self.assertIn("kelas luasan", a["dasar"])


class TestKoreksiDimensi(unittest.TestCase):
    def _terapkan(self, dimensi):
        from deteksi import terapkan_koreksi
        return terapkan_koreksi([_retak()], dimensi=dimensi)

    def test_info_menghitung_koreksi_dimensi(self):
        _, total, info = self._terapkan({"0": {"panjang_cm": 40, "lebar_cm": 0.8}})
        self.assertEqual(info["dimensi"], 1)
        self.assertEqual(info["total"], 1)
        self.assertEqual(total, 33)

    def test_hasil_memakai_angka_operator(self):
        baru, _, _ = self._terapkan({"0": {"panjang_cm": 40, "lebar_cm": 0.8}})
        r = baru[0]
        self.assertEqual((r["panjang_cm"], r["lebar_cm"]), (40.0, 0.8))
        self.assertEqual(r["luas_cm2"], 32.0)
        self.assertEqual(r["severity"], "Ringan")   # 8 mm < 10 mm
        self.assertEqual(r["skor_prioritas"], 33)
        self.assertEqual(r["bahan"], _cfg()["bahan"]["Ringan"])
        self.assertEqual(r["makna"], "tingkat keparahan")
        self.assertIn("lebar retak 8 mm (manual)", r["dasar"])

    def test_satu_sisi_boleh_dikirim_sendiri(self):
        baru, _, _ = self._terapkan({"0": {"lebar_cm": 0.8}})
        self.assertEqual(baru[0]["lebar_cm"], 0.8)
        self.assertEqual(baru[0]["panjang_cm"], 17.3,
                         "sisi yang tidak dikoreksi ikut berubah")

    def test_diubah_menyebut_dimensi_dan_severity(self):
        baru, _, _ = self._terapkan({"0": {"lebar_cm": 0.8}})
        self.assertIn("dimensi 17.3x8.6 -> 17.3x0.8 cm", baru[0]["diubah"])
        self.assertIn("severity Berat->Ringan", baru[0]["diubah"])

    def test_box_conf_idx_asli_pertahankan(self):
        baru, _, _ = self._terapkan({"0": {"lebar_cm": 0.8}})
        self.assertEqual(baru[0]["box"], [0, 0, 400, 200])
        self.assertEqual(baru[0]["idx_asli"], 0)
        self.assertEqual(baru[0]["conf"], 0.6)
        self.assertEqual(baru[0]["sumber"], "AI")

    def test_severity_eksplisit_menang_atas_hasung_dimensi(self):
        from deteksi import terapkan_koreksi
        baru, _, info = terapkan_koreksi([_retak("Ringan")],
                                         dimensi={"0": {"lebar_cm": 0.8}},
                                         severity={"0": "Berat"})
        self.assertEqual(baru[0]["severity"], "Berat")
        self.assertEqual(baru[0]["skor_prioritas"], 100)
        self.assertEqual(info["dimensi"], 1)
        self.assertEqual(info["severity"], 1)
        self.assertEqual(info["total"], 2)

    def test_koreksi_severity_tanpa_dimensi_tetap_lama(self):
        from deteksi import terapkan_koreksi
        baru, _, info = terapkan_koreksi([_retak("Ringan")],
                                         severity={"0": "Berat"})
        self.assertEqual(baru[0]["diubah"], "severity Ringan->Berat")
        self.assertEqual(info["severity"], 1)
        self.assertEqual(info["dimensi"], 0)

    def test_baris_tanpa_box_untuk_koreksi_severity(self):
        from deteksi import terapkan_koreksi
        r = _retak("Ringan")
        del r["box"]
        baru, _, _ = terapkan_koreksi([r], severity={"0": "Berat"})
        self.assertEqual(baru[0]["severity"], "Berat")

    def test_hapus_menang_atas_dimensi(self):
        from deteksi import terapkan_koreksi
        baru, _, info = terapkan_koreksi([_retak()], hapus=[0],
                                         dimensi={"0": {"lebar_cm": 1}})
        self.assertEqual(baru, [])
        self.assertEqual((info["hapus"], info["dimensi"]), (1, 0))

    def test_dimensi_kosong_tidak_mengubah_apa_pun(self):
        baru, _, info = self._terapkan({})
        self.assertEqual(info["total"], 0)
        self.assertNotIn("diubah", baru[0])


class TestMutuBukti(unittest.TestCase):
    """Sampling + mutu bukti (disetujui user 1 Nov 2026).

    Operator tidak disuruh mengukur semua temuan: yang menuntut angka lapangan
    hanya Berat, karena di situlah angka menentukan biaya dan material. Sebagai
    gantinya tiap baris menyebut MUTU bukti angkanya — estimasi (sisi box),
    visual (severity diubah tanpa ukur), terukur (angka operator) — supaya yang
    dibaca di laporan tidak tampak lebih presisi daripada kenyataannya.
    """

    def _terapkan(self, rows, **koreksi):
        from deteksi import terapkan_koreksi
        return terapkan_koreksi(rows, **koreksi)[0]

    def test_baris_tak_disentuh_mutu_estimasi(self):
        r = self._terapkan([_retak()])[0]
        self.assertEqual(r["mutu"], "estimasi")

    def test_angka_operator_jadi_terukur(self):
        from deteksi import perlu_diukur
        r = self._terapkan([_retak()],
                           dimensi={"0": {"panjang_cm": 12, "lebar_cm": 3}})[0]
        self.assertEqual(r["mutu"], "terukur")
        self.assertFalse(perlu_diukur(r),
                         "Berat yang sudah diukur tidak boleh ditagih lagi")

    def test_severity_saja_jadi_visual_dan_diminta_ukur(self):
        from deteksi import perlu_diukur
        r = self._terapkan([_retak("Sedang")], severity={"0": "Berat"})[0]
        self.assertEqual(r["mutu"], "visual")
        self.assertEqual(r["severity"], "Berat")
        self.assertTrue(perlu_diukur(r))

    def test_terukur_tidak_turun_mutu_kala_severity_diubah(self):
        r = self._terapkan([dict(_retak("Berat"), mutu="terukur")],
                           severity={"0": "Sedang"})[0]
        self.assertEqual(r["mutu"], "terukur",
                         "angkanya tersimpan di baris ini; mengubah severity "
                         "tidak menghapus hasil ukur")

    def test_baris_lama_dibaca_dari_jejak_audit(self):
        """Sesi tersimpan sebelum kolom 'mutu' ada tidak dituduh belum mengukur."""
        r = self._terapkan([dict(_retak("Ringan"),
                                 diubah="dimensi 17.3x8.6 -> 12x3 cm")])[0]
        self.assertEqual(r["mutu"], "terukur")
        r = self._terapkan([dict(_retak("Sedang"),
                                 diubah="severity Sedang->Berat")])[0]
        self.assertEqual(r["mutu"], "visual")

    def test_angka_manual_di_dasar_dibaca_sebagai_terukur(self):
        """Baris dari tabel `temuan` tidak punya kolom mutu/jejak; satu-satunya
        bukti yang tersimpan adalah penanda (manual) pada dasar perhitungan."""
        from deteksi import perlu_diukur
        r = self._terapkan([{"kelas": "pothole", "severity": "Berat",
                             "dasar": "diameter 12 cm (manual, kelas ukuran)"}])[0]
        self.assertEqual(r["mutu"], "terukur")
        self.assertFalse(perlu_diukur(r))
        r = self._terapkan([{"kelas": "pothole", "severity": "Berat",
                             "dasar": "diameter ±45 cm (kelas ukuran)"}])[0]
        self.assertEqual(r["mutu"], "estimasi")
        self.assertTrue(perlu_diukur(r))

    def test_ringan_dan_sedang_tidak_diminta_ukur(self):
        from deteksi import perlu_diukur
        for sev in ("Ringan", "Sedang"):
            self.assertFalse(perlu_diukur({"severity": sev, "mutu": "estimasi"}))

    def test_mutu_baris_tanpa_kolom_dianggap_estimasi(self):
        """Baris /api/detect belum pernah diverifikasi sama sekali."""
        from deteksi import perlu_diukur
        self.assertTrue(perlu_diukur({"severity": "Berat"}))


class TestValidasiDimensi(unittest.TestCase):
    def _tolak(self, nilai, pesan=None):
        from deteksi import terapkan_koreksi
        with self.assertRaises(ValueError) as cm:
            terapkan_koreksi([_retak()], dimensi={"0": nilai})
        if pesan:
            self.assertIn(pesan, str(cm.exception))

    def test_nol_dan_negatif_ditolak(self):
        self._tolak({"lebar_cm": 0}, "harus")
        self._tolak({"lebar_cm": -5})

    def test_terlalu_besar_ditolak(self):
        self._tolak({"panjang_cm": 1001})

    def test_huruf_ditolak(self):
        self._tolak({"lebar_cm": "sebelas"}, "bukan angka")

    def test_nan_dan_inf_ditolak(self):
        self._tolak({"lebar_cm": float("nan")})
        self._tolak({"lebar_cm": float("inf")})

    def test_nilai_bukan_objek_ditolak(self):
        self._tolak(12)

    def test_koma_desimal_diterima(self):
        from deteksi import terapkan_koreksi
        baru, _, info = terapkan_koreksi([_retak()],
                                         dimensi={"0": {"lebar_cm": "0,8"}})
        self.assertEqual(info["dimensi"], 1)
        self.assertEqual(baru[0]["lebar_cm"], 0.8)

    def test_idx_tidak_kenal_dimensinya_diabaikan(self):
        from deteksi import terapkan_koreksi
        baru, _, info = terapkan_koreksi([_retak()],
                                         dimensi={"99": {"lebar_cm": 1}})
        self.assertEqual(info["total"], 0)
        self.assertNotIn("diubah", baru[0])


class TestApiVerifikasi(unittest.TestCase):
    def setUp(self):
        self.c = _app().test_client()

    def test_dimensi_diterima_api(self):
        r = self.c.post("/api/verifikasi", json={
            "rows": [_retak()], "dimensi": {"0": {"lebar_cm": 0.8}}})
        self.assertEqual(r.status_code, 200, r.get_json())
        json = r.get_json()
        self.assertEqual(json["info"]["dimensi"], 1)
        self.assertEqual(json["rows"][0]["lebar_cm"], 0.8)

    def test_dimensi_di_luar_batas_jadi_400_bukan_500(self):
        r = self.c.post("/api/verifikasi", json={
            "rows": [_retak()], "dimensi": {"0": {"lebar_cm": 0}}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("harus", r.get_json()["error"])

    def test_dimensi_bukan_dict_jadi_400(self):
        r = self.c.post("/api/verifikasi", json={
            "rows": [_retak()], "dimensi": [1, 2]})
        self.assertEqual(r.status_code, 400)

    def test_tanpa_dimensi_perilaku_lama_utuh(self):
        r = self.c.post("/api/verifikasi", json={
            "rows": [_retak("Ringan")], "severity": {"0": "Berat"}})
        self.assertEqual(r.get_json()["rows"][0]["diubah"],
                         "severity Ringan->Berat")


class TestKontrakTampilan(unittest.TestCase):
    """Kolom dimensi bisa diedit, dan state-nya ikut dikirim + dihitung."""

    def setUp(self):
        self.js = _teks(DETEKSI_JS)

    def test_input_dimensi_dirender(self):
        self.assertIn("function sisiInput", self.js)
        self.assertIn('sisiInput(ia, "panjang_cm"', self.js)
        self.assertIn('sisiInput(ia, "lebar_cm"', self.js)
        self.assertIn("${dimensi}", self.js)

    def test_state_verdim_dibuat_dan_dikirim(self):
        self.assertIn("var verDim = {};", self.js)
        self.assertIn("dimensi: verDim", _fungsi(self.js, "syncVerifikasi"))

    def test_muat_ulang_dan_reset_ikut_menghapus_verdim(self):
        self.assertGreaterEqual(
            self.js.count("verDim = {};"), 4,
            "reset/muat hasil wajib membersihkan koreksi dimensi")

    def test_batas_validasi_sama_dengan_backend(self):
        m = re.search(r"var DIM_MIN_CM = ([\d.]+), DIM_MAX_CM = (\d+)", self.js)
        self.assertIsNotNone(m)
        from deteksi import DIM_MAX_CM, DIM_MIN_CM
        self.assertEqual(float(m.group(1)), DIM_MIN_CM)
        self.assertEqual(float(m.group(2)), float(DIM_MAX_CM))

    def test_teks_verifikasi_menyebut_dimensi(self):
        self.assertIn("koreksi dimensi", _fungsi(self.js, "teksVerifikasi"))

    def test_kolom_dimensi_dinyatakan_batas_atas(self):
        self.assertIn("batas atas", self.js)
        self.assertIn("simpanDimensi", self.js)

    def test_input_sisi_tidak_memakai_number(self):
        """type=number mengubah ketikan "0,8" menjadi .value kosong (Chromium),
        sehingga koreksi operator hilang tanpa kabar."""
        badan = _fungsi(self.js, "sisiInput")
        self.assertIn('type="text"', badan)
        self.assertIn("inputmode=", badan)
        self.assertNotIn('type="number"', badan)

    def test_satuan_cm_tertulis_di_layar(self):
        """Tooltip saja tidak cukup: baris yang sama menampilkan "lebar kotak
        ... mm", jadi operator bisa salah isi 10x lipat tanpa sadar."""
        self.assertIn('class="jp-dim-unit">cm<', _fungsi(self.js, "sisiInput"))
        self.assertIn(".jp-dim-unit", _teks(CIVIC_CSS))

    def test_angka_dibaca_ketat(self):
        """parseFloat("0.8.5") diam-diam jadi 0.8; penolakan harus eksplisit."""
        badan = _fungsi(self.js, "angkaCm")
        self.assertIn(r"^\d+(\.\d+)?$", badan)
        self.assertIn("NaN", badan)

    def test_input_ditolak_kembali_ke_angka_terpakai(self):
        m = re.search(r"const galat = simpanDimensi\(inp\);.*?\n    \}",
                      self.js, re.S)
        self.assertIsNotNone(m, "cabang galat dimensi tidak ditemukan")
        self.assertIn("renderTabelDeteksi();", m.group(0),
                      "input ditolak: kolom harus menampilkan angka yang terpakai")
        self.assertNotIn("inp.value =", _fungsi(self.js, "simpanDimensi"))

    def test_kolom_sumber_memakai_mutu_bukti(self):
        """'AI*' + jejak tidak lagi cukup: yang perlu dibaca operator adalah
        dari mana angka itu datang, bukan cuma ada/tidaknya perubahan."""
        for kata in ("batas atas box", "dilihat mata", "diukur manual"):
            self.assertIn(kata, self.js)
        self.assertIn("selSumber(r)", _fungsi(self.js, "renderTabelDeteksi"))
        self.assertNotIn("AI*", self.js)

    def test_chip_perlu_diukur_hanya_berat_belum_terukur(self):
        badan = _fungsi(self.js, "perluDiukur")
        self.assertIn('r.severity === "Berat"', badan)
        self.assertIn('!== "terukur"', badan)
        self.assertIn("perluDiukur(r)", _fungsi(self.js, "renderTabelDeteksi"))
        self.assertIn(".jp-ukur-chip", _teks(CIVIC_CSS))

    def test_statusbar_menyebut_jumlah_perlu_diukur(self):
        """Sampling harus kelihatan tanpa membuka tiap baris: operator melihat
        sendiri berapa pekerjaan yang masih tersisa — di hasil baru, setelah
        koreksi, dan setelah halaman dibuka ulang."""
        self.assertIn("Perlu diukur", _fungsi(self.js, "nudgePerluDiukur"))
        self.assertIn("nudgePerluDiukur(deteksiRows)",
                      _fungsi(self.js, "refreshVerifikasiUI"))
        m = re.search(r'status\.textContent = data\.rows\.length.*?\);\n',
                      self.js, re.S)
        self.assertIsNotNone(m, "teks status jalur restore tidak ditemukan")
        self.assertIn("nudgePerluDiukur(data.rows)", m.group(0))

    def test_static_version_naik(self):
        v = re.search(r'STATIC_VERSION = "(\d+)"', _teks(APP_PY)).group(1)
        self.assertGreaterEqual(int(v), 60, "JS berubah: cache-buster wajib naik")


class TestCatatanLaporan(unittest.TestCase):
    """PDF memakai aturan sampling yang sama dengan layar, dan mengaku apa
    adanya soal mutu angka."""

    def test_predikat_pdf_sama_dengan_backend(self):
        from deteksi import perlu_diukur
        from laporan import _perlu_diukur
        for row in ({"severity": "Berat"},
                    {"severity": "Berat", "mutu": "visual"},
                    {"severity": "Berat", "mutu": "terukur"},
                    {"severity": "Berat",
                     "dasar": "diameter 12 cm (manual, kelas ukuran)"},
                    {"severity": "Berat",
                     "dasar": "lebar kotak 85 mm"},
                    {"severity": "Sedang"},
                    {"severity": "Sedang", "mutu": "terukur"},
                    {}):
            self.assertEqual(perlu_diukur(row), _perlu_diukur(row),
                             "daftar kerja di layar berbeda dengan catatan PDF")

    def test_catatan_pdf_menyebut_temuan_belum_diukur(self):
        t = _teks(str(ROOT / "app" / "laporan.py"))
        self.assertIn("belum diukur di lapangan", t)
        self.assertIn("n_belum += 1", t)

    def test_pdf_tetap_terbuat_dengan_temuan_belum_diukur(self):
        from laporan import buat_laporan
        items = [{"kelas": "transverse_crack", "severity": "Berat", "conf": 0.6,
                  "dasar": "lebar kotak 85 mm", "bahan": "lastap", "mutu": "estimasi",
                  "panjang_cm": 17.3, "lebar_cm": 8.6, "luas_cm2": 148.8},
                 {"kelas": "pothole", "severity": "Ringan", "conf": 0.5,
                  "dasar": "diameter 12 cm (manual, kelas ukuran)", "bahan": "asbut",
                  "mutu": "terukur", "panjang_cm": 12, "lebar_cm": 12,
                  "luas_cm2": 113, "diubah": "dimensi 30x30 -> 12x12 cm"}]
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            buat_laporan(path, items, 100, meta={"Sumber": "uji"})
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(5), b"%PDF-")
            self.assertGreater(os.path.getsize(path), 1000)
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
