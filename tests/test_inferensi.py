"""Regresi config inferensi + tiling (murni, tanpa model/server).

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_inferensi -v
"""
import math
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "web"), os.path.join(ROOT, "app")):
    if p not in sys.path:
        sys.path.insert(0, p)


class TestConfigInferensi(unittest.TestCase):
    def test_default_dari_yaml(self):
        import deteksi
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        self.assertEqual(inf["imgsz_gambar"], 640)
        self.assertEqual(inf["imgsz_live"], 640)  # akurasi penuh (GPU real-time)
        self.assertEqual(inf["iou"], 0.5)
        self.assertTrue(inf["tta"])  # default true sejak trial 3 foto 2026-09-07
        self.assertEqual(inf["teliti"]["tile"], 640)
        self.assertEqual(inf["device"], "auto")
        # 1536 = batas analisis sejak 26 Okt 2026 (lihat config/inferensi.yaml);
        # 0 = resolusi asli.
        self.assertEqual(inf["maks_sisi_proses"], 1536)

    def test_fallback_bila_file_hilang(self):
        import deteksi
        inf = deteksi.get_inferensi(path=os.path.join(ROOT, "tidak-ada.yaml"))
        self.assertEqual(inf["imgsz_gambar"], 640)
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

    # --- Regresi: yaml.YAMLError tidak menurun dari ValueError -------------
    # Dulu blok except di get_inferensi hanya menangkap (OSError, ValueError).
    # Satu indentasi salah di config/inferensi.yaml membuat YAMLError melescap
    # -> 500 di SETIAP request /api/detect. config/inferensi.yaml sengaja
    # ditulis supaya bisa diedit pengguna tanpa koding, jadi kegagalan ini nyata.

    def test_yaml_rusak_tidak_melunca(self):
        import deteksi
        rusak = {
            "indentasi": "model_gambar: best.pt\n  imgsz_gambar: 960\n",
            "kutip_tak_tertutup": 'model_gambar: "best.pt\nimgsz_gambar: 960\n',
            "tab": "imgsz_gambar: 960\n\tiou: 0.5\n",
            "bukan_mapping": "- a\n- b\n",
        }
        for nama, isi in rusak.items():
            with self.subTest(kasus=nama):
                fd, path = tempfile.mkstemp(suffix=".yaml")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(isi)
                    inf = deteksi.get_inferensi(path=path)  # tidak boleh melempar
                    self.assertEqual(inf["imgsz_gambar"], 640)
                    self.assertEqual(inf["iou"], 0.5)
                finally:
                    os.remove(path)

    def test_yaml_rusak_tidak_kotori_default(self):
        """Parse gagal -> TIDAK boleh ada kunci yang terlanjur ter-override."""
        import deteksi
        fd, path = tempfile.mkstemp(suffix=".yaml")
        try:
            # imgsz_gambar: 320 edgyati success, lalu baris rusak.
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("imgsz_gambar: 320\n  rusak: 1\n")
            inf = deteksi.get_inferensi(path=path)
            self.assertEqual(inf["imgsz_gambar"], 640)  # default, bukan 320
        finally:
            os.remove(path)

    def test_device_disaring(self):
        """device hanya boleh auto/cpu/gpu atau daftar indeks; lain -> auto."""
        import deteksi
        kasus = {"auto": "auto", "GPU": "gpu", "cpu": "cpu", "0": "0",
                 "0,1": "0,1", " 0,1 ": "0,1", "jahat": "auto",
                 "cuda:0": "auto", "": "auto", None: "auto"}
        for masuk, harap in kasus.items():
            with self.subTest(masuk=masuk):
                fd, path = tempfile.mkstemp(suffix=".yaml")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(f"device: {masuk if masuk is not None else ''}\n")
                    inf = deteksi.get_inferensi(path=path)
                    self.assertEqual(inf["device"], harap)
                finally:
                    os.remove(path)


class TestPilihDevice(unittest.TestCase):
    def test_cpu_dipaksa(self):
        import deteksi
        self.assertEqual(deteksi.pilih_device("cpu"), "cpu")

    def test_gpu_dipaksa(self):
        import deteksi
        self.assertEqual(deteksi.pilih_device("gpu"), 0)

    def test_indeks_diteruskan(self):
        import deteksi
        self.assertEqual(deteksi.pilih_device("0,1"), "0,1")

    def test_auto_selalu_aman(self):
        """auto -> 0 (bila CUDA ada) atau 'cpu'; tak boleh melempar."""
        import deteksi
        self.assertIn(deteksi.pilih_device("auto"), (0, "cpu"))
        self.assertIn(deteksi.pilih_device(None), (0, "cpu"))

    def test_onnx_selalu_cpu(self):
        """Model .onnx -> 'cpu' walau device='auto'/'gpu' (tanpa onnxruntime-gpu)."""
        import deteksi
        self.assertEqual(deteksi.pilih_device("auto", "best.onnx"), "cpu")
        self.assertEqual(deteksi.pilih_device("gpu", "best.onnx"), "cpu")
        self.assertIn(deteksi.pilih_device("auto", "best.pt"), (0, "cpu"))


class TestModeBackend(unittest.TestCase):
    """Knob `mode_backend`: .pt di GPU, .onnx di CPU — HANYA jalur live.

    Yang dikunci di sini:
    - config `model_live` TIDAK ikut berubah (resolve_model tidak disentuh),
    - auto tidak pernah jadi error walau kembar .onnx hilang,
    - jalur gambar tidak pernah terpengaruh (pakai model_gambar apa adanya).
    """

    def setUp(self):
        import deteksi
        self.d = deteksi
        self.simpan = deteksi._cuda_tersedia

    def tearDown(self):
        self.d._cuda_tersedia = self.simpan

    def test_default_auto_dan_disaring(self):
        import deteksi
        deteksi._infer = None
        self.assertEqual(deteksi.get_inferensi()["mode_backend"], "auto")
        for salah in ("ganteng", "", "PyTorch", None, 7):
            fd, path = tempfile.mkstemp(suffix=".yaml")
            os.close(fd)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"model_live: best.pt\nmode_backend: {salah}\n")
                inf = deteksi.get_inferensi(path=path)
                self.assertEqual(inf["mode_backend"], "auto", salah)
            finally:
                os.remove(path)

    def test_auto_gpu_memakai_pt(self):
        self.d._cuda_tersedia = True
        self.assertTrue(self.d.backend_live("auto", ada_cuda=True).endswith(".pt"))

    def test_auto_cpu_memakai_onnx(self):
        self.d._cuda_tersedia = False
        nama = self.d.backend_live("auto", ada_cuda=False)
        self.assertTrue(nama.endswith(".onnx"), nama)
        # kembar .onnx harus benar-benar ada di disk (bukan nama karangan)
        self.assertTrue((self.d.WEIGHTS_DIR / nama).is_file(), nama)

    def test_paksa_pt_dan_onnx(self):
        """pt/onnx mengabaikan status CUDA; nilai tak sah -> auto."""
        self.d._cuda_tersedia = True
        self.assertTrue(self.d.backend_live("pt", ada_cuda=True).endswith(".pt"))
        self.assertTrue(self.d.backend_live("pt", ada_cuda=False).endswith(".pt"))
        self.assertTrue(self.d.backend_live("onnx", ada_cuda=True).endswith(".onnx"))
        # tak sah -> auto -> ikut CUDA (True di sini)
        self.assertTrue(self.d.backend_live("ngawur", ada_cuda=True).endswith(".pt"))

    def test_config_model_live_tidak_ikut_berubah(self):
        """Auto-hanya-live tidak boleh menyentuh nilai config / resolve_model."""
        import deteksi
        deteksi._infer = None
        self.d._cuda_tersedia = False  # CPU: jalur live -> onnx
        self.assertEqual(deteksi.get_inferensi()["model_live"], "best.pt")
        self.assertEqual(deteksi.resolve_model(kunci="model_live").name, "best.pt")
        self.assertEqual(deteksi.resolve_model(kunci="model_gambar").name, "best.pt")
        self.assertTrue(deteksi.nama_model_live().endswith(".onnx"))

    def test_hilang_tetap_pt_bukan_error(self):
        """Kembar .onnx tidak ada -> balik ke .pt (jangan sampai request 500).

        Diuji lewat WEIGHTS_DIR sementara yang hanya berisi best.pt, supaya
        bobot asli tidak disentuh.
        """
        import deteksi
        deteksi._infer = None
        bobot = tempfile.mkdtemp(prefix="jp-bobot-")
        shutil.copyfile(str(self.d.WEIGHTS_DIR / "best.pt"),
                        os.path.join(bobot, "best.pt"))
        asli_dir = self.d.WEIGHTS_DIR
        try:
            self.d.WEIGHTS_DIR = Path(bobot)
            for mode, cuda in (("auto", False), ("onnx", False),
                               ("onnx", True)):
                nama = self.d.backend_live(mode, ada_cuda=cuda)
                self.assertTrue(nama.endswith(".pt"), (mode, cuda, nama))
        finally:
            self.d.WEIGHTS_DIR = asli_dir
            shutil.rmtree(bobot, ignore_errors=True)

    def test_ringkasan_perangkat_ada_kunci(self):
        p = self.d.ringkasan_perangkat()
        for k in ("cuda", "gpu", "mode_backend", "backend_live"):
            self.assertIn(k, p)
        self.assertIn(p["mode_backend"], ("auto", "pt", "onnx"))

    def test_status_sistem_bawa_perangkat(self):
        s = self.d.status_sistem()
        self.assertIn("perangkat", s)
        self.assertIn("backend_live", s["perangkat"])

    def test_fallback_selaras_dengan_yaml(self):
        """Fallback harus mencerminkan config/inferensi.yaml.

        Kalau berbeda, mode degradasi diam-diam mengubah perilaku:
        tta=False menurunkan recall, imgsz_live=960 memperlambat live,
        model_gambar/model_live yang beda memuat bobot keliru, dsb.
        Semua kunci (termasuk dict bersarang) diperiksa, bukan hanya sebagian.
        """
        import deteksi
        import yaml as _yaml
        with open(os.path.join(ROOT, "config", "inferensi.yaml"), encoding="utf-8") as f:
            nyata = _yaml.safe_load(f) or {}
        fb = deteksi._INFER_FALLBACK

        def cek(jalur, a, b):
            if isinstance(a, dict):
                self.assertIsInstance(b, dict, f"{jalur}: fallback dict, yaml bukan")
                for kk in a:
                    self.assertIn(kk, b, f"{jalur}.{kk}: tidak ada di config")
                    cek(f"{jalur}.{kk}", a[kk], b[kk])
            else:
                self.assertEqual(a, b, f"{jalur}: fallback {a!r} != yaml {b!r}")

        for k, v in fb.items():
            with self.subTest(kunci=k):
                self.assertIn(k, nyata, f"{k}: tidak ada di config/inferensi.yaml")
                cek(k, v, nyata[k])


class TestKanonikKelas(unittest.TestCase):
    """Nama kelas model (spasi & kapital) harus dinormalkan ke bentuk kanonik.

    Regresi: bobot RDD2022 memuat 'longitudinal crack' / 'Pothole'; tanpa
    normalisasi, toleransi per kelas mati (KeyError -> slider) dan UI
    menampilkan nama kelas mentah.
    """

    def test_kanonik_nama(self):
        import deteksi
        self.assertEqual(deteksi.kanonik_kelas("longitudinal crack"),
                         "longitudinal_crack")
        self.assertEqual(deteksi.kanonik_kelas("Pothole"), "pothole")
        self.assertEqual(deteksi.kanonik_kelas(" other  corruption "),
                         "other_corruption")
        self.assertEqual(deteksi.kanonik_kelas("longitudinal_crack"),
                         "longitudinal_crack")  # idempoten

    def test_nama_kelas_terima_dict_dan_list(self):
        import deteksi
        self.assertEqual(deteksi.nama_kelas({4: "Pothole"}, 4), "pothole")
        self.assertEqual(deteksi.nama_kelas(["a b", "c d"], 1), "c_d")

    def test_kanonik_names_tak_mengubah_input(self):
        import deteksi
        asli = {0: "longitudinal crack", 4: "Pothole"}
        self.assertEqual(deteksi._kanonik_names(asli),
                         {0: "longitudinal_crack", 4: "pothole"})
        self.assertEqual(asli, {0: "longitudinal crack", 4: "Pothole"})

    def test_toleransi_berlaku_setelah_normalisasi(self):
        import deteksi
        tol = {"longitudinal_crack": 0.13, "pothole": 0.08}
        # nama kanonik -> slider dikurangi toleransi (0,25 - 0,13)
        self.assertAlmostEqual(
            deteksi.ambang_efektif(deteksi.kanonik_kelas("longitudinal crack"),
                                   0.25, tol), 0.12)
        # nama mentah -> tak cocok -> tetap slider (bukti bug lama)
        self.assertAlmostEqual(
            deteksi.ambang_efektif("longitudinal crack", 0.25, tol), 0.25)


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

    def test_retak_near_square_ditolak(self):
        from deteksi import masuk_akal
        batas = dict(self.BATAS, rasio_aspek_min_retak=1.5)
        # longitudinal/transversal near-square -> false positive -> tolak
        self.assertFalse(masuk_akal({"kelas": "longitudinal_crack", "panjang_cm": 100,
                                     "lebar_cm": 90, "luas_m2": 0.9}, batas))
        self.assertFalse(masuk_akal({"kelas": "transverse_crack", "panjang_cm": 50,
                                     "lebar_cm": 45, "luas_m2": 0.225}, batas))
        # tepat di ambang -> lolos
        self.assertTrue(masuk_akal({"kelas": "longitudinal_crack", "panjang_cm": 45,
                                    "lebar_cm": 30, "luas_m2": 0.135}, batas))
        # alligator & pothole boleh square -> lolos
        self.assertTrue(masuk_akal({"kelas": "alligator_crack", "panjang_cm": 80,
                                    "lebar_cm": 75, "luas_m2": 0.6}, batas))
        self.assertTrue(masuk_akal({"kelas": "pothole", "panjang_cm": 40,
                                    "lebar_cm": 38, "luas_m2": 0.152}, batas))


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
        self.assertEqual(snap["disaring"],
                         {"ambang": 1, "ukuran": 0, "aspek": 0, "frame": 1})


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


class TestTanpaTilingOtomatis(unittest.TestCase):
    """Regresi: pemicu 'mode teliti otomatis' untuk gambar besar sudah DICABUT.

    Pemicu itu (sisi > imgsz x 2) pernah menyalakan tiling otomatis di setiap
    foto > 1920 px. Diukur di BPID (161 gambar berlabel, IoU 0,5, pothole):
    tiling 640->960 memberi F1 0,011 vs 0,431 untuk full-frame, dengan recall
    0% pada pothole besar (>600 px). Full-frame kini berjalan di imgsz 640
    (F1 0,630), jadi tidak ada lagi alasan menyalakan tiling diam-diam.
    """

    def test_kunci_konfigurasi_otomatis_dihilangkan(self):
        import deteksi
        deteksi._infer = None
        t = deteksi.get_inferensi()["teliti"]
        for kunci in ("otomatis_aktif", "otomatis_ambang"):
            self.assertNotIn(kunci, t)
        # Kunci yang masih dipakai mode teliti manual tetap ada.
        self.assertEqual(t["tile"], 640)
        self.assertEqual(t["imgsz"], 960)

    def test_fungsi_pemicu_tidak_ada_lagi(self):
        import deteksi
        self.assertFalse(hasattr(deteksi, "perlu_teliti_otomatis"))

    def test_gambar_besar_tidak_lagi_otomatis(self):
        """Foto 2200 px tetap jalur full-frame: teliti=False & kunci tak ada."""
        import cv2
        import numpy as np
        import deteksi
        deteksi.get_model(kunci="model_gambar")
        ok, buf = cv2.imencode(".jpg", np.full((2200, 2200, 3), 128,
                                                dtype=np.uint8))
        self.assertTrue(ok)
        deteksi._infer = None
        out = deteksi.analisis_gambar(buf.tobytes(), conf=0.9, imgsz=160)
        self.assertFalse(out["teliti"])
        self.assertNotIn("teliti_otomatis", out)
        self.assertNotIn("tepi_tile", out["disaring"])  # bukan jalur tiling

    def test_teliti_manual_tetap_bisa(self):
        """Mode teliti masih hidup sebagai alat eksperimen (dicentang manual)."""
        import cv2
        import numpy as np
        import deteksi
        deteksi.get_model(kunci="model_gambar")
        ok, buf = cv2.imencode(".jpg", np.full((900, 900, 3), 128,
                                                dtype=np.uint8))
        self.assertTrue(ok)
        deteksi._infer = None
        out = deteksi.analisis_gambar(buf.tobytes(), conf=0.9, imgsz=160,
                                       teliti=True)
        self.assertTrue(out["teliti"])
        self.assertIsInstance(out["rows"], list)

    def test_imgsz_gambar_default_640(self):
        import deteksi
        deteksi._infer = None
        self.assertEqual(deteksi.get_inferensi()["imgsz_gambar"], 640)

    def test_toleransi_pothole_tidak_dilonggarkan(self):
        """pothole 0 (18 Okt 2026): lowering 0,08 menurunkan precision ke 0,32."""
        import deteksi
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        self.assertEqual(inf["toleransi_kelas"]["pothole"], 0.0)
        self.assertAlmostEqual(
            deteksi.ambang_efektif("pothole", 0.25,
                                    inf["toleransi_kelas"]), 0.25)


class TestGabungFragmen(unittest.TestCase):
    def _row(self, kelas, conf, box):
        return {"kelas": kelas, "conf": conf, "box": box,
                "panjang_cm": 10, "lebar_cm": 10, "luas_m2": 0.01,
                "luas_cm2": 100, "tebal_asumsi_cm": 5, "bahan": "b",
                "skor_prioritas": 11, "dasar": "d",
                "severity": "Ringan"}

    def test_fragmen_bersentuhan_melebur_dan_dihitung_ulang(self):
        from deteksi import gabung_fragmen
        rows = [self._row("pothole", 0.8, [0, 0, 100, 100]),
                self._row("pothole", 0.6, [20, 20, 120, 120]),
                self._row("pothole", 0.7, [500, 500, 600, 600])]
        baru, n = gabung_fragmen(rows)
        self.assertEqual(n, 1)
        self.assertEqual(len(baru), 2)
        g = [r for r in baru if r.get("fragmen") == 2][0]
        self.assertEqual(g["box"], [0, 0, 120, 120])
        self.assertEqual(g["conf"], 0.8)  # pemenang
        # severity/skor dihitung ulang dari box gabungan (bukan jumlah fragmen)
        self.assertNotEqual(g["luas_m2"], 0.01)

    def test_pothole_berdampingan_tidak_boleh_dilebur(self):
        """Regresi 18 Okt 2026: ambang lama (iou_min 0,05 / inter_min 0,30)
        menganggap dua pothole yang bersentuhan ringan sebagai SATU kerusakan lalu
        menyatukannya, sehingga satu pothole ground-truth hilang dari hitungan
        (BPID: recall 0,563). Dengan 0,30/0,50 keduanya tetap terpisah.
        """
        from deteksi import gabung_fragmen
        rows = [self._row("pothole", 0.8, [0, 0, 100, 100]),
                self._row("pothole", 0.7, [40, 40, 140, 140])]
        baru, n = gabung_fragmen(rows)
        self.assertEqual(n, 0, "dua pothole berbeda tidak boleh digabung")
        self.assertEqual(len(baru), 2)
        # ...tapi kepingan yang tumpang tindih jelas tetap boleh digabung.
        rows2 = [self._row("pothole", 0.8, [0, 0, 100, 100]),
                 self._row("pothole", 0.7, [10, 10, 110, 110])]
        _baru2, n2 = gabung_fragmen(rows2)
        self.assertEqual(n2, 1)

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
        # Diperketat 18 Okt 2026 (lihat regresi pothole berdampingan).
        self.assertEqual(gf["iou_min"], 0.3)
        self.assertEqual(gf["inter_min"], 0.5)

    def test_default_conf_slider_samakan_jurnal_025(self):
        """Default slider 0,25 (31 Okt 2026): disamakan ke naskah jurnal.

        Sebelumnya 0,30 (18 Okt 2026; F1 terbaik pada sapuan BPID).
        Diganti bukan karena hasil ukurnya berubah, melainkan agar kode
        sama dengan ambang operasi yang tertulis di naskah.
        """
        import inspect
        import web.app as app_mod
        self.assertEqual(app_mod.CONF_DEFAULT, 0.25)
        import deteksi
        # Default di tanda tangan fungsi WAJIB sama dengan CONF_DEFAULT app;
        # kalau melenceng, pemanggil programatis diam-diam memakai ambang lain
        # (pernah kejadian: analisis_gambar() tertinggal di 0,25 saat app
        # sempat naik ke 0,30).
        tanda = inspect.signature(deteksi.analisis_gambar).parameters["conf"]
        self.assertAlmostEqual(tanda.default, app_mod.CONF_DEFAULT)
        deteksi._infer = None
        # ambang efektif per kelas = slider - toleransi
        tol = deteksi.get_inferensi()["toleransi_kelas"]
        self.assertAlmostEqual(deteksi.ambang_efektif("pothole", 0.30, tol), 0.30)
        self.assertAlmostEqual(deteksi.ambang_efektif("longitudinal_crack",
                                                       0.30, tol), 0.30)


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
             "luas_cm2": 100, "luas_m2": 0.01, "skor_prioritas": 33,
             "dasar": "d", "bahan": "b"},
            {"kelas": "longitudinal_crack", "conf": 0.5, "severity": "Ringan",
             "box": [0, 0, 400, 8], "panjang_cm": 50, "lebar_cm": 1,
             "luas_cm2": 50, "luas_m2": 0.005, "skor_prioritas": 33,
             "dasar": "d", "bahan": "b"},
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
        # skor dihitung ulang dari severity Berat -> 100 (bukan angka asal 33)
        self.assertNotEqual(r["skor_prioritas"], 33)
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
            pass
            r = c.post("/api/verifikasi", json={"rows": self._rows(),
                                                "hapus": [0],
                                                "severity": {"1": "Berat"}})
            self.assertEqual(r.status_code, 200)
            j = r.get_json()
            self.assertEqual(len(j["rows"]), 1)
            self.assertEqual(j["info"]["total"], 2)
            self.assertIn("total", j)

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


_BOBOT_ADA = all(
    os.path.isfile(os.path.join(ROOT, "app", "weights", n))
    for n in ("best.pt", "best.onnx"))


@unittest.skipUnless(_BOBOT_ADA, "bobot model tidak ada di app/weights/")
class TestBackendGanda(unittest.TestCase):
    def test_resolve_default_dan_fallback(self):
        import deteksi
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        self.assertEqual(inf["model_gambar"], "best.pt")
        self.assertEqual(inf["model_live"], "best.pt")
        self.assertTrue(deteksi.resolve_model(kunci="model_gambar").name.endswith(".pt"))
        self.assertTrue(deteksi.resolve_model(kunci="model_live").name.endswith(".pt"))
        # hilang / traversal -> fallback best.pt
        self.assertEqual(deteksi.resolve_model("tak-ada.onnx").name, "best.pt")
        self.assertEqual(deteksi.resolve_model("../x.pt").name, "best.pt")
        self.assertEqual(deteksi.resolve_model("jahat.exe").name, "best.pt")

    def test_nama_model(self):
        import deteksi
        deteksi._infer = None
        self.assertEqual(deteksi.nama_model(kunci="model_gambar"), "best.pt")
        self.assertEqual(deteksi.nama_model(kunci="model_live"), "best.pt")

    def test_model_gambar_kelas_benar(self):
        import deteksi
        m = deteksi.get_model(kunci="model_gambar")
        self.assertEqual(deteksi.nama_kelas(m.names, 4), "pothole")
        self.assertEqual(len(m.names), 5)

    def test_get_model_cache_per_path(self):
        import deteksi
        onnx = str(deteksi.WEIGHTS_DIR / "best.onnx")
        m1 = deteksi.get_model(onnx)
        m2 = deteksi.get_model(onnx)
        self.assertIs(m1, m2)
        # nama mentah bobot berkapital/spasi ("Pothole"); bandingkan bentuk kanonik
        kanonik = [deteksi.kanonik_kelas(v) for v in m1.names.values()]
        self.assertIn("pothole", kanonik)

    def test_onnx_inferensi_kecil(self):
        import numpy as np
        import deteksi
        m = deteksi.get_model(str(deteksi.WEIGHTS_DIR / "best.onnx"))
        img = np.zeros((96, 96, 3), dtype=np.uint8)
        r = m.predict(img, conf=0.25, imgsz=96, device="cpu", verbose=False)[0]
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
        deteksi.get_model(str(deteksi.WEIGHTS_DIR / "best.onnx"))
        ok, buf = cv2.imencode(".jpg", np.zeros((160, 160, 3),
                                                dtype=np.uint8) + 128)
        self.assertTrue(ok)
        raw = buf.tobytes()
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        # model_kedua beda berkas (best.pt + best.onnx) -> jalur ensemble aktif
        inf["ensemble"] = {"aktif": True, "model_kedua": "best.onnx",
                           "iou": 0.5, "metode": "wbf"}
        try:
            h = deteksi.analisis_gambar(raw, conf=0.9, imgsz=160)
            self.assertIn("+", h["model"])
            self.assertIn("ensemble", h["disaring"])
            self.assertIsInstance(h["rows"], list)
            # model_kedua == utama (best.pt) -> jalur tunggal
            inf["ensemble"] = {"aktif": True, "model_kedua": "best.pt",
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



class TestSkorPrioritas(unittest.TestCase):
    def test_bobot_severity(self):
        from prioritas import skor
        self.assertEqual(skor({"severity": "Ringan", "luas_cm2": 10000})["skor_prioritas"], 33)
        self.assertEqual(skor({"severity": "Sedang", "luas_cm2": 10000})["skor_prioritas"], 67)
        self.assertEqual(skor({"severity": "Berat", "luas_cm2": 10000})["skor_prioritas"], 100)

    def test_skor_tidak_tergantung_luas(self):
        from prioritas import skor
        # revisi M8: skor hanya dari severity; luas tidak memengaruhi skor
        self.assertEqual(skor({"severity": "Berat", "luas_cm2": 50000})["skor_prioritas"], 100)
        self.assertEqual(skor({"severity": "Berat", "luas_cm2": 1000})["skor_prioritas"], 100)
        self.assertEqual(skor({"severity": "Ringan", "luas_cm2": 1})["skor_prioritas"], 33)
        self.assertEqual(skor({"severity": "Sedang"})["skor_prioritas"], 67)

    def test_rentang_0_100(self):
        from prioritas import skor
        for sev in ("Ringan", "Sedang", "Berat"):
            for luas in (0, 1, 500, 9999, 10000, 10**9):
                v = skor({"severity": sev, "luas_cm2": luas})["skor_prioritas"]
                self.assertGreaterEqual(v, 0)
                self.assertLessEqual(v, 100)

    def test_total_prioritas(self):
        from prioritas import total_prioritas
        rows = [{"skor_prioritas": 100}, {"skor_prioritas": 33}, {}]
        self.assertEqual(total_prioritas(rows), 133)


class TestBatasUpload(unittest.TestCase):
    def test_detect_tolak_gambar_raksasa(self):
        import io
        import sys
        import web.app as app_mod
        app = app_mod.create_app()
        app.config["TESTING"] = True
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


class TestWorkerInferensi(unittest.TestCase):
    """Anti-gantung worker inferensi GPU.

    Regresi: `balasan.get()` tanpa timeout membuat /api/detect menggantung
    selamanya bila worker mati. Simulasi tanpa model/kamera: worker diganti
    thread palsu sehingga test tidak memuat bobot maupun menyentuh CUDA.
    """

    def setUp(self):
        import deteksi
        self.d = deteksi
        self._orig = (deteksi._thread_pekerja, deteksi._antrean_pekerja,
                      deteksi._pastikan_pekerja)

    def tearDown(self):
        (self.d._thread_pekerja, self.d._antrean_pekerja,
         self.d._pastikan_pekerja) = self._orig

    def _thread_mati(self):
        import threading
        t = threading.Thread(target=lambda: None)
        t.start()
        t.join()
        return t

    def test_worker_mati_gagal_cepat_bukan_menggantung(self):
        import queue
        import time
        d = self.d
        d._pastikan_pekerja = lambda: None   # jangan lahirkan worker nyata
        d._thread_pekerja = self._thread_mati()
        d._antrean_pekerja = queue.Queue()   # tak ada yang melayani
        t0 = time.time()
        with self.assertRaises(d.WorkerInferensiMati):
            d.analisis_gambar_terjadwal(b"\xff\xd8\xff")
        self.assertLess(time.time() - t0, 5.0, "harus gagal-cepat")

    def test_jalur_normal_mengembalikan_hasil(self):
        import queue
        import threading
        d = self.d
        d._pastikan_pekerja = lambda: None
        q = queue.Queue()
        berhenti = threading.Event()

        def worker():
            while not berhenti.is_set():
                try:
                    fn, args, kwargs, balasan = q.get(timeout=0.1)
                except queue.Empty:
                    continue
                balasan.put((True, fn(*args, **kwargs)))

        th = threading.Thread(target=worker, daemon=True)
        d._antrean_pekerja = q
        d._thread_pekerja = th
        th.start()
        asli = d.analisis_gambar
        d.analisis_gambar = lambda *a, **k: {"rows": [], "total": 0}
        try:
            out = d.analisis_gambar_terjadwal(b"x", conf=0.25)
        finally:
            d.analisis_gambar = asli
            berhenti.set()
        self.assertEqual(out["total"], 0)

    def test_pastikan_pekerja_lahirkan_ulang(self):
        import unittest.mock as mock
        d = self.d
        mati = self._thread_mati()
        dibuat = []

        class Palsu:
            """Thread palsu: tak menyentuh memori/OS, cukup catat start()."""
            def __init__(self, target=None, args=(), name=None, daemon=None):
                self.target, self.args = target, args
                self._alive = False
                dibuat.append(self)

            def start(self):
                self._alive = True

            def is_alive(self):
                return self._alive

        d._thread_pekerja = mati
        with mock.patch.object(d.threading, "Thread", Palsu):
            d._pastikan_pekerja()
        self.assertEqual(len(dibuat), 1, "worker baru harus dibuat")
        self.assertIsNot(d._thread_pekerja, mati)
        self.assertTrue(d._thread_pekerja.is_alive())

    def test_route_detect_worker_mati_503(self):
        import io
        import unittest.mock as mock
        import web.app as app_mod
        app = app_mod.create_app()
        app.config["TESTING"] = True
        c = app.test_client()
        data = {"gambar": (io.BytesIO(b"\xff\xd8\xff" + b"0" * 64), "x.jpg")}
        with mock.patch.object(
                app_mod, "analisis_gambar_terjadwal",
                side_effect=app_mod.WorkerInferensiMati("mati")):
            r = c.post("/api/detect", data=data,
                       content_type="multipart/form-data")
        self.assertEqual(r.status_code, 503)
        self.assertIn("error", r.get_json())

    # --- Regresi 18 Okt 2026: kehabisan RAM tidak boleh dilayani sebagai 500.
    # Terukur nyata saat pengukuran BPID: RAM habis -> MemoryError saat
    # f.read(), dan cv2.error "Insufficient memory" saat decode 12 MP. Tanpa
    # penanganan ini klien mendapat halaman HTML 500 dari debugger dan tidak
    # tahu itu masalah sementara, bukan gambar rusak.

    def test_route_detect_memoryerror_503(self):
        import io
        import unittest.mock as mock
        import web.app as app_mod
        app = app_mod.create_app()
        app.config["TESTING"] = True
        c = app.test_client()
        data = {"gambar": (io.BytesIO(b"\xff\xd8\xff" + b"0" * 64), "x.jpg")}
        with mock.patch.object(app_mod, "analisis_gambar_terjadwal",
                               side_effect=MemoryError()):
            r = c.post("/api/detect", data=data,
                       content_type="multipart/form-data")
        self.assertEqual(r.status_code, 503)
        self.assertIn("memori", r.get_json()["error"].lower())

    def test_route_detect_opencv_oom_503(self):
        import io
        import unittest.mock as mock
        import web.app as app_mod
        app = app_mod.create_app()
        app.config["TESTING"] = True
        c = app.test_client()
        data = {"gambar": (io.BytesIO(b"\xff\xd8\xff" + b"0" * 64), "x.jpg")}
        with mock.patch.object(
                app_mod, "analisis_gambar_terjadwal",
                side_effect=RuntimeError(
                    "OpenCV(5.0.0) alloc.cpp:73: (-4:Insufficient memory)")):
            r = c.post("/api/detect", data=data,
                       content_type="multipart/form-data")
        self.assertEqual(r.status_code, 503)

    def test_kurang_memori_mengenali_bentuknya(self):
        import web.app as app_mod
        self.assertTrue(app_mod._kurang_memori(MemoryError()))
        self.assertTrue(app_mod._kurang_memori(
            RuntimeError("(-4:Insufficient memory) Failed to allocate")))
        self.assertTrue(app_mod._kurang_memori(
            RuntimeError("cv::OutOfMemoryError")))
        # Jangan salah tangkap: gambar rusak & worker mati tetap 400/503 lain.
        self.assertFalse(app_mod._kurang_memori(
            ValueError("Berkas bukan gambar yang valid (JPG/PNG).")))
        self.assertFalse(app_mod._kurang_memori(
            app_mod.WorkerInferensiMati("mati")))
        self.assertFalse(app_mod._kurang_memori(RuntimeError("shape mismatch")))


class TestNanGuard(unittest.TestCase):
    """Regresi bug FP16/TTA 2026-10-17: box NaN tidak boleh lolos ke pengguna.

    NaN berasal dari overflow FP16 (half=True + TTA @imgsz 960). Dampaknya bukan
    sekadar "satu box aneh": wbf_gabung melebur dengan rata-rata berbobot
    sehingga NaN menulari temuan asli, lalu masuk_akal() melaporkannya sebagai
    "ukuran tidak masuk akal" (menyesatkan) dan NaN bisa bocor ke JSON.
    """

    @staticmethod
    def _row(conf=0.9, box=(0, 0, 100, 100)):
        return {"kelas": "pothole", "conf": conf, "box": list(box),
                "panjang_cm": 10, "lebar_cm": 10, "luas_m2": 0.01}

    def test_saring_rows_hitung_rusak_bukan_ukuran(self):
        from deteksi import saring_rows
        nan = float("nan")
        rows = [self._row(0.9, (nan, nan, nan, nan)),
                self._row(0.8, (0, 0, 100, 100))]
        ok, info = saring_rows(rows, 0.25, {}, None)
        self.assertEqual(len(ok), 1)
        self.assertEqual(info["rusak"], 1)
        self.assertEqual(info["ukuran"], 0)  # dulu salah masuk ke sini
        self.assertEqual(info["ambang"], 0)

    def test_conf_nan_dihitung_rusak(self):
        from deteksi import saring_rows
        ok, info = saring_rows([self._row(float("nan"))], 0.25, {}, None)
        self.assertEqual(ok, [])
        self.assertEqual(info["rusak"], 1)

    def test_inf_juga_dihitung_rusak(self):
        from deteksi import saring_rows
        rows = [self._row(0.9, (0, 0, float("inf"), 100))]
        ok, info = saring_rows(rows, 0.25, {}, None)
        self.assertEqual(ok, [])
        self.assertEqual(info["rusak"], 1)

    def test_cm_nan_dihitung_rusak(self):
        from deteksi import saring_rows
        r = self._row(0.9)
        r["panjang_cm"] = float("nan")
        ok, info = saring_rows([r], 0.25, {}, None)
        self.assertEqual(ok, [])
        self.assertEqual(info["rusak"], 1)

    def test_wbf_tidak_menulari_nan(self):
        from deteksi import wbf_gabung
        nan = float("nan")
        hasil = wbf_gabung([[0, 0, 100, 100], [nan, nan, nan, nan],
                            [0, 0, 100, 100]], [0.9, 0.95, 0.8], 0.5)
        self.assertTrue(hasil)
        for fb, fs, _anggota in hasil:
            self.assertTrue(all(math.isfinite(v) for v in fb))
            self.assertTrue(math.isfinite(fs))

    def test_wbf_skor_nol_tidak_menghasilkan_nan(self):
        from deteksi import wbf_gabung
        hasil = wbf_gabung([[0, 0, 10, 10], [0, 0, 10, 10]],
                           [0.0, 0.0], 0.5)
        self.assertTrue(hasil)
        self.assertTrue(all(math.isfinite(v) for v in hasil[0][0]))

    def test_wbf_masukan_kosong(self):
        from deteksi import wbf_gabung
        self.assertEqual(wbf_gabung([], [], 0.5), [])


class TestHalfGambarDanGelap(unittest.TestCase):
    def tearDown(self):
        import deteksi
        deteksi._infer = None

    def test_half_gambar_default_false(self):
        import deteksi
        deteksi._infer = None
        inf = deteksi.get_inferensi()
        self.assertFalse(inf["half_gambar"])
        # Live (imgsz 640, tanpa TTA) tetap FP16 di GPU; jalur gambar tidak.
        self.assertTrue(deteksi.half_untuk("0"))
        self.assertFalse(deteksi.half_gambar_untuk("0"))
        self.assertFalse(deteksi.half_gambar_untuk("cpu"))

    def test_half_gambar_bisa_dinyalakan(self):
        import deteksi
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                         encoding="utf-8") as f:
            f.write("half_gambar: true\n")
            tmp = f.name
        try:
            self.assertTrue(deteksi.get_inferensi(tmp)["half_gambar"])
        finally:
            os.remove(tmp)
            deteksi._infer = None

    def test_fallback_tanpa_kunci_half_gambar(self):
        import deteksi
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                         encoding="utf-8") as f:
            f.write("imgsz_gambar: 960\n")
            tmp = f.name
        try:
            self.assertFalse(deteksi.get_inferensi(tmp)["half_gambar"])
        finally:
            os.remove(tmp)
            deteksi._infer = None

    def test_deteksi_gelap(self):
        import numpy as np
        import deteksi
        hitam = np.zeros((40, 40, 3), dtype=np.uint8)
        putih = np.full((40, 40, 3), 255, dtype=np.uint8)
        self.assertTrue(deteksi.deteksi_gelap(hitam))
        self.assertFalse(deteksi.deteksi_gelap(putih))
        self.assertFalse(deteksi.deteksi_gelap(putih, ambang=0))


class TestSkalaProsesGambar(unittest.TestCase):
    """maks_sisi_proses: analisis di gambar kecil, box tetap koordinat ASLI.

    Uji ini mengunci keputusan desain yang paling mudah rusak diam-diam: bila
    box tidak dikembalikan ke ruang gambar asli, app/severity.py menghitung
    dimensi terlalu kecil (pixels_per_cm menganggap 1 cm = 8 px pada gambar
    asli), sehingga severity turun dan verifikasi operator salah hitung —
    tanpa error apa pun. Bukti perilaku agregatnya ada di §6e.
    """

    def _analisis(self, maks, teliti=False, hw=(1600, 1200)):
        import cv2
        import numpy as np
        import deteksi
        deteksi.get_model(kunci="model_gambar")
        ok, buf = cv2.imencode(".jpg", np.full((hw[0], hw[1], 3), 128,
                                               dtype=np.uint8))
        self.assertTrue(ok)
        asli = deteksi.get_inferensi
        deteksi.get_inferensi = lambda path=None: {**asli(path),
                                                   "maks_sisi_proses": maks}
        try:
            return deteksi.analisis_gambar(buf.tobytes(), conf=0.9, imgsz=160,
                                           teliti=teliti)
        finally:
            deteksi.get_inferensi = asli

    def test_maks_sisi_proses_diklem(self):
        import deteksi
        for isi, harap in (("99999", 4096), ("100", 320), ("-5", 0),
                           ("0", 0), ("abc", 0)):
            with self.subTest(isi=isi):
                fd, path = tempfile.mkstemp(suffix=".yaml")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write("maks_sisi_proses: %s\n" % isi)
                    inf = deteksi.get_inferensi(path=path)
                    self.assertEqual(inf["maks_sisi_proses"], harap)
                finally:
                    os.remove(path)

    def test_skala_box_mengembalikan_koordinat_ke_gambar_asli(self):
        import deteksi

        class B:
            def __init__(self, xyxy, cls, conf):
                self.xyxy, self.cls, self.conf = [xyxy], [cls], [conf]

        class R:
            boxes = [B([100.0, 200.0, 300.0, 400.0], 4, 0.9)]

        names = {4: "pothole"}
        tanpa = deteksi.proses_detections(R, names)
        self.assertEqual(tanpa[0]["box"], [100.0, 200.0, 300.0, 400.0])
        dobel = deteksi.proses_detections(R, names, skala_box=2.0)
        self.assertEqual(dobel[0]["box"], [200.0, 400.0, 600.0, 800.0])
        # Dimensi fisik ikut membesar — buktinya kalibrasi px/cm tak mengecil.
        self.assertAlmostEqual(dobel[0]["panjang_cm"],
                               2 * tanpa[0]["panjang_cm"], places=1)

    def test_maks_0_analisis_resolusi_asli(self):
        out = self._analisis(0)
        self.assertEqual(out["disaring"]["skala_proses"], 1.0)

    def test_gambar_besar_diperkecil_dan_bukti_ikut_kecil(self):
        import cv2
        import numpy as np
        out = self._analisis(800, hw=(1600, 1200))
        self.assertAlmostEqual(out["disaring"]["skala_proses"], 0.5, places=2)
        buf = cv2.imdecode(np.frombuffer(out["gambar_jpg"], np.uint8),
                           cv2.IMREAD_COLOR)
        self.assertEqual(max(buf.shape[:2]), 800)

    def test_teliti_selalu_resolusi_asli(self):
        out = self._analisis(800, teliti=True, hw=(900, 1200))
        self.assertTrue(out["teliti"])
        self.assertEqual(out["disaring"]["skala_proses"], 1.0)


if __name__ == "__main__":
    unittest.main()
