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


class FakeCapStatis(FakeCap):
    """VideoCapture palsu: frame IDENTIK terus (adegan diam)."""

    def read(self):
        self._n += 1
        time.sleep(0.02)
        return True, np.full((480, 640, 3), 128, np.uint8)


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
        self.track_threads = []     # nama thread tiap panggilan track (termasuk warmup)

    def track(self, img, **k):
        import threading
        self.calls += 1
        self.track_threads.append(threading.current_thread().name)
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
        # Hangatkan sekali (sinkron) lalu nolkan hitungan: test mengukur
        # panggilan inferensi SESI saja, bukan panggilan warmup.
        self.m.panaskan()
        self.model.calls = 0

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

    def test_frame_diff_dimatikan_untuk_video(self):
        """Sumber video harus tetap diinferensi walau frame nyaris sama."""
        self._pasang(model_delay=0.01)
        self.streaming.cv2.VideoCapture = FakeCapStatis
        m = self.m
        try:
            m.start("file", "x.mp4", frame_skip=1)
            time.sleep(0.6)
            self.assertGreaterEqual(
                self.model.calls, 4,
                "frame-diff salah aktif untuk sumber video (demo jadi beku)")
        finally:
            self._lepas(m)

    def test_frame_diff_aktif_untuk_webcam_diam(self):
        """Adegan webcam diam -> inferensi di-skip (hemat GPU), bukan diulang."""
        self._pasang(model_delay=0.01)
        self.streaming.cv2.VideoCapture = FakeCapStatis
        m = self.m
        try:
            m.start("webcam", 0, frame_skip=1)
            time.sleep(0.6)
            self.assertLessEqual(
                self.model.calls, 2,
                "frame-diff tak menahan inferensi berulang di adegan diam")
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
                                         "cam_fps": 5000, "min_frames": 0}}, f)
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
                  "frame_diff_threshold", "jpeg_quality", "display_width",
                  "cam_width", "cam_height", "cam_fps"):
            self.assertIn(k, deteksi._INFER_FALLBACK["live"])


class TestInferPersisten(_StreamCase):
    """Thread inferensi live harus PERSISTEN antar sesi (biaya CUDA sekali)."""

    def test_warmup_jalan_di_thread_persisten(self):
        self._pasang(model_delay=0.02)
        m = self.m
        try:
            self.assertTrue(m._infer_siap.is_set(), "warmup tak selesai")
            self.assertTrue(m._infer_persisten.is_alive())
            self.assertGreaterEqual(len(self.model.track_threads), 1,
                                    "warmup track tak dijalankan")
            for nama in self.model.track_threads:
                self.assertEqual(nama, "inferensi-live",
                                 "warmup harus di thread inferensi, bukan main")
        finally:
            self._lepas(m)

    def test_thread_dipakai_ulang_antar_sesi(self):
        self._pasang(model_delay=0.02)
        m = self.m
        try:
            m.start("webcam", 0)
            time.sleep(0.2)
            t1 = m._infer_persisten
            self.assertIsNotNone(t1)
            m.stop()
            m.start("webcam", 0)
            time.sleep(0.2)
            self.assertIs(m._infer_persisten, t1,
                          "thread inferensi dibuat ulang tiap sesi")
            self.assertTrue(t1.is_alive())
        finally:
            self._lepas(m)

    def test_stop_mengembalikan_ke_idle(self):
        self._pasang(model_delay=0.02)
        m = self.m
        try:
            m.panaskan()
            m.start("webcam", 0)
            time.sleep(0.15)
            m.stop()
            self.assertTrue(m._infer_idle.is_set(),
                            "thread inferensi tak kembali menganggur")
            self.assertFalse(m._infer_sesi.is_set())
        finally:
            self._lepas(m)


class TestSnapshotBerbox(_StreamCase):
    """Foto riwayat live memakai frame ber-box terakhir bila ada."""

    def test_snapshot_pilih_frame_berbox(self):
        import base64
        self._pasang()
        m = self.m
        try:
            m.latest_jpg = b"frame-biasa"
            m.latest_jpg_berbox = b"frame-berbox"
            snap = m.snapshot()
            self.assertEqual(base64.b64decode(snap["image_b64"]), b"frame-berbox")
            # Fallback: tanpa berbox -> frame biasa.
            m.latest_jpg_berbox = None
            snap = m.snapshot()
            self.assertEqual(base64.b64decode(snap["image_b64"]), b"frame-biasa")
        finally:
            self._lepas(m)

    def test_reset_state_membersihkan_berbox(self):
        self._pasang()
        m = self.m
        try:
            m.latest_jpg_berbox = b"frame-berbox"
            m.reset_state()
            self.assertIsNone(m.latest_jpg_berbox)
            self.assertIsNone(m.latest_jpg)
        finally:
            self._lepas(m)


if __name__ == "__main__":
    unittest.main()
