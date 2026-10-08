"""Uji audit trail disposisi: perubahan status mencatat pelaku (oleh).

Perubahan status HARUS selalu tercatat di disposisi_catatan (walau tanpa
catatan teks), lengkap dengan username admin, untuk akuntabilitas.
"""
import os
import tempfile
import unittest


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    return app


class TestAuditDisposisi(unittest.TestCase):
    def test_update_status_mencatat_oleh_tanpa_catatan(self):
        app = _app()
        c = app.test_client()
        with app.app_context():
            from database import (AKUN_DEMO, init_instansi, migrasi_disposisi_v2,
                                  migrasi_admin_v2, migrasi_sesi_v2, init_admin,
                                  simpan_disposisi, riwayat_catatan)
            init_instansi()
            migrasi_disposisi_v2()
            migrasi_admin_v2()
            migrasi_sesi_v2()
            init_admin()
            did = simpan_disposisi(
                bap_id=1, bap_nomor="BA-INS/1", lokasi="Jl Uji",
                lat=-6.9, lon=107.6, n_temuan=2, total_rp=1000, worst="Berat",
                instansi_id=None, instansi_nama="Dinas Uji",
                instansi_daerah="Bandung", instansi_email="a@b.c",
                urgensi="Kritis", catatan="-")

        c.post("/login", data={"username": AKUN_DEMO[0], "password": AKUN_DEMO[1]})
        r = c.put("/api/disposisi/%d" % did, json={"status": "Diproses"})
        self.assertTrue(r.get_json().get("ok"), r.get_json())

        with app.app_context():
            cat = riwayat_catatan(did)
        self.assertTrue(cat, "perubahan status harus tercatat di audit trail")
        self.assertEqual(cat[-1]["status"], "Diproses")
        self.assertEqual(cat[-1]["oleh"], AKUN_DEMO[0])


if __name__ == "__main__":
    unittest.main()
