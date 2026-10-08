"""Uji endpoint API web/app.py (deterministik: tanpa model, kamera, atau jaringan).

Menutup celah coverage terbesar (web/app.py). Perhatian:
- Kalibrasi POST menulis config/severity.yaml -> di-PATCH agar tidak mengubah berkas.
- Laporan POST menulis PDF sementara -> ditangani route (dihapus sendiri).
"""
import io
import os
import tempfile
import unittest
from unittest import mock

ROWS = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
         "total_rp": 1000, "total_str": "Rp1.000"}]


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():          # seed DB sementara
        from database import (init_instansi, migrasi_disposisi_v2, migrasi_admin_v2,
                              migrasi_sesi_v2, init_admin)
        init_instansi()
        migrasi_disposisi_v2()
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()
    return app


def _login(c):
    from database import AKUN_DEMO
    return c.post("/login", data={"username": AKUN_DEMO[0], "password": AKUN_DEMO[1]})


class TestApiPublik(unittest.TestCase):
    def setUp(self):
        self.c = _app().test_client()

    def test_peta(self):
        r = self.c.get("/api/peta")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.get_json(), list)

    def test_instansi_daftar_dan_terdekat(self):
        self.assertEqual(self.c.get("/api/instansi").status_code, 200)
        r = self.c.get("/api/instansi/terdekat?lat=-6.9175&lon=107.6191")
        self.assertEqual(r.status_code, 200)
        self.assertIn("nama", r.get_json())

    def test_instansi_detail_tidak_ada(self):
        self.assertEqual(self.c.get("/api/instansi/999999").status_code, 404)

    def test_instansi_terdekat_param_salah(self):
        self.assertEqual(self.c.get("/api/instansi/terdekat?lat=x&lon=y").status_code, 400)

    def test_riwayat_daftar_bentuk(self):
        r = self.c.get("/api/riwayat")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        for k in ("data", "overflow", "total_db"):
            self.assertIn(k, j)

    def test_riwayat_detail_dan_gambar_tidak_ada(self):
        self.assertEqual(self.c.get("/api/riwayat/999999").status_code, 404)
        self.assertEqual(self.c.get("/api/riwayat/999999/gambar").status_code, 404)

    def test_disposisi_stats_dan_detail(self):
        r = self.c.get("/api/disposisi/stats?daerah=Bandung&exact=1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("total", r.get_json())
        self.assertEqual(self.c.get("/api/disposisi/999999").status_code, 404)

    def test_kalibrasi_status(self):
        r = self.c.get("/api/kalibrasi")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIn("pixels_per_cm", j)
        self.assertIn("dampak", j)

    def test_verifikasi_tanpa_rows_400(self):
        self.assertEqual(self.c.post("/api/verifikasi", json={"rows": []}).status_code, 400)


class TestApiButuhLogin(unittest.TestCase):
    def setUp(self):
        self.c = _app().test_client()

    def test_endpoint_admin_mengembalikan_401(self):
        self.assertEqual(self.c.post("/api/instansi", json={}).status_code, 401)
        self.assertEqual(self.c.get("/api/admin").status_code, 401)
        self.assertEqual(self.c.post("/api/kalibrasi", json={"pixels_per_cm": 11.0}).status_code, 401)
        self.assertEqual(self.c.put("/api/disposisi/1", json={"status": "Diproses"}).status_code, 401)
        self.assertEqual(self.c.delete("/api/disposisi/1").status_code, 401)


class TestApiSetelahLogin(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.c = self.app.test_client()
        _login(self.c)

    def test_admin_daftar(self):
        r = self.c.get("/api/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.get_json(), list)

    def test_kalibrasi_simpan_dipatch(self):
        palsu = {"pixels_per_cm": 11.0, "metode": "manual", "catatan": "-",
                 "diperbarui": "x"}
        with mock.patch("web.app.simpan_kalibrasi", return_value=palsu):
            r = self.c.post("/api/kalibrasi", json={"pixels_per_cm": 11.0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["pixels_per_cm"], 11.0)

    def test_kalibrasi_nilai_salah_400(self):
        with mock.patch("web.app.hitung_ppc", side_effect=ValueError("panjang tidak valid")):
            r = self.c.post("/api/kalibrasi", json={"panjang_px": 0, "panjang_cm": 0})
        self.assertEqual(r.status_code, 400)

    def test_stream_stats_dan_anotasi(self):
        self.assertEqual(self.c.get("/api/stream/stats").status_code, 200)
        from streaming import MANAGER
        semula = MANAGER.anotasi_aktif
        try:
            r = self.c.post("/api/stream/anotasi")
            self.assertEqual(r.status_code, 200)
            self.assertIn("anotasi", r.get_json())
        finally:
            MANAGER.anotasi_aktif = semula

    def test_stream_snapshot_tanpa_track_400(self):
        self.assertEqual(self.c.post("/api/stream/snapshot").status_code, 400)

    def test_stream_stop(self):
        self.assertEqual(self.c.post("/api/stream/stop").status_code, 200)

    def test_stream_dimiliki_sesi_lain_ditolak(self):
        """Regression: hanya ada SATU StreamManager untuk seluruh server.

        Tanpa token kepemilikan, tab kedua bisa mematikan atau merebut stream
        milik tab pertama. Token hanya wajib saat stream sedang berjalan.
        """
        from streaming import MANAGER
        import web.app as app_mod
        MANAGER.running = True
        holders = []
        try:
            app_mod._stream_token = "TOKEN-PEMILIK"
            # Tanpa token: stop/anotasi/snapshot ditolak, start ditolak 409.
            for path, kode in (("/api/stream/stop", 403),
                               ("/api/stream/anotasi", 403),
                               ("/api/stream/snapshot", 403)):
                r = self.c.post(path, json={})
                self.assertEqual(r.status_code, kode, path)
            r = self.c.post("/api/stream/start",
                            json={"source": "webcam", "target": "0"})
            self.assertEqual(r.status_code, 409)
            # Token salah juga ditolak.
            r = self.c.post("/api/stream/stop", json={"token": "SALAH"})
            self.assertEqual(r.status_code, 403)
            # Pemilik sah boleh menghentikan.
            r = self.c.post("/api/stream/stop", json={"token": "TOKEN-PEMILIK"})
            self.assertEqual(r.status_code, 200)
        finally:
            MANAGER.running = False
            MANAGER.anotasi_aktif = True
            app_mod._stream_token = None

    def test_stream_terbuka_saat_tidak_berjalan(self):
        """Saat tidak ada stream, endpoint tetap terbuka agar idempoten
        dan tidak mengganggu state antarmuka."""
        from streaming import MANAGER
        MANAGER.running = False
        self.assertEqual(self.c.post("/api/stream/stop", json={}).status_code, 200)
        self.assertEqual(self.c.post("/api/stream/anotasi", json={}).status_code, 200)
        self.assertEqual(self.c.post("/api/stream/snapshot", json={}).status_code, 400)

    def test_foto_sesudah_tampil_di_halaman_publik(self):
        """Regression: dinas bisa mengunggah foto perbaikan, tapi halaman
        publik /disposisi/<id> tidak menampilkannya sama sekali."""
        import io
        import pathlib
        import tempfile as _tf
        from PIL import Image
        from database import get_db, migrasi_disposisi_v2

        app = _app()
        with app.app_context():
            get_db()
            migrasi_disposisi_v2()   # tambah kolom foto_sesudah
        c = app.test_client()
        sid = c.post("/api/riwayat", json={
            "sumber": "uji", "lokasi": "Jl Uji", "model": "m",
            "rows": ROWS, "total": 1000, "client_ref": "fs-s",
        }).get_json()["id"]
        did = c.post("/api/disposisi", json={
            "bap_id": sid, "bap_nomor": "BA-FS/1", "lokasi": "Jl Uji",
            "n_temuan": 1, "total_rp": 1000, "worst": "Berat",
            "instansi_id": 0, "instansi_nama": "Dinas Uji",
            "instansi_daerah": "Kabupaten Bogor", "instansi_email": "a@b.c",
            "urgensi": "rutin", "catatan": "uji", "client_ref": "fs-d",
        }).get_json()["id"]

        # Sebelum ada foto: halaman tetap jalan, tanpa <img> yang rusak.
        html = c.get(f"/disposisi/{sid}").get_data(as_text=True)
        self.assertIn("Foto Setelah Penanganan", html)
        self.assertNotIn("/api/disposisi/%d/foto" % did, html)
        self.assertEqual(c.get(f"/api/disposisi/{did}/foto").status_code, 404)

        # Unggah foto lalu pastikan muncul di halaman.
        nama = f"{sid}_sesudah_{did}.jpg"
        buf = io.BytesIO()
        Image.new("RGB", (60, 40), (20, 110, 70)).save(buf, format="JPEG")
        p = pathlib.Path(app.config["DB_PATH"]).parent / "hasil" / nama
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(buf.getvalue())
        with app.app_context():
            db = get_db()
            db.execute("UPDATE disposisi SET foto_sesudah = ? WHERE id = ?", (nama, did))
            db.commit()

        r = c.get(f"/api/disposisi/{did}/foto")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("Content-Type"), "image/jpeg")
        r.close()   # lepas handle file sebelum lanjut (Windows menahan file terbuka)
        html = c.get(f"/disposisi/{sid}").get_data(as_text=True)
        self.assertIn("/api/disposisi/%d/foto" % did, html)
        self.assertIn("TERSEDIA", html)

        # Kolom terisi tapi berkas hilang -> jangan render <img> yang rusak.
        # (Tidak menghapus berkas sungguhan karena Windows menahan handle.)
        hilang = f"{sid}_sesudah_{did}_hilang.jpg"
        with app.app_context():
            db = get_db()
            db.execute("UPDATE disposisi SET foto_sesudah = ? WHERE id = ?",
                       (hilang, did))
            db.commit()
        html = c.get(f"/disposisi/{sid}").get_data(as_text=True)
        self.assertNotIn("/api/disposisi/%d/foto" % did, html)
        self.assertEqual(c.get(f"/api/disposisi/{did}/foto").status_code, 404)

    def test_foto_sesudah_tolak_path_traversal(self):
        """Nama file di kolom DB tidak boleh dipakai untuk keluar dari folder."""
        app = _app()
        with app.app_context():
            from database import get_db, migrasi_disposisi_v2
            get_db()
            migrasi_disposisi_v2()
        c = app.test_client()
        sid = c.post("/api/riwayat", json={
            "sumber": "uji", "lokasi": "Jl", "model": "m",
            "rows": ROWS, "total": 1000, "client_ref": "tr-s",
        }).get_json()["id"]
        did = c.post("/api/disposisi", json={
            "bap_id": sid, "bap_nomor": "BA-TR/1", "lokasi": "Jl",
            "n_temuan": 1, "total_rp": 1000, "worst": "Berat",
            "instansi_id": 0, "instansi_nama": "D", "instansi_daerah": "Kabupaten Bogor",
            "instansi_email": "a@b.c", "urgensi": "rutin", "catatan": "-",
            "client_ref": "tr-d",
        }).get_json()["id"]
        for jahat in ("../../.env", "/etc/hosts", "..\\..\\.env",
                      "sub/dir.jpg", "catatan.txt", "-", ""):
            with app.app_context():
                db = get_db()
                db.execute("UPDATE disposisi SET foto_sesudah = ? WHERE id = ?",
                           (jahat, did))
                db.commit()
            with self.subTest(nama=jahat):
                self.assertEqual(c.get(f"/api/disposisi/{did}/foto").status_code, 404)
        self.assertEqual(c.get("/api/disposisi/999999/foto").status_code, 404)

    def test_laporan_pdf(self):
        r = self.c.post("/api/laporan", json={"rows": ROWS, "total": 1000,
                                              "source": "uji", "model": "m"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["Content-Type"], "application/pdf")
        self.assertEqual(r.get_data()[:5], b"%PDF-")

    def test_laporan_tanpa_rows_400(self):
        self.assertEqual(self.c.post("/api/laporan", json={"rows": []}).status_code, 400)

    def test_logout_redirect(self):
        self.assertEqual(self.c.get("/logout").status_code, 302)


class TestAutentikasiDan404(unittest.TestCase):
    def test_login_salah_401(self):
        c = _app().test_client()
        self.assertEqual(
            c.post("/login", data={"username": "admin", "password": "salah"}).status_code, 401)

    def test_halaman_tidak_ditemukan(self):
        c = _app().test_client()
        self.assertEqual(c.get("/laporan/preview/999999").status_code, 404)
        self.assertEqual(c.get("/disposisi/999999").status_code, 404)

    def test_mobile_dan_kalibrasi_anon(self):
        c = _app().test_client()
        self.assertEqual(c.get("/mobile").status_code, 200)
        self.assertEqual(c.get("/kalibrasi").status_code, 302)  # butuh login


class TestValidasiInput(unittest.TestCase):
    """Jalur validasi (400) — murah, deterministik, dan mengunci perilaku."""

    def setUp(self):
        self.app = _app()
        self.c = self.app.test_client()
        _login(self.c)

    def test_detect_tanpa_berkas_400(self):
        self.assertEqual(self.c.post("/api/detect", data={}).status_code, 400)

    def test_detect_format_salah_400(self):
        r = self.c.post("/api/detect", data={"gambar": (io.BytesIO(b"xx"), "a.txt")},
                        content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_kalibrasi_foto_tanpa_berkas_400(self):
        self.assertEqual(self.c.post("/api/kalibrasi/foto", data={}).status_code, 400)

    def test_video_tanpa_berkas_400(self):
        self.assertEqual(self.c.post("/api/video", data={}).status_code, 400)

    def test_stream_start_sumber_salah_400(self):
        self.assertEqual(
            self.c.post("/api/stream/start", json={"source": "xyz"}).status_code, 400)

    def test_stream_start_ipcam_localhost_400(self):
        r = self.c.post("/api/stream/start",
                        json={"source": "ipcam", "target": "http://localhost:8080/x"})
        self.assertEqual(r.status_code, 400)

    def test_stream_start_webcam_idx_bukan_angka_400(self):
        r = self.c.post("/api/stream/start",
                        json={"source": "webcam", "target": "bukan-angka"})
        self.assertEqual(r.status_code, 400)

    def test_riwayat_koordinat_luar_rentang_400(self):
        r = self.c.post("/api/riwayat", json={"rows": ROWS, "total": 1, "lat": 999, "lon": 0})
        self.assertEqual(r.status_code, 400)

    def test_disposisi_field_kurang_400(self):
        self.assertEqual(self.c.post("/api/disposisi", json={"bap_id": 1}).status_code, 400)

    def test_admin_sandi_terlalu_pendek_400(self):
        r = self.c.post("/api/admin/sandi", json={"username": "admin", "sandi_baru": "x"})
        self.assertEqual(r.status_code, 400)

    def test_instansi_field_kurang_400(self):
        self.assertEqual(self.c.post("/api/instansi", json={"nama": "X"}).status_code, 400)

    def test_disposisi_daftar_hormati_limit(self):
        """Regresi: ?limit= pernah DIABAIKAN, sehingga cek overflow
        (rows.length > 200) di dashboard selalu false."""
        app = _app()
        c = app.test_client()
        for i in range(4):
            sid = c.post("/api/riwayat", json={
                "sumber": "uji", "lokasi": "Jl", "model": "m",
                "rows": ROWS, "total": 1000, "client_ref": f"lim-s{i}",
            }).get_json()["id"]
            c.post("/api/disposisi", json={
                "bap_id": sid, "bap_nomor": f"B{i}", "lokasi": "Jl",
                "n_temuan": 1, "total_rp": 1000, "worst": "Berat",
                "instansi_id": 0, "instansi_nama": "D",
                "instansi_daerah": "Kabupaten Bogor", "instansi_email": "a@b.c",
                "urgensi": "kritis", "catatan": "-", "client_ref": f"lim-d{i}",
            })
        base = "/api/disposisi?daerah=bogor"
        self.assertEqual(len(c.get(base).get_json()), 4)
        self.assertEqual(len(c.get(base + "&limit=2").get_json()), 2)
        self.assertEqual(len(c.get(base + "&limit=201").get_json()), 4)
        # Nilai aneh tidak boleh melempar exception.
        self.assertEqual(len(c.get(base + "&limit=abc").get_json()), 4)
        # Nilai negatif dijepit ke 1, bukan error 500.
        self.assertEqual(len(c.get(base + "&limit=-5").get_json()), 1)

    def test_urgensi_disimpan_kapital(self):
        """Regresi: form mengirim lowercase, konsumen membandingkan kapital."""
        app = _app()
        c = app.test_client()
        sid = c.post("/api/riwayat", json={
            "sumber": "uji", "lokasi": "Jl", "model": "m",
            "rows": ROWS, "total": 1000, "client_ref": "urg-s",
        }).get_json()["id"]
        r = c.post("/api/disposisi", json={
            "bap_id": sid, "bap_nomor": "BU", "lokasi": "Jl",
            "n_temuan": 1, "total_rp": 1000, "worst": "Berat",
            "instansi_id": 0, "instansi_nama": "D",
            "instansi_daerah": "Kabupaten Bogor", "instansi_email": "a@b.c",
            "urgensi": "kritis", "catatan": "-", "client_ref": "urg-d",
        })
        self.assertEqual(r.status_code, 200, r.get_json())
        did = r.get_json()["id"]
        from database import detail_disposisi
        with app.app_context():
            self.assertEqual(detail_disposisi(did)["urgensi"], "Kritis")
        # Filter kapital harus menemukan baris lowercase yang sudah disimpan.
        self.assertEqual(len(c.get("/api/disposisi?daerah=bogor&urgensi=Kritis").get_json()), 1)
        self.assertEqual(len(c.get("/api/disposisi?daerah=bogor&urgensi=kritis").get_json()), 1)


if __name__ == "__main__":
    unittest.main()
