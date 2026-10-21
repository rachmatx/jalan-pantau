"""Regresi race pada objek YOLO yang dipakai jalur gambar dan live.

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_konkurensi_model -v

Latar: saat GPU CUDA tersedia dan `mode_backend: auto`, jalur gambar
(`analisis_gambar` -> `get_model(kunci="model_gambar")`) dan jalur live
(`model_live_aktif()`) sama-sama mengarah ke `best.pt`. Bila cache hanya
berkunci path, keduanya berbagi satu instance YOLO, padahal ultralytics
menyimpan `predictor` dan `trackers` ByteTrack sebagai atribut instance.

Invariant yang dikunci test ini: kedua jalur HARUS memakai instance terpisah
walau file bobotnya sama, sehingga `predict()` (jalur gambar) tidak pernah
melihat/menimpa state tracker milik `track()` (jalur live).

Batasan: test ini membuktikan wiring produksi + hazard state via model palsu,
bukan menjalankan CUDA/ultralytics nyata.
"""
import os
import sys
import tempfile
import threading
import types
import unittest
import unittest.mock as mock
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "web"), os.path.join(ROOT, "app")):
    if p not in sys.path:
        sys.path.insert(0, p)


class Bus:
    """Event bersama lintas instance: mengunci urutan interleaving."""

    def __init__(self):
        self.predict_siap = threading.Event()
        self.track_siap = threading.Event()


class YOLOPalsu:
    """Model palsu dengan state `predictor` di instance, seperti ultralytics.

    `predict` menulis predictor lalu menunggu `track` menulis; baru setelah
    itu membaca predictor-nya sendiri. Dengan instance yang sama, pembacaan
    itu pasti melihat tulisan `track` — deterministik, tanpa bergantung timing.
    Dengan instance terpisah, masing-masing membaca tulisannya sendiri.
    """

    bus = None

    def __init__(self, path):
        self.path = str(path)
        self.names = {0: "pothole"}
        self.predictor = None
        self.terlihat = {}

    def predict(self, img, **kwargs):
        self.predictor = {"jenis": "predict", "augment": kwargs.get("augment")}
        self.bus.predict_siap.set()
        self.bus.track_siap.wait(timeout=5)
        self.terlihat["predict"] = dict(self.predictor or {})
        return []

    def track(self, img, **kwargs):
        self.bus.predict_siap.wait(timeout=5)
        self.predictor = {"jenis": "track", "persist": kwargs.get("persist")}
        self.bus.track_siap.set()
        self.terlihat["track"] = dict(self.predictor or {})
        return []


class TestModelGambarDanLiveTerpisah(unittest.TestCase):
    def setUp(self):
        import deteksi
        self.d = deteksi
        self.cfg = {
            "model_gambar": "best.pt",
            "model_live": "best.pt",
            "mode_backend": "auto",
        }

        # Cache model global: kosongkan sementara agar model palsu yang dipakai.
        self.models_asli = dict(deteksi._models)
        deteksi._models.clear()
        self.addCleanup(self._pulihkan_models)

        # Weights palsu: hasil resolve tidak bergantung pada file di repo/CI.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for nama in ("best.pt", "best.onnx"):
            Path(self.tmp.name, nama).write_bytes(b"bobot-palsu")
        p_weights = mock.patch.object(deteksi, "WEIGHTS_DIR", Path(self.tmp.name))
        p_weights.start()
        self.addCleanup(p_weights.stop)

        # get_inferensi dipalsukan supaya tes tidak bergantung config runtime.
        p_infer = mock.patch.object(
            deteksi, "get_inferensi", side_effect=lambda *a, **k: dict(self.cfg))
        p_infer.start()
        self.addCleanup(p_infer.stop)

        # Jangan impor ultralytics/torch asli saat get_model() dipanggil.
        self.ultralytics_asli = sys.modules.get("ultralytics")
        modul = types.ModuleType("ultralytics")
        modul.YOLO = YOLOPalsu
        sys.modules["ultralytics"] = modul
        self.addCleanup(self._pulihkan_ultralytics)

        YOLOPalsu.bus = Bus()

    def _pulihkan_models(self):
        self.d._models.clear()
        self.d._models.update(self.models_asli)

    def _pulihkan_ultralytics(self):
        if self.ultralytics_asli is None:
            sys.modules.pop("ultralytics", None)
        else:
            sys.modules["ultralytics"] = self.ultralytics_asli

    def _model_gambar_dan_live(self, ada_cuda):
        with mock.patch.object(self.d, "cuda_tersedia", return_value=ada_cuda):
            gambar = self.d.get_model(kunci="model_gambar")
            live = self.d.model_live_aktif()
        return gambar, live

    def test_gpu_instance_terpisah_untuk_gambar_dan_live(self):
        """Di GPU kedua jalur memakai file yang sama, tapi instance wajib beda."""
        gambar, live = self._model_gambar_dan_live(ada_cuda=True)
        self.assertIsInstance(gambar, YOLOPalsu)
        self.assertIsInstance(live, YOLOPalsu)
        self.assertEqual(
            gambar.path, live.path,
            "prasyarat: keduanya resolve ke bobot yang sama (best.pt)")
        self.assertIsNot(
            gambar, live,
            "Jalur gambar dan live berbagi instance YOLO yang sama. "
            "predict/track akan saling menimpa predictor & trackers.")

    def test_cpu_instance_terpisah(self):
        """Kontrol: di CPU live memakai best.onnx, jadi objeknya berbeda."""
        gambar, live = self._model_gambar_dan_live(ada_cuda=False)
        self.assertIsNot(gambar, live)

    def test_predict_dan_track_tidak_saling_menimpa_state(self):
        """predict di instance gambar tidak boleh melihat state track live."""
        gambar, live = self._model_gambar_dan_live(ada_cuda=True)

        t_gambar = threading.Thread(
            target=lambda: gambar.predict(None, augment=True), daemon=True)
        t_live = threading.Thread(
            target=lambda: live.track(None, persist=True), daemon=True)
        t_gambar.start()
        t_live.start()
        t_gambar.join(10)
        t_live.join(10)
        self.assertFalse(
            t_gambar.is_alive() or t_live.is_alive(),
            "thread macet: barrier interleaving tidak terpenuhi")

        self.assertEqual(
            gambar.terlihat.get("predict", {}).get("jenis"), "predict",
            "RACE: model.predict() melihat predictor milik "
            f"{gambar.terlihat.get('predict', {}).get('jenis')!r}. Jalur gambar "
            "dan live berbagi instance YOLO, sehingga state predictor/trackers "
            "saling menimpa.")
        self.assertEqual(
            live.terlihat.get("track", {}).get("jenis"), "track",
            "RACE: model.track() melihat predictor milik "
            f"{live.terlihat.get('track', {}).get('jenis')!r}.")


if __name__ == "__main__":
    unittest.main()
