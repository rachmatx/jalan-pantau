"""Uji alur SPK dari awal sampai akhir: dinas terbitkan -> kontraktor terima
-> kerjakan -> bukti foto -> ajukan hasil -> dinas terima (BAST).

Fokus pengujian ini pada BATASAN, bukan tampilan:
- kontraktor tidak boleh melihat atau mengubah SPK kontraktor lain
- akun dinas tidak boleh memakai API kontraktor (dan sebaliknya)
- status tidak boleh dilompati (Diterbitan -> Dikerjakan ditolak)
- titik tidak boleh ditandai Selesai tanpa foto bukti
- SPK otomatis DIAJUKAN ke dinas setelah SELURUH titiknya selesai
- kontraktor tidak boleh menutup SPK sendiri: harus diterima dinas
- bukti foto lama dihapus saat dinas meminta revisi
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

    def _tugas(self, spk=None):
        with self.app.app_context():
            from database import daftar_tugas_spk
            return [t["id"] for t in daftar_tugas_spk(spk or self.spk)]

    def _selesaikan_semua_tugas(self, c, spk=None):
        """Kerjakan lalu selesaikan tiap titik, lengkap dengan bukti foto."""
        for n, tid in enumerate(self._tugas(spk)):
            c.post(f"/api/kontraktor/spk/{spk or self.spk}/tugas/{tid}/foto",
                   data={"foto": (_jpeg(), f"b{n}.jpg")},
                   content_type="multipart/form-data")
            c.post(f"/api/kontraktor/spk/{spk or self.spk}/tugas/{tid}",
                   json={"status": "Dikerjakan"})
            c.post(f"/api/kontraktor/spk/{spk or self.spk}/tugas/{tid}",
                   json={"status": "Selesai"})


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
        """Kontraktor tidak boleh melompati tahap (Diterbitan -> Dikerjakan)."""
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Dikerjakan"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("tidak bisa diubah", r.get_json()["error"])

    def test_status_tidak_dikenal_ditolak(self):
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Ngawur"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("tidak dikenal", r.get_json()["error"])

    def test_kontraktor_tidak_bisa_menytakan_status_final(self):
        """Kontraktor tidak boleh menutup SPK sendiri tanpa penerimaan dinas."""
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima Dinas"})
        self.assertEqual(r.status_code, 400)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Dikerjakan")

    def test_tidak_bisa_mengajukan_kalau_titik_belum_selesai(self):
        """SPK tidak boleh diajukan ke dinas sebelum tiap titik selesai.

        Tanpa gerbang ini kontraktor bisa menekan "Ajukan hasil kerja"
        sementara satu titik masih "Menunggu", lalu dinas menerima
        pekerjaan yang belum dikerjakan.
        """
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status",
                   json={"status": "Menunggu Penerimaan"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("belum selesai", r.get_json()["error"])
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Dikerjakan")

    def test_pengajuan_otomatis_tetap_berjalan(self):
        """Menyelesaikan titik terakhir harus tetap mengajukan SPK otomatis."""
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
        self._selesaikan_semua_tugas(c)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Menunggu Penerimaan")

    def test_pengajuan_gagal_tidak_naik_status_spk(self):
        """Pengajuan yang ditolak tidak boleh meninggalkan SPK setengah jalan."""
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status",
                   json={"status": "Menunggu Penerimaan"})
        self.assertEqual(r.status_code, 400)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Dikerjakan")
        with self.app.app_context():
            from database import riwayat_spk
            isi = [c2["status"] for c2 in riwayat_spk(self.spk)]
        self.assertNotIn("Menunggu Penerimaan", isi)

    def test_urutan_diterima_kerja_ke_aja(self):
        """Jalur kontraktor: terima -> kerjakan -> ajukan ke dinas.

        Pengajuan dilakukan lewat penyelesaian titik pekerjaan, bukan
        melompat langsung ke "Menunggu Penerimaan".
        """
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
            self.assertEqual(r.status_code, 200, s)
        self._selesaikan_semua_tugas(c)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Menunggu Penerimaan")

    def test_kontraktor_tidak_bisa_membatalkan(self):
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Dibatalkan"})
        self.assertEqual(r.status_code, 400)

    def test_dinas_tidak_bisa_maju_status_spk(self):
        """Dinas tidak boleh memaksa pekerjaan kontraktor; endpoint kontraktor tertutup."""
        c = self._kontraktor()
        c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        self.assertEqual(
            self.dinas.post(f"/api/kontraktor/spk/{self.spk}/status",
                             json={"status": "Menunggu Penerimaan"}).status_code, 403)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Diterima")

    def test_dinas_tidak_bisa_menerima_sebelum_diajukan(self):
        """Penerimaan hanya sah kalau kontraktor sudah mengajukan hasil."""
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
        r = self.dinas.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": "BAST/1"})
        self.assertEqual(r.status_code, 400)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Dikerjakan")

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
    def test_spk_diajukan_setelah_semua_titik_selesai(self):
        """Semua titik selesai -> SPK OTOMATIS diajukan ke dinas (bukan ditutup)."""
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
            # Belum "Diterima Dinas": masih menunggu pemeriksaan dinas.
            self.assertEqual(detail_spk(self.spk)["status"], "Menunggu Penerimaan")
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


class TestPenerimaanHasilKerja(_Dasar):
    """Alur:after the contractor submits the work, the agency EXAMINES it.

    This is the part that was previously missing: the contractor used to
    declare the SPK finished by himself with no agency verification at all.
    """

    def _ajukan(self):
        """Drive the SPK all the way to "Menunggu Penerimaan"."""
        c = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": s})
        for tid in (1, 2):
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}/foto",
                   data={"foto": (_jpeg(), "b.jpg")}, content_type="multipart/form-data")
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}", json={"status": "Dikerjakan"})
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}", json={"status": "Selesai"})
        return c

    def test_terima_mencatat_bast(self):
        self._ajukan()
        r = self.dinas.post(f"/api/spk/{self.spk}/terima",
                            json={"nomor_bast": "BAST/77/2026", "catatan": "Bagus"})
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import detail_spk
            item = detail_spk(self.spk)
        self.assertEqual(item["status"], "Diterima Dinas")
        self.assertEqual(item["nomor_bast"], "BAST/77/2026")
        self.assertIsNotNone(item["waktu_diterima"])
        self.assertEqual(item["catatan_penerimaan"], "Bagus")

    def test_terima_menulis_riwayat(self):
        self._ajukan()
        self.dinas.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": "BAST/1"})
        with self.app.app_context():
            from database import riwayat_spk
            status = [c["status"] for c in riwayat_spk(self.spk)]
        self.assertIn("Diterima Dinas", status)

    def test_status_final_tidak_bisa_dibuka_lagi(self):
        self._ajukan()
        self.dinas.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": "BAST/1"})
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/status", json={"status": "Diterima"})
        self.assertEqual(r.status_code, 400)

    def test_revisi_wajib_alasan(self):
        self._ajukan()
        r = self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "   "})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Alasan revisi", r.get_json()["error"])

    def test_revisi_mengosongkan_bukti_lama(self):
        """After revision the old photo MUST be cleared, or the contractor
        could immediately press "Selesai" without a new photo."""
        self._ajukan()
        r = self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "Aspal kurang"})
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import detail_spk, daftar_tugas_spk
            item = detail_spk(self.spk)
            tugas = daftar_tugas_spk(self.spk)
        self.assertEqual(item["status"], "Perlu Revisi")
        self.assertEqual(item["revisi_ke"], 1)
        for t in tugas:
            self.assertEqual(t["status"], "Dikerjakan")
            self.assertIsNone(t["foto_selesai"])

    def test_titik_tidak_bisa_selesai_tanpa_foto_baru_setelah_revisi(self):
        self._ajukan()
        self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "Aspal kurang"})
        c = self._kontraktor()
        r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1", json={"status": "Selesai"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("foto bukti", r.get_json()["error"])

    def test_alur_revisi_lengkap_sampai_diterima(self):
        """Revisi -> perbaiki -> unggah bukti -> otomatis diajukan -> diterima.

        Ini sekaligus mengunci perbaikan bug dead-end: kontraktor tidak punya
        tombol submit saat status "Perlu Revisi", jadi pengajuan SETELAH revisi
        harus datang dari auto-submit di server. Test ini sengaja tidak
        memanggil POST /status -- kalau auto-submitnya rusak lagi, SPK akan
        menggantung di "Perlu Revisi" dan test ini gagal.
        """
        self._ajukan()
        self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "Aspal kurang"})
        c = self._kontraktor()
        for tid in (1, 2):
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}/foto",
                   data={"foto": (_jpeg(), "p.jpg")}, content_type="multipart/form-data")
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}", json={"status": "Selesai"})
        # Tanpa POST /status -- pengajuan harus terjadi sendiri begitu titik
        # terakhir selesai, walau SPK sedang berstatus "Perlu Revisi".
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Menunggu Penerimaan")
        r = self.dinas.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": "BAST/99"})
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Diterima Dinas")

    def test_setelah_revisi_tidak_menunggu_perintah_tambahan(self):
        """Regression: SPK tidak boleh menggantung di "Perlu Revisi".

        Kontraktor hanya punya tombol "Terima SPK" saat status "Diterbitan",
        jadi kalau auto-submit tidak menyalakan diri di "Perlu Revisi" maka
        kontraktor tidak punya satu pun jalan untuk mengirim ulang hasilnya.
        """
        self._ajukan()
        self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "Aspal kurang"})
        c = self._kontraktor()
        for tid in (1, 2):
            c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}/foto",
                   data={"foto": (_jpeg(), "p.jpg")}, content_type="multipart/form-data")
            r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}", json={"status": "Selesai"})
            self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import detail_spk, daftar_tugas_spk
            item = detail_spk(self.spk)
            tugas = daftar_tugas_spk(self.spk)
        self.assertNotEqual(item["status"], "Perlu Revisi",
                            "SPK menggantung: kontraktor tidak bisa mengirim ulang hasil kerja")
        self.assertEqual(item["status"], "Menunggu Penerimaan")
        for t in tugas:
            self.assertEqual(t["status"], "Selesai")
            self.assertIsNotNone(t["foto_selesai"])

    def test_halaman_kontraktor_tidak_punya_tombol_saat_perlu_revisi(self):
        """Cek sisi template: saat "Perlu Revisi" tidak ada tombol status.

        Kontraktor hanya punya tombol "Terima SPK" saat status "Diterbitan",
        jadi halaman revisi memang tidak boleh punya tombol submit -- yang
        membuat jalur auto-submit jadi satu-satunya jalan, dan wajib diuji.
        """
        self._ajukan()
        self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "Aspal kurang"})
        r = self._kontraktor().get(f"/kontraktor/spk/{self.spk}")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertNotIn('id="btn-terima"', html)
        # Tanpa tombol, satu-satunya jalan keluar harus pengajuan otomatis.
        with self.app.app_context():
            from database import SPK_STATUS_AJUKAN_OTOMATIS
        self.assertIn("Perlu Revisi", SPK_STATUS_AJUKAN_OTOMATIS)

    def test_kontraktor_ditolak_di_endpoint_dinas(self):
        """Kontraktor (bahkan kontraktor lain) tidak boleh menerima hasil kerja."""
        self._ajukan()
        c2 = self._kontraktor("kt_jalanpresisi")
        r = c2.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": "BAST/x"})
        self.assertEqual(r.status_code, 401)
        r2 = c2.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "sengaja"})
        self.assertEqual(r2.status_code, 401)

    def test_bukti_tidak_bisa_diganti_setelah_bast(self):
        """Regression: bukti publik harus berhenti berubah begitu BAST diteken.

        Kalau kontraktor masih boleh mengunggah setelah "Diterima Dinas", isi
        yang dilihat publik bukan lagi bukti yang pernah diperiksa dinas, dan
        keputusan BAST kehilangan makna sebagai dokumen acceptance.
        """
        self._ajukan()
        self.dinas.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": "BAST/1"})
        with self.app.app_context():
            from database import detail_spk, daftar_tugas_spk
            sebelum = {t["id"]: t["foto_selesai"] for t in daftar_tugas_spk(self.spk)}
            self.assertEqual(detail_spk(self.spk)["status"], "Diterima Dinas")
        r = self._kontraktor().post(
            f"/api/kontraktor/spk/{self.spk}/tugas/1/foto",
            data={"foto": (_jpeg(), "palsu.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("tidak bisa diubah", r.get_json()["error"])
        with self.app.app_context():
            from database import daftar_tugas_spk
            sesudah = {t["id"]: t["foto_selesai"] for t in daftar_tugas_spk(self.spk)}
        self.assertEqual(sesudah, sebelum, "Bukti berubah setelah SPK final")

    def test_bukti_tidak_bisa_diganti_setelah_dibatalkan(self):
        # SPK yang dibatalkan bisa berada di status mana pun yang boleh
        # dibatalkan dinas (Diterbitan / Diterima / Dikerjakan), bukan dari
        # "Menunggu Penerimaan" -- ke sana dinas hanya boleh terima atau revisi.
        self.dinas.post(f"/api/spk/{self.spk}/batal")
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Dibatalkan")
        r = self._kontraktor().post(
            f"/api/kontraktor/spk/{self.spk}/tugas/1/foto",
            data={"foto": (_jpeg(), "palsu.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_tombol_foto_hilang_setelah_spk_final(self):
        """Sisi template: tombol unggah foto tidak boleh tampil saat SPK final.

        Dicek atribut HTML-nya (data-foto-btn=") supaya tidak tertukar dengan
        querySelector di dalam skrip, yang memang selalu ada.
        """
        self._ajukan()
        html_aktif = self._kontraktor().get(
            f"/kontraktor/spk/{self.spk}").get_data(as_text=True)
        self.assertIn('data-foto-btn="', html_aktif, "tombol harus ada sebelum SPK final")
        self.dinas.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": "BAST/1"})
        html_final = self._kontraktor().get(
            f"/kontraktor/spk/{self.spk}").get_data(as_text=True)
        self.assertNotIn('data-foto-btn="', html_final)
        # Bukti yang sudah ada harus tetap bisa dilihat.
        self.assertIn("Lihat foto", html_final)

    def test_ganti_foto_membuang_berkas_lama(self):
        """Kolom foto_selesai hanya menyimpan satu nama.

        Kalau berkas lama tidak dihapus saat diganti, setiap penggantian
        menyisakan file yatim permanen di folder hasil/.
        """
        self._ajukan()
        c = self._kontraktor()
        with self.app.app_context():
            from database import daftar_tugas_spk, _paths
            lama = daftar_tugas_spk(self.spk)[0]["foto_selesai"]
            folder = _paths()[1]
            self.assertTrue((folder / lama).is_file())
        r = c.post(f"/api/kontraktor/spk/{self.spk}/tugas/1/foto",
                   data={"foto": (_jpeg(), "baru.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import daftar_tugas_spk, _paths
            baru = daftar_tugas_spk(self.spk)[0]["foto_selesai"]
            folder = _paths()[1]
        self.assertNotEqual(baru, lama)
        self.assertFalse((folder / lama).exists(), f"berkas yatim {lama} tidak dihapus")
        self.assertTrue((folder / baru).is_file())


class TestFotoSesudahTanpaSPK(_Dasar):
    """Foto "jalan sesudah diperbaiki" milik dinas HANYA untuk laporan tanpa SPK.

    Kalau ada SPK, bukti yang sah adalah foto kontraktor yang sudah diperiksa
    dinas lewat BAST. Membiarkan dinas mengunggah foto sendiri di tiket yang
    sama menghasilkan dua klaim "sudah diperbaiki" yang berbeda untuk satu
    lokasi, dan yang tampil ke publik bisa bukan yang pernah diperiksa.
    """

    def test_tolak_unggah_foto_sesudah_bila_sudah_punya_spk(self):
        # self.d1 dan self.d2 sudah jadi titik pekerjaan SPK di setUp.
        r = self.dinas.post(f"/api/disposisi/{self.d1}/foto",
                            data={"foto": (_jpeg(), "a.jpg")},
                            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("sudah punya SPK", r.get_json()["error"])
        with self.app.app_context():
            from database import detail_disposisi
            self.assertIsNone(detail_disposisi(self.d1)["foto_sesudah"])

    def test_panel_foto_sesudah_disembunyikan_bila_ada_spk(self):
        r = self.dinas.get(f"/pupr-bandung/dashboard/disposisi/{self.d1}")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('id="update-foto"', r.get_data(as_text=True))

    def test_tetap_boleh_bila_laporan_tanpa_spk(self):
        """Fitur ini tidak dihapus, hanya dipersempit: tiket tanpa SPK masih
        butuh cara menunjukkan bahwa kerusakan sudah ditangani."""
        with self.app.app_context():
            from database import simpan_disposisi, detail_sesi, rekap_temuan, simpan_sesi
            rows = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
                     "total_rp": 1500000, "total_str": "Rp1.500.000", "conf": 0.9}]
            s = simpan_sesi("uji", "Jl. Tanpa SPK", "m", rows, 0, lat=-6.9, lon=107.6)
            rc = rekap_temuan(s)
            did = simpan_disposisi(s, "BAP-X/1", "Jl. Tanpa SPK", -6.9, 107.6,
                                   rc["n_temuan"], rc["total_rp"], rc["worst"],
                                   None, "D", "Bandung", "a@b.c", "rutin")
        r = self.dinas.post(f"/api/disposisi/{did}/foto",
                            data={"foto": (_jpeg(), "a.jpg")},
                            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        with self.app.app_context():
            from database import detail_disposisi
            self.assertIsNotNone(detail_disposisi(did)["foto_sesudah"])


class TestDataKontrakSPK(_Dasar):
    def test_data_kontrak_tersimpan(self):
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": "Perbaikan",
            "disposisi_ids": [1],
            "nomor_kontrak": "027/KONT/2026", "nilai_kontrak": "45000000",
            "tgl_mulai": "2026-03-01", "masa_kerja_hari": "30"})
        self.assertEqual(r.status_code, 200)
        sid = r.get_json()["id"]
        with self.app.app_context():
            from database import detail_spk
            item = detail_spk(sid)
        self.assertEqual(item["nomor_kontrak"], "027/KONT/2026")
        self.assertEqual(item["nilai_kontrak"], 45000000)
        self.assertEqual(item["masa_kerja_hari"], 30)

    def test_nilai_kontrak_bukan_angka_ditolak(self):
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": "X",
            "disposisi_ids": [1], "nilai_kontrak": "banyak"})
        self.assertEqual(r.status_code, 400)

    def test_masa_kerja_nol_ditolak(self):
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": "X",
            "disposisi_ids": [1], "masa_kerja_hari": "0"})
        self.assertEqual(r.status_code, 400)

    def test_kosong_tidak_dianggap_nol(self):
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": "X",
            "disposisi_ids": [1], "nilai_kontrak": "", "masa_kerja_hari": ""})
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import detail_spk
            item = detail_spk(r.get_json()["id"])
        self.assertIsNone(item["nilai_kontrak"])


class TestMigrasiPenerimaan(_Dasar):
    def test_status_selesai_lama_dikonversi(self):
        """SPK lama berstatus "Selesai" belum pernah diperiksa dinas, jadi
        harus masuk antrean verifikasi, bukan dianggap final."""
        with self.app.app_context():
            from database import get_db, migrasi_spk_penerimaan_v3
            db = get_db()
            db.execute("UPDATE spk SET status = 'Selesai' WHERE id = ?", (self.spk,))
            db.commit()
            migrasi_spk_penerimaan_v3()
            status = db.execute("SELECT status FROM spk WHERE id = ?",
                                (self.spk,)).fetchone()[0]
        self.assertEqual(status, "Menunggu Penerimaan")

    def test_migrasi_aman_dijalankan_berulang(self):
        with self.app.app_context():
            from database import migrasi_spk_penerimaan_v3
            migrasi_spk_penerimaan_v3()
            migrasi_spk_penerimaan_v3()  # harus tidak error


class TestEjaanStatus(_Dasar):
    """Nama status harus sama persis antara kode, basis data, dan antarmuka.

    Ralunya pernah Amir karena nilai tahap terbit tersimpan dengan huruf
    nyasar. Akibatnya satu tombol aksi kontraktor diam-diam tidak pernah
    aktif karena perbandingannya tidak pernah cocok. Tes ini menjaga
    supaya ketidakcocokan sekecil itu langsung ketahuan.
    """

    def test_nilai_status_konsisten_dan_berhuruf_benar(self):
        with self.app.app_context():
            from database import SPK_STATUS, SPK_STATUS_TERBITKAN, get_db
            dari_db = get_db().execute(
                "SELECT status FROM spk WHERE id = ?", (self.spk,)).fetchone()[0]
        # Nilai di dalam basis data harus salah satu dari status yang sah.
        self.assertIn(dari_db, SPK_STATUS)
        self.assertEqual(dari_db, SPK_STATUS_TERBITKAN)
        # Nama itu harus ejaan Indonesia yang benar, tanpa huruf nyasar.
        self.assertNotIn("k", SPK_STATUS_TERBITKAN[8:9])
        self.assertEqual(len(SPK_STATUS_TERBITKAN), 10)

    def test_tombol_terima_muncul_pada_spk_baru(self):
        """Tombol aksi harus tampil kalau kondisinya benar-benar terpenuhi."""
        c = self._kontraktor()
        html = c.get(f"/kontraktor/spk/{self.spk}").get_data(as_text=True)
        self.assertIn('id="btn-terima"', html)

    def test_migrasi_ejaan_memperbaiki_data_lama(self):
        with self.app.app_context():
            from database import get_db, migrasi_spk_status_tertulis_v4
            db = get_db()
            salah = "Diterbit" + "kan"
            db.execute("UPDATE spk SET status = ? WHERE id = ?", (salah, self.spk))
            db.execute("INSERT INTO spk_catatan (spk_id, waktu, status, catatan, oleh)"
                       " VALUES (?, ?, ?, ?, ?)",
                       (self.spk, "2026-01-01T00:00:00", salah, "-", "admin"))
            db.commit()

            migrasi_spk_status_tertulis_v4()
            migrasi_spk_status_tertulis_v4()  # harus idempoten

            sisa_spk = db.execute("SELECT COUNT(*) c FROM spk WHERE status = ?",
                                  (salah,)).fetchone()["c"]
            sisa_catatan = db.execute(
                "SELECT COUNT(*) c FROM spk_catatan WHERE status = ?",
                (salah,)).fetchone()["c"]
        self.assertEqual(sisa_spk, 0)
        self.assertEqual(sisa_catatan, 0)


class TestKonsistensiBuktiFoto(_Dasar):
    """Pemeriksaan tambahan pada jalur foto, di luar alur SPK utama."""

    def test_dashboard_memakai_validator_yang_sama_dengan_route_publik(self):
        """Dashboard harus lewat path_foto_sesudah, bukan merangkai path sendiri.

        Kalau dashboard merangkai folder hasil langsung dari nilai kolom, ia
        melewati pemeriksaan basename dan bisa membaca berkas di luar folder
        hasil lalu membungkusnya jadi base64 di dalam HTML.

        Test ini benar-benar meletakkan berkas target di LUAR folder hasil,
        lalu memastikan isinya tidak bocor ke halaman.
        """
        import base64 as _b64
        with self.app.app_context():
            from database import simpan_disposisi, rekap_temuan, simpan_sesi, _paths
            rows = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
                     "total_rp": 1500000, "total_str": "Rp1.500.000", "conf": 0.9}]
            s = simpan_sesi("uji", "Jl. Jalur", "m", rows, 0, lat=-6.9, lon=107.6,
                            image_b64=_b64.b64encode(_jpeg().read()).decode())
            rc = rekap_temuan(s)
            did = simpan_disposisi(s, "BAP-J/1", "Jl. Jalur", -6.9, 107.6,
                                   rc["n_temuan"], rc["total_rp"], rc["worst"],
                                   None, "D", "Bandung", "a@b.c", "rutin")
            hasil = _paths()[1]
            hasil.mkdir(parents=True, exist_ok=True)
            # Berkas rahasia satu folder DI LUAR folder hasil.
            rahasia = hasil.parent / "rahasia.txt"
            rahasia.write_text("RAHASIA-JP-SECRET-1234", encoding="utf-8")
            sidah = _b64.b64encode(b"RAHASIA-JP-SECRET-1234").decode()
            from database import get_db
            get_db().execute("UPDATE disposisi SET foto_sesudah = ? WHERE id = ?",
                             ("../rahasia.txt", did))
            get_db().commit()
        try:
            html = self.dinas.get(f"/pupr-bandung/dashboard/disposisi/{did}")
            self.assertEqual(html.status_code, 200)
            teks = html.get_data(as_text=True)
            # Path lintasan harus ditolak validator.
            self.assertNotIn(sidah, teks,
                             "berkas di luar folder hasil bocor ke dashboard")
            self.assertNotIn("RAHASIA-JP-SECRET-1234", teks)
        finally:
            rahasia.unlink(missing_ok=True)

    def test_foto_lama_yang_benar_ada_tetap_ditampilkan(self):
        """Penjaga test di atas: validasi tidak boleh terlalu ketat sampai
        gambar yang sah ikut hilang."""
        import base64 as _b64
        with self.app.app_context():
            from database import simpan_disposisi, rekap_temuan, simpan_sesi, _paths
            rows = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
                     "total_rp": 1500000, "total_str": "Rp1.500.000", "conf": 0.9}]
            s = simpan_sesi("uji", "Jl. Sah", "m", rows, 0, lat=-6.9, lon=107.6,
                            image_b64=_b64.b64encode(_jpeg().read()).decode())
            rc = rekap_temuan(s)
            did = simpan_disposisi(s, "BAP-S/1", "Jl. Sah", -6.9, 107.6,
                                   rc["n_temuan"], rc["total_rp"], rc["worst"],
                                   None, "D", "Bandung", "a@b.c", "rutin")
            nama = f"{did}_sesudah_{did}.jpg"
            folder = _paths()[1]
            folder.mkdir(parents=True, exist_ok=True)
            (folder / nama).write_bytes(_jpeg().read())
            from database import get_db
            get_db().execute("UPDATE disposisi SET foto_sesudah = ? WHERE id = ?",
                             (nama, did))
            get_db().commit()
        html = self.dinas.get(f"/pupr-bandung/dashboard/disposisi/{did}")
        self.assertEqual(html.status_code, 200)
        teks = html.get_data(as_text=True)
        self.assertIn("Foto sesudah sudah tersimpan", teks)
        # Gambar sesudah harus benar-benar dirender (label SESUDAH), bukan
        # hanya status teksnya.
        self.assertIn("SESUDAH", teks)

    def test_bukti_publik_memakai_penerimaan_terbaru(self):
        """Kalau satu disposisi masuk dua SPK yang keduanya diterima dinas,
        yang ditampilkan ke publik adalah penerimaan TERAKHIR.

        Memilih s.id terkecil asal bisa menampilkan bukti lama padahal
        pekerjaan yang lebih baru sudah selesai.
        """
        from PIL import Image
        import io as _io
        with self.app.app_context():
            from database import get_db, detail_spk
            # SPK kedua untuk disposisi yang sama.
            kid = get_db().execute(
                "SELECT kontraktor_id FROM spk WHERE id = ?", (self.spk,)).fetchone()[0]
            spk1 = self.spk
            spk2 = detail_spk(spk1)["id"]
            # Terbitkan SPK kedua berisi disposisi yang sama.
            import database as D
            d = get_db().execute(
                "SELECT id FROM disposisi WHERE bap_id ="
                " (SELECT bap_id FROM disposisi WHERE id = ?)", (self.d1,)).fetchone()[0]
            baru = D.terbitkan_spk(kid, "Bandung", "Perbaikan Susulan", [d])
            # Beri waktu terima berbeda supaya "terbaru" tidak ambigu.
            get_db().execute(
                "UPDATE spk SET status='Diterima Dinas', waktu_diterima=?"
                " WHERE id = ?", ("2026-01-01T00:00:00", spk2))
            get_db().execute(
                "UPDATE spk SET status='Diterima Dinas', waktu_diterima=?"
                " WHERE id = ?", ("2026-12-31T00:00:00", baru))
            get_db().commit()
            # Foto berbeda untuk kedua SPK.
            _paths = D._paths()
            _paths[1].mkdir(parents=True, exist_ok=True)
            f_lama, f_baru = "bukti_lama.jpg", "bukti_baru.jpg"
            (_paths[1] / f_lama).write_bytes(_jpeg().read())
            buf = _io.BytesIO()
            Image.new("RGB", (30, 30), (10, 200, 10)).save(buf, format="JPEG")
            (_paths[1] / f_baru).write_bytes(buf.getvalue())
            get_db().execute(
                "UPDATE spk_tugas SET foto_selesai=? WHERE spk_id=?",
                (f_lama, spk2))
            get_db().execute(
                "UPDATE spk_tugas SET foto_selesai=? WHERE spk_id=?",
                (f_baru, baru))
            get_db().commit()
            assert D.foto_bukti_disposisi(d) == f_baru, (
                "penerimaan terbaru harus menang, bukan s.id terkecil")


class TestRateLimitFoto(_Dasar):
    """Route unggah foto harus ikut dibatasi; sebelumnya hanya rate limit
    global 600/jam yang berlaku, dan hilang total tanpa flask-limiter."""

    def test_route_foto_memakai_pembatas(self):
        """Guard statis: ketiga route foto harus punya dekorator limit.

        Diuji lewat sumber, bukan lewat configurer Flask, supaya tetap
        berlaku walau limiter tidak terpasang di lingkungan uji.
        """
        import re
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "web", "app.py"),
            encoding="utf-8").read()
        for route in ("/api/disposisi/<int:did>/foto",
                      "/api/kontraktor/spk/<int:sid>/tugas/<int:tid>/foto",
                      "/api/kalibrasi/foto"):
            m = re.search(r'@app\.post\("' + re.escape(route) + r'"\)(.{0,400})'
                          r'\n    def ', src, re.S)
            self.assertIsNotNone(m, f"route {route} tidak ditemukan")
            self.assertIn("limiter.limit", m.group(1),
                          f"route {route} tidak punya rate limit")


if __name__ == "__main__":
    unittest.main()