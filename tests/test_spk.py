"""Uji alur SPK dari awal sampai akhir: dinas terbitkan -> kontraktor terima
-> kerjakan -> bukti foto -> selesai.

Fokus pengujian ini pada BATASAN, bukan tampilan:
- kontraktor tidak boleh melihat atau mengubah SPK kontraktor lain
- akun dinas tidak boleh memakai API kontraktor (dan sebaliknya)
- status tidak boleh dilompati (Diterbitan -> Selesai ditolak)
- titik tidak boleh ditandai Selesai tanpa foto bukti
- SPK baru otomatis Selesai setelah SELURUH titiknya selesai
"""
import io
import os
import tempfile
import unittest

PASS = os.environ.get("JP_DEMO_PASS", "jalanpantau2026")


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        from database import (init_admin, migrasi_admin_v2, migrasi_disposisi_v2,
                              migrasi_sesi_v2, migrasi_urgensi_v1,
                              init_kontraktor, simpan_disposisi, rekap_temuan,
                              simpan_sesi)
        migrasi_admin_v2()
        migrasi_disposisi_v2()
        migrasi_sesi_v2()
        migrasi_urgensi_v1()
        init_admin()
        init_kontraktor()
        rows = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
                 "total_rp": 1500000, "total_str": "Rp1.500.000"}]
        sid = simpan_sesi("uji", "Jl. Uji km 1", "m", rows, 0, lat=-6.9, lon=107.6)
        r = rekap_temuan(sid)
        app.extensions["uji_d1"] = simpan_disposisi(
            sid, "BAP-001", "Jl. Uji km 1", -6.9, 107.6, r["n_temuan"],
            r["total_rp"], r["worst"], None, "Dinas Uji", "Bandung",
            "uji@example.go.id", "Kritis")
        app.extensions["uji_d2"] = simpan_disposisi(
            sid, "BAP-002", "Jl. Uji km 2", -6.91, 107.61, r["n_temuan"],
            r["total_rp"], r["worst"], None, "Dinas Uji", "Bandung",
            "uji@example.go.id", "Tinggi")
    return app


def _jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 30, 30)).save(buf, format="JPEG")
    buf.seek(0)
    return buf


class _Dasar(unittest.TestCase):
    """Fixture: satu SPK milik KT-001 dengan dua titik pekerjaan."""

    def setUp(self):
        self.app = _app()
        self.d1 = self.app.extensions["uji_d1"]
        self.d2 = self.app.extensions["uji_d2"]
        self.dinas = self.app.test_client()
        r = self.dinas.post("/login", data={"username": "admin", "password": PASS})
        self.assertEqual(r.status_code, 302)
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": "Perbaikan km 1-2",
            "prioritas": "Kritis", "catatan_dinas": "Kritis lebih dulu",
            "disposisi_ids": [self.d1, self.d2]})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.spk = r.get_json()["id"]

    def _kontraktor(self, username="kt_mitrakarya"):
        c = self.app.test_client()
        r = c.post("/login", data={"username": username, "password": PASS})
        self.assertEqual(r.status_code, 302, f"login {username} gagal")
        return c


class TestTerbitkanSpk(_Dasar):
    def test_nomor_spk_terformat(self):
        with self.app.app_context():
            from database import detail_spk
            nomor = detail_spk(self.spk)["nomor"]
        self.assertRegex(nomor, r"^SPK/\d{4}/\d{4}$")

    def test_tugas_hanya_yang_sah(self):
        with self.app.app_context():
            from database import daftar_tugas_spk
            tugas = daftar_tugas_spk(self.spk)
        self.assertEqual(len(tugas), 2)
        self.assertEqual({t["disposisi_id"] for t in tugas}, {self.d1, self.d2})

    def test_disposisi_daerah_lain_ditolak(self):
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bogor", "kontraktor_id": 1, "judul": "x",
            "disposisi_ids": [self.d1]})
        self.assertEqual(r.status_code, 400)

    def test_tanpa_titik_ditolak(self):
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": "x",
            "disposisi_ids": []})
        self.assertEqual(r.status_code, 400)

    def test_kontraktor_tak_ada_ditolak(self):
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 9999, "judul": "x",
            "disposisi_ids": [self.d1]})
        self.assertEqual(r.status_code, 400)

    def test_halaman_dinas_render(self):
        for u in ("/pupr-bandung/dashboard/spk",
                  "/pupr-bandung/dashboard/kontraktor",
                  f"/pupr-bandung/dashboard/spk/{self.spk}"):
            self.assertEqual(self.dinas.get(u).status_code, 200, u)


class TestDashboardKontraktor(_Dasar):
    def test_login_mengarah_ke_dashboard_kontraktor(self):
        c = self._kontraktor()
        self.assertIn("/kontraktor/dashboard", c.get("/login").headers.get("Location", ""))

    def test_halaman_render(self):
        c = self._kontraktor()
        self.assertEqual(c.get("/kontraktor/dashboard").status_code, 200)
        self.assertEqual(c.get(f"/kontraktor/spk/{self.spk}").status_code, 200)

    def test_belum_login_ke_halaman_kontraktor(self):
        self.assertEqual(self.app.test_client().get("/kontraktor/dashboard").status_code, 302)

    def test_kontraktor_ditolak_di_dashboard_dinas(self):
        c = self._kontraktor()
        r = c.get("/pupr-bandung/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/kontraktor/dashboard", r.headers["Location"])

    def test_dinas_ditolak_di_api_kontraktor(self):
        r = self.dinas.get("/api/kontraktor/spk")
        self.assertEqual(r.status_code, 403)

    def test_api_daftar_hanya_spk_sendiri(self):
        c1 = self._kontraktor("kt_mitrakarya")
        c2 = self._kontraktor("kt_jalanpresisi")
        self.assertEqual(len(c1.get("/api/kontraktor/spk").get_json()), 1)
        self.assertEqual(c2.get("/api/kontraktor/spk").get_json(), [])


class TestIsolasiAntarKontraktor(_Dasar):
    def test_spk_milik_orang_tidak_bisa_dibuka(self):
        c2 = self._kontraktor("kt_jalanpresisi")
        self.assertEqual(c2.get(f"/kontraktor/spk/{self.spk}").status_code, 404)

    def test_spk_milik_orang_tidak_bisa_diubah(self):
        c2 = self._kontraktor("kt_jalanpresisi")
        r = c2.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        self.assertEqual(r.status_code, 404)

    def test_foto_bukti_milik_orang_ditolak(self):
        c2 = self._kontraktor("kt_jalanpresisi")
        r = c2.get(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto")
        self.assertEqual(r.status_code, 404)


class TestTransisiStatus(_Dasar):
    def test_kontraktor_lompat_status_ditolak(self):
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Selesai"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("tidak bisa diubah", r.get_json()["error"])

    def test_urutan_diterima_kerja_selesai(self):
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
            self.assertEqual(r.status_code, 200, s)

    def test_kontraktor_tidak_bisa_membatalkan(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Dibatalkan"})
        self.assertEqual(r.status_code, 400)

    def test_dinas_tidak_bisa_maju_status_spk(self):
        """Dinas hanya boleh membatalkan, bukan menandai pekerjaan kontraktor selesai."""
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        # Endpoint departments tidak punya jalur untuk memaksa SPK Selesai.
        self.assertEqual(
            self.dinas.post(f"/api/kontraktor/spk/{self.spk}/status",
                             json={"status": "Selesai"}).status_code, 403)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Diterima")

    def test_dinas_bisa_membatalkan_spk_aktif(self):
        r = self.dinas.post(f"/api/spk/{self.spk}/batal")
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Dibatalkan")

    def test_status_tidak_dikenal_ditolak(self):
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Ngawur"})
        self.assertEqual(r.status_code, 400)


class TestBuktiFoto(_Dasar):
    def test_tugas_selesai_tanpa_foto_ditolak(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Dikerjakan"})
        c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1", json={"status": "Dikerjakan"})
        r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1", json={"status": "Selesai"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("foto bukti", r.get_json()["error"])

    def test_unggah_lalu_tandai_selesai(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Dikerjakan"})
        c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1", json={"status": "Dikerjakan"})
        r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto",
                   data={"foto": (_jpeg(), "bukti.jpg")},
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        r = c.get(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["Content-Type"], "image/jpeg")
        r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1", json={"status": "Selesai"})
        self.assertEqual(r.status_code, 200, r.get_json())

    def test_dinas_boleh_lihat_foto_bukti(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto",
               data={"foto": (_jpeg(), "bukti.jpg")},
               content_type="multipart/form-data")
        r = self.dinas.get(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto")
        self.assertEqual(r.status_code, 200)

    def test_foto_bukan_gambar_ditolak(self):
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto",
                   data={"foto": (io.BytesIO(b"bukan gambar sama sekali"), "x.jpg")},
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_tugas_milik_spk_lain_ditolak(self):
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/9999", json={"status": "Dikerjakan"})
        self.assertEqual(r.status_code, 404)


class TestPenyelarasanOtomatis(_Dasar):
    def test_spk_selesai_setelah_semua_titik_selesai(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Dikerjakan"})
        for tid in (1, 2):
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}/foto",
                   data={"foto": (_jpeg(), "b.jpg")},
                   content_type="multipart/form-data")
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}", json={"status": "Dikerjakan"})
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}", json={"status": "Selesai"})
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Selesai")
            self.assertIsNotNone(detail_spk(self.spk)["selesai_pada"])

    def test_spk_belum_selesai_saat_satu_titik_tertinggal(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Dikerjakan"})
        c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto",
               data={"foto": (_jpeg(), "b.jpg")},
               content_type="multipart/form-data")
        c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1", json={"status": "Dikerjakan"})
        c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1", json={"status": "Selesai"})
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Dikerjakan")

    def test_statistik_mencerminkan_kondisi(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        with self.app.app_context():
            from database import statistik_spk
            s = statistik_spk(kontraktor_id=1)
        self.assertEqual(s["total"], 1)
        self.assertEqual(s["status"]["Diterima"], 1)
        self.assertEqual(s["n_tugas"], 2)
        self.assertEqual(s["n_tugas_selesai"], 0)


class TestSeedKontraktor(unittest.TestCase):
    def test_seed_membuat_akun(self):
        app = _app()
        with app.app_context():
            from database import daftar_kontraktor, daftar_akun_kontraktor
            daftar_kontraktor(aktif_only=False)
            akun = daftar_akun_kontraktor()
        self.assertGreaterEqual(len(akun), 5)

    def test_kontraktor_nonaktif_tidak_bisa_login(self):
        app = _app()
        c = app.test_client()
        r = c.post("/login", data={"username": "kt_togugede", "password": PASS})
        self.assertEqual(r.status_code, 401)

    def test_sandi_pendek_ditolak(self):
        app = _app()
        with app.app_context():
            from database import set_password_kontraktor
            self.assertFalse(set_password_kontraktor("kt_mitrakarya", "pendek"))
            self.assertTrue(set_password_kontraktor("kt_mitrakarya", "sandi_panjang_kok"))

    def test_simpan_kontraktor_upsert_bukan_duplikat(self):
        app = _app()
        with app.app_context():
            from database import simpan_kontraktor, daftar_kontraktor, kontraktor_by_id
            kid = simpan_kontraktor("KT-001", "CV. Nama Baru", bidang="Uji")
            self.assertEqual(kontraktor_by_id(kid)["nama"], "CV. Nama Baru")
            self.assertEqual(len([k for k in daftar_kontraktor(aktif_only=False)
                                  if k["kode"] == "KT-001"]), 1)

    def test_normalisasi_kode(self):
        from database import normalisasi_kode_kontraktor as n
        self.assertEqual(n("kt 01"), "KT-01")
        self.assertEqual(n("  kt__02 "), "KT-02")
        self.assertEqual(n(""), "KT")
        self.assertEqual(n("!!!"), "KT")


if __name__ == "__main__":
    unittest.main()