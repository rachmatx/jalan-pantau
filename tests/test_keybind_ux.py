"""Regresi UX keyboard: konfirmasi Enter/Esc, pintasan global, drag-drop kalibrasi.

Kontrak statis (pola yang sama dengan tes batch 2) karena logika berada di
template/JS halaman; perilaku nyata diverifikasi di browser.
"""
import unittest
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent


def _teks(rel):
    return (AKAR / rel).read_text(encoding="utf-8")


def _potong(teks, awal, akhir):
    i = teks.index(awal)
    return teks[i:teks.index(akhir, i)]


class TestKonfirmasiKeyboard(unittest.TestCase):
    def setUp(self):
        self.base = _teks("web/templates/base.html")

    def test_tombol_utama_difokuskan(self):
        blok = self.base[self.base.index("window.jpConfirm"):]
        self.assertIn('getElementById("jp-confirm-ok")', blok)
        self.assertIn(".focus()", blok.split('getElementById("jp-confirm-ok")', 1)[1][:120])

    def test_escape_membatalkan_konfirmasi(self):
        blok = _potong(self.base, "window.jpConfirm", "window.jpButuhLogin")
        self.assertIn('"Escape"', blok)
        self.assertIn("resolve(false)", blok)

    def test_modal_login_bisa_ditutup_escape(self):
        blok = _potong(self.base, "window.jpButuhLogin", "</script>")
        self.assertIn('"Escape"', blok)
        self.assertIn("tutup(false)", blok)

    def test_helper_guard_input_tersedia(self):
        self.assertIn("window.jpSedangMengetik", self.base)
        self.assertIn("isContentEditable", self.base)


class TestPanelPintasan(unittest.TestCase):
    def test_panel_dan_tombol_footer_ada(self):
        base = _teks("web/templates/base.html")
        self.assertIn('id="btn-pintasan"', base)
        self.assertIn('id="jp-pintasan"', base)
        self.assertIn('e.key === "?"', base)
        self.assertIn("Ctrl + Enter", base)
        self.assertIn("Pintasan", base)


class TestDropKalibrasi(unittest.TestCase):
    def test_drag_drop_ke_input_yang_sama(self):
        tpl = _teks("web/templates/kalibrasi.html")
        for ev in ("dragenter", "dragover", "dragleave", "drop"):
            self.assertIn(ev, tpl, "event %s belum ditangani" % ev)
        self.assertIn("new DataTransfer()", tpl)
        self.assertIn('new Event("change"', tpl.replace("'", '"'),
                      "berkas drop harus memicu change pada input yang ada")
        self.assertIn("image/jpeg", tpl)
        self.assertIn("5 * 1024 * 1024", tpl)
        self.assertIn("kal-seret", tpl)

    def test_shortcut_kalibrasi(self):
        tpl = _teks("web/templates/kalibrasi.html")
        self.assertIn("btnSimpanP.click()", tpl)
        self.assertIn("btnHapus.click()", tpl)
        self.assertIn('"Backspace"', tpl)


class TestShortcutHalaman(unittest.TestCase):
    def setUp(self):
        self.deteksi = _teks("web/static/js/deteksi.js")
        self.live = _teks("web/static/js/live.js")
        self.riwayat = _teks("web/static/js/riwayat.js")
        self.peta = _teks("web/static/js/peta.js")

    def test_deteksi_ctrl_enter_dan_tab(self):
        self.assertIn("requestSubmit()", self.deteksi)
        self.assertIn("ctrlKey", self.deteksi)
        self.assertIn('e.key === "1"', self.deteksi)
        self.assertIn('"tab-live"', self.deteksi)

    def test_live_shortcut(self):
        self.assertIn('e.key === " "', self.live)
        self.assertIn('btn-snapshot', self.live)
        self.assertIn('btn-toggle-box', self.live)
        self.assertIn('btn-toggle-osd', self.live)

    def test_riwayat_cari_dan_pdf(self):
        self.assertIn('e.key === "/"', self.riwayat)
        self.assertIn('"f-q"', self.riwayat)
        self.assertIn('"d-pdf"', self.riwayat)

    def test_peta_cari_lokasi_fit(self):
        self.assertIn('e.key === "/"', self.peta)
        self.assertIn("map-lokasi", self.peta)
        self.assertIn("map-fit", self.peta)

    def test_semua_shortcut_menghormati_input(self):
        for nama, js in (("deteksi", self.deteksi), ("live", self.live),
                         ("riwayat", self.riwayat), ("peta", self.peta)):
            self.assertIn("jpSedangMengetik", js, nama)


if __name__ == "__main__":
    unittest.main()
