"""Verifikasi: halaman dengan daftar kosong tidak lagi mematikan skrip halaman.

Sebelum jp_core.js diberi guard tbody-null, halaman yang memanggil
jpPaginasi({tbody: getElementById(...)}) saat elemen itu tidak ada akan
melempar TypeError di baris pertama IIFE, sehingga listener tombol yang
di baris-bawah tidak pernah terpasang.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

PAGES = [
    ("dashboard/spk", "btn-terbitkan"),
    ("dashboard/instansi", None),
    ("dashboard/spk_detail", None),
    ("kontraktor/index", None),
    ("kontraktor/peta", None),
    ("kontraktor/spk_list", None),
]


def app_dan_klien():
    import web.app as app_mod
    from web import database as db_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        # Panel "Terbitkan SPK" hanya dirender kalau ada kontraktor aktif.
        db_mod.init_kontraktor()
    c = app.test_client()
    c.get("/")
    with c.session_transaction() as s:
        s["admin_id"] = 1
        s["admin_user"] = "admin"
        s["admin_daerah"] = "Kabupaten Bogor"
        s["peran"] = "dinas"
    return app, c


class TestDaftarKosong(unittest.TestCase):
    def test_halaman_spk_kosong_tetap_punya_elemen_paginasi(self):
        app, c = app_dan_klien()
        r = c.get("/pupr-kab-bogor/dashboard/spk")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        # Elemen ini harus ada walau items kosong; kalau hilang, jpPaginasi
        # dipanggil dengan tbody null dan seluruh skrip halaman mati.
        for id_ in ("spk-paginasi", "spk-page-info"):
            self.assertIn(f'id="{id_}"', html, f"#{id_} hilang saat daftar kosong")

    def test_tombol_terbitkan_ada_walau_belum_ada_spk(self):
        app, c = app_dan_klien()
        html = c.get("/pupr-kab-bogor/dashboard/spk").get_data(as_text=True)
        self.assertIn('id="btn-terbitkan"', html)
        # Listener-nya terpasang lewat addEventListener di IIFE yang sama
        # dengan pemanggilan jpPaginasi -- kalau itu melempar, tombol mati.
        self.assertIn('getElementById("btn-terbitkan")', html)
        self.assertIn('addEventListener("click"', html)

    def test_jp_core_tidak_melempar_saat_tbody_null(self):
        """Penjaga utama: helper harus bail-out, bukan melempar."""
        import subprocess
        import re
        with open("web/static/js/jp_core.js", encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"window\.jpNomorHalaman.*?window\.jpToast", src, re.S)
        self.assertTrue(m)
        harness = (
            "global.window={};global.document={getElementById:()=>null};\n"
            + m.group(0).replace("window.jpToast", "")
            + "\ntry{window.jpPaginasi({tbody:null,bar:null,info:null}).segarkan();"
            "console.log('AMAN');}catch(e){console.log('MELEMPAR:'+e.message);}\n"
        )
        tmp = os.path.join(tempfile.gettempdir(), "jp_tbody_null.js")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(harness)
        out = subprocess.run(["node", tmp], capture_output=True, text=True)
        self.assertIn("AMAN", out.stdout,
                      f"jpPaginasi masih melempar: {out.stdout}{out.stderr}")