"""Uji kualitas penulisan template.

Menangkap kelas bug yang lolos semua guard lain:
- entitas HTML rusak (`&qnbsp;` dan sejenisnya). Karakternya ASCII semua,
  jadi guard emoji dan guard aksara asing tidak menyentuhnya, tapi
  tampilannya jadi sampah di browser.
- placeholder Jinja yang tertinggal di sumber template (mis. `{{ }}` atau
  `{% %}` yang tidak pernah dievaluasi karena ditulis di luar blok).
"""
import html
import pathlib
import re
import unittest

AKAR = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = AKAR / "web" / "templates"

ENTITAS = re.compile(r"&([A-Za-z][A-Za-z0-9]{1,10});")
VALID = {e.rstrip(";") for e in html.entities.html5}


def berkas_template():
    return sorted(p for p in TEMPLATES.rglob("*.html"))


class TestEntitasHtml(unittest.TestCase):
    """Entitas yang tidak dikenal browser akan tampil apa adanya."""

    def test_tidak_ada_entitas_rusak(self):
        rusak = []
        for p in berkas_template():
            t = p.read_text(encoding="utf-8")
            for m in ENTITAS.finditer(t):
                nama = m.group(1)
                if nama in VALID or nama + ";" in VALID:
                    continue
                ln = t[:m.start()].count("\n") + 1
                rusak.append(f"{p.relative_to(AKAR).as_posix()}:{ln} {m.group(0)}")
        self.assertEqual(rusak, [], "Entitas HTML rusak: " + ", ".join(rusak))

    def test_tidak_ada_entitas_terbalik(self):
        """`&amp;nbsp;` berarti teks literal "&nbsp;", bukan spasi."""
        salah = []
        for p in berkas_template():
            t = p.read_text(encoding="utf-8")
            for m in re.finditer(r"&amp;(nbsp|amp|lt|gt|quot|#\d+);", t):
                ln = t[:m.start()].count("\n") + 1
                salah.append(f"{p.relative_to(AKAR).as_posix()}:{ln} {m.group(0)}")
        self.assertEqual(salah, [], "Entitas terbalik: " + ", ".join(salah))


class TestPlaceholderJinja(unittest.TestCase):
    """Placeholder Jinja yang tertinggal akan tampil mentah di halaman.

    Diperiksa pada HTML yang sudah dirender, bukan pada sumber template:
    menghitung `{{`/`}}` di sumber tidak bisa dipercaya karena blok
    JavaScript dan CSS juga memakai kurung kurawal, sehingga hampir selalu
    menghasilkan false positive.
    """

    HALAMAN = ["/", "/peta", "/riwayat", "/tentang", "/login", "/disposisi"]

    def setUp(self):
        import os
        import tempfile

        import web.app as app_mod
        self.app = app_mod.create_app()
        self.app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
        self.app.config["TESTING"] = True
        self.c = self.app.test_client()

    def test_tidak_ada_placeholder_di_halaman_publik(self):
        for path in self.HALAMAN:
            with self.subTest(path=path):
                teks = self.c.get(path).get_data(as_text=True)
                self.assertNotIn("{{", teks, f"placeholder {{{{ masih ada di {path}")
                self.assertNotIn("{%", teks, f"placeholder {{% masih ada di {path}")

    def test_tidak_ada_placeholder_di_halaman_login_gagal(self):
        """Halaman login dengan pesan galat juga harus bersih."""
        r = self.c.post("/login", data={"username": "x", "password": "y"})
        teks = r.get_data(as_text=True)
        self.assertNotIn("{{", teks)
        self.assertNotIn("{%", teks)


class TestLoginKontraktor(unittest.TestCase):
    """Halaman login melayani dua jenis akun, jadi harus menyebut keduanya."""

    def setUp(self):
        import os
        import tempfile

        import web.app as app_mod
        self.app = app_mod.create_app()
        self.app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
        self.app.config["TESTING"] = True

    def test_login_menyebut_dua_peran(self):
        html_teks = self.app.test_client().get("/login").get_data(as_text=True)
        self.assertIn("kontraktor", html_teks.lower())
        self.assertIn("dinas", html_teks.lower())
        # Tidak boleh lagi judul eksklusif yang menutupi kontraktor.
        self.assertNotIn("hanya untuk akun resmi dinas", html_teks)

    def test_login_tetap_punya_field_csrf(self):
        html_teks = self.app.test_client().get("/login").get_data(as_text=True)
        self.assertIn('name="_csrf"', html_teks)


if __name__ == "__main__":
    unittest.main()