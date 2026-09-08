"""Regresi config inferensi + tiling (murni, tanpa model/server).

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_inferensi -v
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "web"), os.path.join(ROOT, "app")):
    if p not in sys.path:
        sys.path.insert(0, p)


class TestConfigInferensi(unittest.TestCase):
    def test_default_dari_yaml(self):
        import deteksi
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        self.assertEqual(inf["imgsz_gambar"], 960)
        self.assertEqual(inf["imgsz_live"], 960)
        self.assertEqual(inf["iou"], 0.5)
        self.assertTrue(inf["tta"])  # default true sejak trial 3 foto 2026-09-07
        self.assertEqual(inf["teliti"]["tile"], 640)

    def test_fallback_bila_file_hilang(self):
        import deteksi
        inf = deteksi.get_inferensi(path=os.path.join(ROOT, "tidak-ada.yaml"))
        self.assertEqual(inf["imgsz_gambar"], 960)
        self.assertEqual(inf["iou"], 0.5)

    def test_nilai_ngawur_diklem(self):
        import deteksi
        fd, path = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("imgsz_gambar: 99999\niou: 7\nteliti:\n  tile: 10\n  overlap: 0.9\n")
            inf = deteksi.get_inferensi(path=path)
            self.assertEqual(inf["imgsz_gambar"], 1536)
            self.assertEqual(inf["iou"], 0.95)
            self.assertEqual(inf["teliti"]["tile"], 320)
            self.assertEqual(inf["teliti"]["overlap"], 0.5)
        finally:
            os.remove(path)


class TestAmbangKelas(unittest.TestCase):
    TOL = {"longitudinal_crack": 0.13, "pothole": 0.0}

    def test_retak_lebih_sensitif_dari_slider(self):
        from deteksi import ambang_efektif
        self.assertAlmostEqual(ambang_efektif("longitudinal_crack", 0.25, self.TOL), 0.12)

    def test_slider_tetap_batas_mutlak(self):
        # Slider 0.80: retak 0.67, pothole 0.80 — tak ada yang lolos di bawah itu.
        from deteksi import ambang_efektif
        self.assertAlmostEqual(ambang_efektif("longitudinal_crack", 0.80, self.TOL), 0.67)
        self.assertAlmostEqual(ambang_efektif("pothole", 0.80, self.TOL), 0.80)

    def test_kelas_tak_dikenal_pakai_slider(self):
        from deteksi import ambang_efektif
        self.assertEqual(ambang_efektif("alien", 0.25, self.TOL), 0.25)

    def test_conf_prediksi_ambil_terendah(self):
        from deteksi import conf_prediksi
        self.assertAlmostEqual(conf_prediksi(0.25, self.TOL), 0.12)
        self.assertAlmostEqual(conf_prediksi(0.80, self.TOL), 0.67)

    def test_saring_rows(self):
        from deteksi import saring_rows
        rows = [
            {"kelas": "longitudinal_crack", "conf": 0.15, "panjang_cm": 50,
             "lebar_cm": 1, "luas_m2": 0.05},
            {"kelas": "longitudinal_crack", "conf": 0.10, "panjang_cm": 50,
             "lebar_cm": 1, "luas_m2": 0.05},
            {"kelas": "pothole", "conf": 0.20, "panjang_cm": 30,
             "lebar_cm": 30, "luas_m2": 0.09},
        ]
        ok, info = saring_rows(rows, 0.25, self.TOL, None)
        self.assertEqual(len(ok), 1)
        self.assertEqual(ok[0]["conf"], 0.15)
        self.assertEqual(info["ambang"], 2)
        # Slider 0.80: semua tersaring.
        ok, info = saring_rows(rows, 0.80, self.TOL, None)
        self.assertEqual(len(ok), 0)
        self.assertEqual(info["ambang"], 3)


class TestPriorUkuran(unittest.TestCase):
    BATAS = {"diameter_maks_cm": 300, "lebar_retak_maks_cm": 100,
             "luas_maks_m2": 100}

    def test_lubang_raksasa_ditolak(self):
        from deteksi import masuk_akal
        self.assertFalse(masuk_akal({"kelas": "pothole", "panjang_cm": 500,
                                     "lebar_cm": 400, "luas_m2": 20}, self.BATAS))

    def test_lubang_wajar_lolos(self):
        from deteksi import masuk_akal
        self.assertTrue(masuk_akal({"kelas": "pothole", "panjang_cm": 60,
                                    "lebar_cm": 50, "luas_m2": 0.3}, self.BATAS))

    def test_retak_wajar_lolos_raksasa_ditolak(self):
        from deteksi import masuk_akal
        self.assertTrue(masuk_akal({"kelas": "transverse_crack", "panjang_cm": 200,
                                    "lebar_cm": 5, "luas_m2": 0.1}, self.BATAS))
        self.assertFalse(masuk_akal({"kelas": "transverse_crack", "panjang_cm": 200,
                                     "lebar_cm": 500, "luas_m2": 10}, self.BATAS))


class TestWbf(unittest.TestCase):
    def test_duplikat_dilebur_bukan_dibuang(self):
        from deteksi import wbf_gabung
        boxes = [[0, 0, 100, 100], [10, 10, 110, 110], [500, 500, 600, 600]]
        hasil = wbf_gabung(boxes, [0.9, 0.7, 0.5], 0.5)
        self.assertEqual(len(hasil), 2)
        fb, fs, anggota = sorted(hasil, key=lambda t: -t[1])[0]
        self.assertEqual(sorted(anggota), [0, 1])
        self.assertTrue(0 < fb[0] < 10)  # di antara kedua box
        self.assertAlmostEqual(fs, 0.8)

    def test_config_metode_gabung_valid(self):
        import deteksi
        deteksi._infer = None
        self.assertIn(deteksi.get_inferensi()["teliti"]["metode_gabung"],
                      ("nms", "wbf"))


class TestVotingTemporal(unittest.TestCase):
    def test_mayoritas_dan_seri(self):
        from deteksi import kelas_mayoritas
        self.assertEqual(kelas_mayoritas({"pothole": 1, "alligator_crack": 4}),
                         "alligator_crack")
        self.assertEqual(kelas_mayoritas({"pothole": 2, "alligator_crack": 2}),
                         "pothole")  # seri -> pertama terlihat
        self.assertIsNone(kelas_mayoritas({}))

    def test_snapshot_saring_frame_dan_ambang(self):
        import streaming
        from streaming import StreamManager
        m = StreamManager()
        m.conf = 0.25
        m.tracks = {
            1: {"kelas": "pothole", "conf_max": 0.8, "box_best": (0, 0, 80, 80),
                "area_best": 6400, "frames": 5,
                "votes": {"pothole": 5}},
            2: {"kelas": "pothole", "conf_max": 0.8, "box_best": (0, 0, 80, 80),
                "area_best": 6400, "frames": 1,
                "votes": {"pothole": 1}},  # kedip 1 frame
            3: {"kelas": "longitudinal_crack", "conf_max": 0.10,
                "box_best": (0, 0, 400, 8), "area_best": 3200, "frames": 5,
                "votes": {"longitudinal_crack": 5}},  # di bawah ambang retak
        }
        m.latest_jpg = None
        asli = streaming.get_inferensi
        streaming.get_inferensi = lambda: {
            "live": {"min_frames": 3},
            "toleransi_kelas": {"longitudinal_crack": 0.12},
            "batas_ukuran": {"diameter_maks_cm": 300,
                             "lebar_retak_maks_cm": 100, "luas_maks_m2": 100}}
        try:
            snap = m.snapshot()
        finally:
            streaming.get_inferensi = asli
        self.assertEqual([r["track_id"] for r in snap["rows"]], [1])
        self.assertEqual(snap["disaring"], {"ambang": 1, "ukuran": 0, "frame": 1})


class TestDedupTeliti(unittest.TestCase):
    def test_box_tepi_dalam_dibuang_tepi_gambar_lolos(self):
        from deteksi import sentuh_tepi_dalam
        # gambar 1000x1000, tile 640: tile (0,0) tepi kanan/bawah = dalam
        self.assertTrue(sentuh_tepi_dalam((630, 100, 700, 200), 0, 0, 640, 1000, 1000))
        self.assertTrue(sentuh_tepi_dalam((100, 630, 200, 700), 0, 0, 640, 1000, 1000))
        # tepi kiri/atas tile (0,0) = tepi gambar -> lolos
        self.assertFalse(sentuh_tepi_dalam((0, 0, 100, 100), 0, 0, 640, 1000, 1000))
        # box tengah lolos
        self.assertFalse(sentuh_tepi_dalam((100, 100, 200, 200), 0, 0, 640, 1000, 1000))
        # tile terakhir: tepi kanan = tepi gambar -> lolos
        self.assertFalse(sentuh_tepi_dalam((540, 100, 639, 200), 360, 0, 640, 1000, 1000))

    def test_nms_agnostik_satu_wilayah_satu_pemenang(self):
        from deteksi import nms_agnostik
        gabung = [([0, 0, 100, 100], 0.5, "alligator_crack"),
                  ([5, 5, 105, 105], 0.3, "pothole"),
                  ([500, 500, 600, 600], 0.2, "pothole")]
        hasil = nms_agnostik(sorted(gabung, key=lambda t: -t[1]), 0.6)
        self.assertEqual(len(hasil), 2)
        self.assertEqual(hasil[0][2], "alligator_crack")  # conf tertinggi menang

    def test_box_kecil_tertelan_digabung(self):
        from deteksi import nms_agnostik
        gabung = [([0, 0, 300, 300], 0.5, "alligator_crack"),  # IoU kecil...
                  ([100, 100, 150, 150], 0.3, "pothole")]  # ...tapi tertelan utuh
        hasil = nms_agnostik(sorted(gabung, key=lambda t: -t[1]), 0.6)
        self.assertEqual(len(hasil), 1)

    def test_config_baru_terbaca(self):
        import deteksi
        deteksi._infer = None
        t = deteksi.get_inferensi()["teliti"]
        self.assertTrue(t["buang_tepi_tile"])
        self.assertEqual(t["iou_agnostik"], 0.6)


class TestGabungFragmen(unittest.TestCase):
    def _row(self, kelas, conf, box):
        return {"kelas": kelas, "conf": conf, "box": box,
                "panjang_cm": 10, "lebar_cm": 10, "luas_m2": 0.01,
                "luas_cm2": 100, "tebal_asumsi_cm": 5, "bahan": "b",
                "total_rp": 1000, "total_str": "Rp1.000", "dasar": "d",
                "severity": "Ringan"}

    def test_fragmen_bersentuhan_melebur_dan_dihitung_ulang(self):
        from deteksi import gabung_fragmen
        rows = [self._row("pothole", 0.8, [0, 0, 100, 100]),
                self._row("pothole", 0.6, [50, 50, 150, 150]),
                self._row("pothole", 0.7, [500, 500, 600, 600])]
        baru, n = gabung_fragmen(rows)
        self.assertEqual(n, 1)
        self.assertEqual(len(baru), 2)
        g = [r for r in baru if r.get("fragmen") == 2][0]
        self.assertEqual(g["box"], [0, 0, 150, 150])
        self.assertEqual(g["conf"], 0.8)  # pemenang
        # severity/biaya dihitung ulang dari box gabungan (bukan jumlah fragmen)
        self.assertNotEqual(g["luas_m2"], 0.01)

    def test_terpisah_tidak_melebur(self):
        from deteksi import gabung_fragmen
        rows = [self._row("pothole", 0.8, [0, 0, 50, 50]),
                self._row("pothole", 0.7, [500, 500, 560, 560])]
        baru, n = gabung_fragmen(rows)
        self.assertEqual(n, 0)
        self.assertEqual(len(baru), 2)

    def test_lintas_kelas_bisa_dimatikan(self):
        from deteksi import gabung_fragmen
        rows = [self._row("pothole", 0.8, [0, 0, 100, 100]),
                self._row("alligator_crack", 0.7, [10, 10, 110, 110])]
        baru, n = gabung_fragmen(rows, lintas_kelas=False)
        self.assertEqual(n, 0)
        baru, n = gabung_fragmen(rows, lintas_kelas=True)
        self.assertEqual(n, 1)
        self.assertEqual(baru[0]["kelas"], "pothole")

    def test_config_terbaca(self):
        import deteksi
        deteksi._infer = None
        gf = deteksi.get_inferensi()["gabung_fragmen"]
        self.assertTrue(gf["aktif"])
        self.assertEqual(gf["inter_min"], 0.3)


class TestSaringAkhir(unittest.TestCase):
    def _row(self, conf, box):
        return {"kelas": "pothole", "conf": conf, "box": box,
                "panjang_cm": 10, "lebar_cm": 10, "luas_m2": 0.01}

    def test_box_mungil_dibuang(self):
        from deteksi import saring_rows
        rows = [self._row(0.9, [0, 0, 100, 100]),
                self._row(0.8, [0, 0, 10, 10])]  # 100 px < 900
        ok, info = saring_rows(rows, 0.25, {}, None, 900)
        self.assertEqual(len(ok), 1)
        self.assertEqual(info["mungil"], 1)

    def test_tanpa_box_diloloskan(self):
        from deteksi import saring_rows
        ok, info = saring_rows([{"kelas": "pothole", "conf": 0.9}], 0.25,
                               {}, None, 900)
        self.assertEqual(len(ok), 1)

    def test_topk_ambil_conf_tertinggi(self):
        from deteksi import batas_topk
        rows = [self._row(c, [0, 0, 100, 100]) for c in (0.5, 0.9, 0.7)]
        ok, n = batas_topk(rows, 2)
        self.assertEqual(n, 1)
        self.assertEqual([r["conf"] for r in ok], [0.9, 0.7])
        ok, n = batas_topk(rows, 0)
        self.assertEqual((len(ok), n), (3, 0))

    def test_config_saring_terbaca(self):
        import deteksi
        deteksi._infer = None
        s = deteksi.get_inferensi()["saring"]
        self.assertEqual(s["luas_min_px"], 900)
        self.assertEqual(s["maks_temuan"], 20)


class TestVerifikasiOperator(unittest.TestCase):
    def _rows(self):
        return [
            {"kelas": "pothole", "conf": 0.8, "severity": "Berat",
             "box": [0, 0, 80, 80], "panjang_cm": 10, "lebar_cm": 10,
             "luas_cm2": 100, "luas_m2": 0.01, "total_rp": 5000,
             "total_str": "Rp5.000", "dasar": "d", "bahan": "b"},
            {"kelas": "longitudinal_crack", "conf": 0.5, "severity": "Ringan",
             "box": [0, 0, 400, 8], "panjang_cm": 50, "lebar_cm": 1,
             "luas_cm2": 50, "luas_m2": 0.005, "total_rp": 1000,
             "total_str": "Rp1.000", "dasar": "d", "bahan": "b"},
        ]

    def test_hapus(self):
        from deteksi import terapkan_koreksi
        baru, total, info = terapkan_koreksi(self._rows(), hapus=[0], severity={})
        self.assertEqual(len(baru), 1)
        self.assertEqual(info, {"hapus": 1, "severity": 0, "total": 1})
        self.assertEqual(baru[0]["idx_asli"], 1)

    def test_koreksi_severity_hitung_ulang(self):
        from deteksi import terapkan_koreksi
        baru, total, info = terapkan_koreksi(self._rows(), severity={"1": "Berat"})
        self.assertEqual(info["severity"], 1)
        r = baru[1]
        self.assertEqual(r["severity"], "Berat")
        self.assertEqual(r["diubah"], "severity Ringan->Berat")
        self.assertEqual(r["sumber"], "AI")
        # biaya dihitung ulang dari box + harga Berat (bukan angka asal 1000)
        self.assertNotEqual(r["total_rp"], 1000)
        self.assertEqual(r["bahan"], "beton + lapis pondasi")

    def test_tidak_ubah_tetap_nol(self):
        from deteksi import terapkan_koreksi
        baru, total, info = terapkan_koreksi(self._rows())
        self.assertEqual(info["total"], 0)
        self.assertEqual(len(baru), 2)

    def test_endpoint_verifikasi(self):
        import json as _json
        import tempfile
        import web.app as app_mod
        tmp = tempfile.mkdtemp()
        app = app_mod.create_app()
        app.config["DB_PATH"] = os.path.join(tmp, "t.db")
        app.config["TESTING"] = True
        c = app.test_client()
        with app.app_context():
            from database import init_instansi, migrasi_disposisi_v2
            init_instansi()
            migrasi_disposisi_v2()
            r = c.post("/api/verifikasi", json={"rows": self._rows(),
                                                "hapus": [0],
                                                "severity": {"1": "Berat"}})
            self.assertEqual(r.status_code, 200)
            j = r.get_json()
            self.assertEqual(len(j["rows"]), 1)
            self.assertEqual(j["info"]["total"], 2)
            self.assertIn("total_str", j)

    def test_pdf_dengan_ubah(self):
        import tempfile
        from laporan import buat_laporan
        rows = [dict(self._rows()[0], sumber="AI",
                     diubah="severity Ringan->Berat")]
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            buat_laporan(path, rows, 5000,
                         meta={"Sumber": "uji",
                               "Verifikasi operator": "1 perubahan (1 koreksi severity)"})
            with open(path, "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertGreater(os.path.getsize(path), 1000)
        finally:
            if os.path.exists(path):
                os.remove(path)


class TestBackendGanda(unittest.TestCase):
    def test_resolve_default_dan_fallback(self):
        import deteksi
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        self.assertEqual(inf["model_gambar"], "best_yolo11s.pt")
        self.assertEqual(inf["model_live"], "best.onnx")
        self.assertTrue(deteksi.resolve_model(kunci="model_gambar").name.endswith(".pt"))
        self.assertTrue(deteksi.resolve_model(kunci="model_live").name.endswith(".onnx"))
        # hilang / traversal -> fallback best.pt
        self.assertEqual(deteksi.resolve_model("tak-ada.onnx").name, "best.pt")
        self.assertEqual(deteksi.resolve_model("../x.pt").name, "best.pt")
        self.assertEqual(deteksi.resolve_model("jahat.exe").name, "best.pt")

    def test_nama_model(self):
        import deteksi
        deteksi._infer = None
        self.assertEqual(deteksi.nama_model(kunci="model_gambar"), "best_yolo11s.pt")
        self.assertEqual(deteksi.nama_model(kunci="model_live"), "best.onnx")

    def test_model_gambar_kelas_benar(self):
        import deteksi
        m = deteksi.get_model(kunci="model_gambar")
        self.assertEqual(m.names[4], "pothole")
        self.assertEqual(len(m.names), 5)

    def test_get_model_cache_per_path(self):
        import deteksi
        onnx = str(deteksi.WEIGHTS_DIR / "best.onnx")
        m1 = deteksi.get_model(onnx)
        m2 = deteksi.get_model(onnx)
        self.assertIs(m1, m2)
        self.assertIn("pothole", list(m1.names.values()))

    def test_onnx_inferensi_kecil(self):
        import numpy as np
        import deteksi
        m = deteksi.get_model(str(deteksi.WEIGHTS_DIR / "best.onnx"))
        img = np.zeros((96, 96, 3), dtype=np.uint8)
        r = m.predict(img, conf=0.25, imgsz=96, verbose=False)[0]
        self.assertIsNotNone(r)


class TestEnsemble(unittest.TestCase):
    def test_default_mati(self):
        import deteksi
        deteksi._infer = None
        en = deteksi.get_inferensi()["ensemble"]
        self.assertFalse(en["aktif"])
        self.assertEqual(en["model_kedua"], "best.pt")
        self.assertEqual(en["iou"], 0.5)
        self.assertEqual(en["metode"], "wbf")

    def test_parse_dan_sanitasi(self):
        import tempfile
        import deteksi
        with tempfile.NamedTemporaryFile("w", suffix=".yaml",
                                         delete=False) as f:
            f.write("ensemble:\n  aktif: true\n  model_kedua: ../jahat.pt\n"
                    "  iou: 9\n  metode: rata-rata\n")
            tmp = f.name
        try:
            en = deteksi.get_inferensi(path=tmp)["ensemble"]
        finally:
            import os
            os.unlink(tmp)
        self.assertTrue(en["aktif"])
        self.assertEqual(en["model_kedua"], "jahat.pt")
        self.assertEqual(en["iou"], 0.95)
        self.assertEqual(en["metode"], "wbf")

    def test_e2e_ensemble_dan_fallback_sama(self):
        import cv2
        import numpy as np
        import deteksi
        deteksi.get_model(kunci="model_gambar")
        deteksi.get_model(str(deteksi.WEIGHTS_DIR / "best.pt"))
        ok, buf = cv2.imencode(".jpg", np.zeros((160, 160, 3),
                                                dtype=np.uint8) + 128)
        self.assertTrue(ok)
        raw = buf.tobytes()
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        inf["ensemble"] = {"aktif": True, "model_kedua": "best.pt",
                           "iou": 0.5, "metode": "wbf"}
        try:
            h = deteksi.analisis_gambar(raw, conf=0.9, imgsz=160)
            self.assertIn("+", h["model"])
            self.assertIn("ensemble", h["disaring"])
            self.assertIsInstance(h["rows"], list)
            # model_kedua == utama -> jalur tunggal
            inf["ensemble"] = {"aktif": True,
                               "model_kedua": "best_yolo11s.pt",
                               "iou": 0.5, "metode": "wbf"}
            h2 = deteksi.analisis_gambar(raw, conf=0.9, imgsz=160)
            self.assertNotIn("+", h2["model"])
            self.assertNotIn("ensemble", h2["disaring"])
        finally:
            deteksi._infer = None


class TestKalibrasi(unittest.TestCase):
    def test_hitung_ppc(self):
        import deteksi
        self.assertAlmostEqual(deteksi.hitung_ppc(800, 10), 80.0)
        for px, cm in [(0, 10), (800, 0), (-5, 10), ("x", 10),
                       (1e12, 0.001)]:
            with self.assertRaises(ValueError):
                deteksi.hitung_ppc(px, cm)

    def test_simpan_roundtrip_dan_validasi(self):
        import tempfile
        import deteksi
        with tempfile.NamedTemporaryFile("w", suffix=".yaml",
                                         delete=False,
                                         encoding="utf-8") as f:
            f.write("# komen jaga\npixels_per_cm: 8.0  # lama\n"
                    "crack_width_mm:\n  ringan_max: 10\n")
            tmp = f.name
        try:
            st = deteksi.simpan_kalibrasi(80.5, metode="penggaris",
                                          catatan="uji", path=tmp)
            self.assertAlmostEqual(st["pixels_per_cm"], 80.5)
            self.assertEqual(st["metode"], "penggaris")
            teks = open(tmp, encoding="utf-8").read()
            self.assertIn("pixels_per_cm: 80.5000", teks)
            self.assertIn("# komen jaga", teks)
            self.assertIn("ringan_max: 10", teks)
            self.assertIn("metode: penggaris", teks)
            # tulis ulang: blok lama diganti, tak ganda
            deteksi.simpan_kalibrasi(9, metode="manual", path=tmp)
            teks2 = open(tmp, encoding="utf-8").read()
            self.assertEqual(teks2.count("kalibrasi:"), 1)
            self.assertIn("metode: manual", teks2)
            # regresi: catatan "-" polos merusak YAML (sekuens)
            deteksi.simpan_kalibrasi(10, path=tmp)
            import yaml
            isi = yaml.safe_load(open(tmp, encoding="utf-8"))
            self.assertEqual(isi["kalibrasi"]["catatan"], "-")
            self.assertAlmostEqual(float(isi["pixels_per_cm"]), 10.0)
            for buruk, m in [(0, "manual"), (-1, "manual"), (1e9, "manual"),
                             (8, "salah"), ("x", "manual")]:
                with self.assertRaises(ValueError):
                    deteksi.simpan_kalibrasi(buruk, metode=m, path=tmp)
        finally:
            import os
            os.unlink(tmp)

    def test_status_default(self):
        import deteksi
        deteksi._cfg = None
        st = deteksi.get_kalibrasi()
        self.assertIn(st["metode"], ("bawaan", "manual", "penggaris"))
        self.assertGreater(st["pixels_per_cm"], 0)
        deteksi._cfg = None


class TestHargaPerKelas(unittest.TestCase):
    def test_kelompok_dan_fallback(self):
        from biaya import cari_harga, kelompok_jenis, load_harga
        self.assertEqual(kelompok_jenis("longitudinal_crack"), "crack")
        self.assertEqual(kelompok_jenis("transverse_crack"), "crack")
        self.assertEqual(kelompok_jenis("pothole"), "pothole")
        self.assertIsNone(kelompok_jenis("kelas_aneh"))
        rows = load_harga("config/harga_acuan.csv")
        # retak ringan -> crack sealing per meter
        h = cari_harga(rows, "Ringan", "crack")
        self.assertEqual(h["bahan"], "crack sealing emulsi")
        self.assertEqual(h["satuan"], "m")
        # lubang ringan -> fallback patching per m2
        h = cari_harga(rows, "Ringan", "pothole")
        self.assertEqual(h["bahan"], "cold-mix patching")
        # retak berat -> baris crack satuan m (bukan beton m3)
        h = cari_harga(rows, "Berat", "crack")
        self.assertEqual(h["satuan"], "m")
        self.assertIn("crack sealing", h["bahan"])
        with self.assertRaises(ValueError):
            cari_harga(rows, "Ringansekali")

    def test_estimasi_satuan_meter(self):
        from biaya import estimasi, load_harga
        rows = load_harga("config/harga_acuan.csv")
        item = {"kelas": "transverse_crack", "severity": "Ringan",
                "panjang_cm": 200, "lebar_cm": 2, "luas_cm2": 400,
                "tebal_asumsi_cm": 2}
        r = estimasi(item, rows)
        self.assertEqual(r["total_rp"], round(2.0 * 45000))  # 2 m x Rp45rb
        self.assertEqual(r["satuan"], "m")
        # lubang tak berubah: per m2
        item2 = {"kelas": "pothole", "severity": "Ringan",
                 "panjang_cm": 100, "lebar_cm": 50, "luas_cm2": 5000,
                 "tebal_asumsi_cm": 2}
        r2 = estimasi(item2, rows)
        self.assertEqual(r2["total_rp"], round(0.5 * 150000))
        self.assertEqual(r2["satuan"], "m2")


class TestBatasUpload(unittest.TestCase):
    def test_detect_tolak_gambar_raksasa(self):
        import io
        import sys
        import web.app as app_mod
        app = app_mod.create_app()
        c = app.test_client()
        besar = b"\xff\xd8\xff" + b"\x00" * (15 * 1024 * 1024)
        r = c.post("/api/detect", data={"gambar": (io.BytesIO(besar),
                                                   "besar.jpg")},
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("15MB", r.json["error"])
        self.assertLessEqual(len(besar), app_mod.MAX_IMG_BYTES + 3)

    def test_errorhandler_413_json(self):
        import web.app as app_mod
        app = app_mod.create_app()
        with app.test_request_context():
            resp = app.handle_user_exception(
                __import__("werkzeug").exceptions.RequestEntityTooLarge())
            self.assertEqual(resp[1], 413)


class TestGridTile(unittest.TestCase):
    def test_menutupi_sudut_dan_tidak_keluar(self):
        from deteksi import grid_tile
        w, h, tile = 4032, 3024, 640
        grid = grid_tile(w, h, tile, 0.25)
        self.assertIn((0, 0), grid)
        for (x, y) in grid:
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + tile, w)
            self.assertLessEqual(y + tile, h)
        # pojok kanan-bawah tertutup tile terakhir
        lx, ly = max(x for x, _ in grid), max(y for _, y in grid)
        self.assertEqual((lx, ly), (w - tile, h - tile))

    def test_gambar_kecil_satu_tile(self):
        from deteksi import grid_tile
        self.assertEqual(grid_tile(400, 300, 640, 0.25), [(0, 0)])


class TestNmsGabung(unittest.TestCase):
    def test_duplikat_dibuang_yang_terpisah_disimpan(self):
        from deteksi import nms_gabung
        boxes = [[0, 0, 100, 100], [5, 5, 100, 100], [500, 500, 600, 600]]
        skor = [0.9, 0.8, 0.7]
        simpan = nms_gabung(boxes, skor, 0.5)
        self.assertIn(0, simpan)
        self.assertNotIn(1, simpan)
        self.assertIn(2, simpan)


if __name__ == "__main__":
    unittest.main()
