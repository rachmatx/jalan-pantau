"""Regresi: hapus riwayat kena 429 terlalu cepat + pesan tanpa waktu tunggu.

Laporan lapangan: DELETE /api/riwayat/53 terus 429 setelah beberapa hapusan.
Batas lama 10/jam dihitung per endpoint termasuk hapusan baris yang sudah
tidak ada (404), jadi bersih-bersih 10 riwayat mengunci admin selama 1 jam
tanpa penjelasan. API 429 juga tidak mengirim Retry-After.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        from database import migrasi_admin_v2, migrasi_sesi_v2, init_admin
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()
    return app


class TestBatasHapusRiwayat(unittest.TestCase):
    def setUp(self):
        self.c = _app().test_client()
        with self.c.session_transaction() as s:
            s["admin_id"] = 1
            s["admin_user"] = "admin"
            s["login_at"] = time.time()

    def test_lima_belas_hapusan_tidak_kena_429(self):
        kode = [self.c.delete("/api/riwayat/%d" % (1000 + i)).status_code
                for i in range(15)]
        self.assertNotIn(429, kode,
                         "bersih-bersih 15 riwayat tidak boleh langsung diblokir")

    def test_429_api_memberi_waktu_tunggu(self):
        for i in range(35):
            r = self.c.delete("/api/riwayat/%d" % (2000 + i))
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)
        self.assertGreaterEqual(int(r.headers["Retry-After"]), 1)
        pesan = r.get_json().get("error", "")
        self.assertRegex(pesan, r"\d+\s*(menit|detik)")


class TestPesanGagalHapusFrontend(unittest.TestCase):
    def test_toast_memakai_pesan_server(self):
        js = (AKAR / "web" / "static" / "js" / "riwayat.js").read_text(encoding="utf-8")
        awal = js.index("function lakukanHapus")
        blok = js[awal:js.index("function eksporCsv")]
        self.assertIn("res.j.error", blok,
                      "pesan 429 dari server harus ditampilkan, bukan teks generik")


if __name__ == "__main__":
    unittest.main()
