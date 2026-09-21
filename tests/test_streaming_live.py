"""Regresi optimasi live stream (decouple capture/inferensi/compose).

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_streaming_live -v

Tanpa kamera/model nyata: cv2.VideoCapture & model live di-monkeypatch.
"""
import os
import sys
import tempfile
import time
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WEB_DIR = os.path.join(ROOT, "web")
APP_DIR = os.path.join(ROOT, "app")
for p in (WEB_DIR, APP_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


class FakeCap:
    """VideoCapture palsu: frame solid berganti terang/gelap tiap read."""

    def __init__(self, *a, **k):
        self._n = 0

    def isOpened(self):
        return True

    def set(self, *a, **k):
        return True

    def get(self, prop):
        try:
            import cv2
            if prop == cv2.CAP_PROP_FPS:
                return 30.0
        except Exception:
            pass
        return 0.0

    def read(self):
        self._n += 1
        time.sleep(0.002)  # emulasi laju kamera (~500 fps) biar tak spin gila
        img = np.zeros((480, 640, 3), np.uint8)
        img[:] = 255 if (self._n % 2 == 0) else 0
        return True, img

    def release(self):
        pass


class _NoBoxes:
    def __len__(self):
        return 0


class FakeRes:
    boxes = None


class FakeModel:
    names = {0: "pothole"}

    def __init__(self, delay=0.12):
        self.delay = delay
        self.calls = 0

    def track(self, img, **k):
        self.calls += 1
        time.sleep(self.delay)  # model lambat -> FPS inferensi rendah
        return [FakeRes()]


INFER = {
    "imgsz_live": 480, "iou": 0.5, "toleransi_kelas": {},
    "live": {"min_frames": 1, "display_fps": 30, "infer_interval": 1,
             "jpeg_quality": 72, "display_width": 640,
             "cam_width": 640, "cam_height": 480, "cam_fps": 30},
}


class _StreamCase(unittest.TestCase):
    def _pasang(self, model_delay=0.12):
        import streaming
        self.streaming = streaming
        self.model = FakeModel(model_delay)
        self._get_model = streaming.get_model
        self._get_inf = streaming.get_inferensi
        self._vcap = streaming.cv2.VideoCapture
        streaming.get_model = lambda *a, **k: self.model
        streaming.get_inferensi = lambda *a, **k: INFER
        streaming.cv2.VideoCapture = FakeCap
        self.m = streaming.StreamManager()

    def _lepas(self, m):
        try:
            m.stop()
        except Exception:
            pass
        self.streaming.get_model = self._get_model
        self.streaming.get_inferensi = self._get_inf
        self.streaming.cv2.VideoCapture = self._vcap


class TestDecouple(_StreamCase):
    def test_tampil_jauh_lebih_cepat_dari_inferensi(self):
        self._pasang(model_delay=0.12)
        m = self.m
        try:
            m.start("webcam", 0, conf=0.25, frame_skip=1)
            time.sleep(0.8)
            composes = m._latest_seq
            inits = self.model.calls
            self.assertGreaterEqual(inits, 1, "inferensi tak pernah jalan")
            # Inti decouple: compose tak menunggu inferensi.
            self.assertGreater(composes, inits,
                               f"compose={composes} tak melampaui infer={inits}")
        finally:
            self._lepas(m)

    def test_capture_simpan_hanya_frame_terbaru(self):
        self._pasang(model_delay=0.05)
        m = self.m
        try:
            m.start("webcam", 0)
            time.sleep(0.4)
            self.assertIsNotNone(m._raw_frame)
            self.assertEqual(m.n_frame, m._raw_seq)  # 1 frame terbaca = 1 seq
            self.assertGreater(m._raw_seq, 10)
        finally:
            self._lepas(m)

    def test_wait_frame_memberi_seq_baru(self):
        self._pasang(model_delay=0.05)
        m = self.m
        try:
            m.start("webcam", 0)
            _, _, s1 = m.wait_frame(-1, timeout=1.0)
            _, _, s2 = m.wait_frame(s1, timeout=1.0)
            self.assertNotEqual(s1, s2)
        finally:
            self._lepas(m)

    def test_stats_punya_fps_tampil_dan_infer(self):
        self._pasang(model_delay=0.05)
        m = self.m
        try:
            m.start("webcam", 0)
            time.sleep(0.3)
            st = m.stats()
            for k in ("fps", "fps_tampil", "fps_infer", "frame", "unik",
                      "deteksi", "running"):
                self.assertIn(k, st)
        finally:
            self._lepas(m)

    def test_restart_sesi_baru_tetap_mengalir(self):
        self._pasang(model_delay=0.05)
        m = self.m
        try:
            m.start("webcam", 0)
            time.sleep(0.25)
            m.stop()
            seq_setelah_stop = m._latest_seq
            m.start("webcam", 0)
            time.sleep(0.4)
            self.assertGreater(m._latest_seq, seq_setelah_stop,
                               "sesi baru tak memproduksi frame")
        finally:
            self._lepas(m)


class TestPresetPerforma(unittest.TestCase):
    def test_preset_mengoverride_knobs(self):
        import streaming
        self.assertIn("halus", streaming.PERFORMA)
        self.assertLess(streaming.PERFORMA["halus"]["imgsz_live"],
                        streaming.PERFORMA["akurat"]["imgsz_live"])
        self.assertGreaterEqual(streaming.PERFORMA["halus"]["display_fps"],
                                streaming.PERFORMA["akurat"]["display_fps"])


class TestClampLiveConfig(unittest.TestCase):
    def test_nilai_ekstrem_dijepit(self):
        import yaml
        import deteksi
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump({"live": {"display_fps": 9999, "infer_interval": 0,
                                         "jpeg_quality": 5, "display_width": 5,
                                         "cam_width": 99999, "cam_height": 1,
                                         "cam_fps": 5000}}, f)
            d = deteksi.get_inferensi(path=path)["live"]
            self.assertEqual(d["display_fps"], 30)
            self.assertEqual(d["infer_interval"], 1)
            self.assertEqual(d["jpeg_quality"], 40)
            self.assertEqual(d["display_width"], 320)
            self.assertEqual(d["cam_width"], 1920)
            self.assertEqual(d["cam_height"], 120)
            self.assertEqual(d["cam_fps"], 120)
            self.assertEqual(d["min_frames"], 1)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_fallback_punya_semua_key_live(self):
        import deteksi
        for k in ("min_frames", "display_fps", "infer_interval",
                  "jpeg_quality", "display_width", "cam_width",
                  "cam_height", "cam_fps"):
            self.assertIn(k, deteksi._INFER_FALLBACK["live"])


if __name__ == "__main__":
    unittest.main()
