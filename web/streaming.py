"""Live stream Flask: VideoCapture -> YOLO track(persist=True, ByteTrack) -> MJPEG.

Arsitektur decouple (3 peran thread) agar preview tetap halus walau inferensi
berat di CPU:

  capture worker  : baca frame kamera terbaru (buang frame basi, BUFFERSIZE=1)
  infer worker    : jalankan model.track tiap `infer_interval` frame -> tracks + overlay
  compose (loop)  : tempel overlay TERAKHIR ke frame kamera SEGAR -> JPEG, laju `display_fps`

Dulu ketiganya satu loop bloking sehingga FPS tampil == FPS inferensi (~3 FPS)
dan buffer kamera menumpuk -> patah-patah. Pengukuran/snapshot tetap dari
self.tracks (box terbaik per ID), jadi angka severity/biaya tak terpengaruh.

Satu sesi aktif dalam satu waktu (cukup untuk demo sidang + hemat CPU).
Setiap start() me-reset tracker sehingga ID mulai dari 1 lagi.
"""
import threading
import time
from pathlib import Path

import cv2

from deteksi import (ambang_efektif, cerahkan_malam, conf_prediksi, get_config,
                     get_inferensi, get_model, get_prices, kelas_mayoritas,
                     masuk_akal)
from severity import diagnose
from biaya import estimasi

WARNA = {"Ringan": (0, 180, 0), "Sedang": (0, 200, 200), "Berat": (0, 0, 220)}
MAX_TRACKS = 500  # P1: cegah OOM sesi live berjam-jam
JPEG_Q_DEFAULT = 72  # encode lebih murah dari 85 -> FPS tampil lebih tinggi
FRAME_DIFF_THRESHOLD = 0.02  # 2% berbeda = layak diinferensi ulang

# Preset "Mode Performa" (dikirim UI lewat /api/stream/start).
PERFORMA = {
    "halus": {"imgsz_live": 320, "infer_interval": 3, "display_fps": 30},
    "seimbang": {"imgsz_live": 480, "infer_interval": 2, "display_fps": 25},
    "akurat": {"imgsz_live": 640, "infer_interval": 1, "display_fps": 15},
}


class StreamManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.reset_state()

    def reset_state(self):
        self.running = False
        self.error = None
        self.source_label = "-"
        self.conf = 0.25
        self.malam = False
        self.frame_skip = 1
        self.n_frame = 0
        self.n_deteksi = 0
        self.fps_ema = 0.0        # FPS inferensi (kompat UI lama)
        self.fps_infer = 0.0
        self.fps_tampil = 0.0
        self.tracks = {}          # id -> {kelas, conf_max, box_best, area_best, frames}
        self.latest_jpg = None
        self.finished = False
        self.anotasi_aktif = True
        # --- state decouple ---
        self._performa = None
        self._live_cfg = {}
        self._raw_lock = threading.Lock()
        self._raw_frame = None
        self._raw_seq = 0
        self._last_raw_compose = -1
        self._last_raw_infer = -1
        self._boxes = []
        self._boxes_lock = threading.Lock()
        self._frame_cond = threading.Condition()
        self._latest_seq = 0
        self._t_publish = 0.0
        self._cap_thread = None
        self._infer_thread = None

    # ---- kontrol ----
    def start(self, source_type, target, conf=0.25, frame_skip=1, label=None,
              malam=False, performa=None):
        """source_type: webcam | ipcam | file. target: index/url/path.

        performa: 'halus' | 'seimbang' | 'akurat' (opsional, override imgsz +
        interval inferensi + batas FPS tampil).
        """
        self.stop()
        with self._lock:
            self.reset_state()
            self._stop = threading.Event()  # Event baru per sesi (hindari race restart)
            self.conf = min(max(float(conf), 0.05), 0.8)
            self.frame_skip = min(max(int(frame_skip), 1), 30)
            self.malam = bool(malam)
            self._performa = str(performa).lower() if performa else None
            self.running = True
            self.source_label = label or {
                "webcam": f"Webcam {target}", "ipcam": "HP IP-camera",
                "file": Path(str(target)).name}.get(source_type, "-")
            infer = get_inferensi()
            live = dict(infer.get("live") or {})
            pre = PERFORMA.get(self._performa) if self._performa else None
            self._live_cfg = {
                "imgsz_live": int(pre["imgsz_live"]) if pre
                else int(infer.get("imgsz_live", 480)),
                "infer_interval": int(pre["infer_interval"]) if pre
                else int(self.frame_skip),
                "display_fps": float(pre["display_fps"]) if pre
                else float(live.get("display_fps", 25)),
                "jpeg_quality": int(live.get("jpeg_quality", JPEG_Q_DEFAULT)),
                "display_width": int(live.get("display_width", 640)),
                "cam_width": int(live.get("cam_width", 640)),
                "cam_height": int(live.get("cam_height", 480)),
                "cam_fps": int(live.get("cam_fps", 30)),
                "iou": float(infer.get("iou", 0.5)),
            }
        self._reset_tracker()
        self._thread = threading.Thread(target=self._loop,
                                        args=(source_type, target), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        t, self._thread = self._thread, None
        if t is not None:
            t.join(timeout=5)
        with self._lock:
            self.running = False
        with self._frame_cond:
            self._frame_cond.notify_all()

    def _reset_tracker(self):
        """Buang tracker lama agar ID sesi baru mulai dari 1 lagi."""
        try:
            model = get_model(kunci="model_live")
            pred = getattr(model, "predictor", None)
            if pred is not None and hasattr(pred, "trackers"):
                for tr in pred.trackers:
                    try:
                        tr.reset()
                    except Exception:
                        pass
                try:
                    delattr(pred, "trackers")
                except Exception:
                    pass
        except Exception:
            pass

    # ---- worker ----
    def _open(self, source_type, target):
        if source_type == "webcam":
            cap = cv2.VideoCapture(int(target))
        else:
            cap = cv2.VideoCapture(str(target))
        try:
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        except Exception:
            pass
        if not cap.isOpened():
            raise RuntimeError(f"Tidak bisa membuka sumber: {target}")
        if source_type == "webcam":
            cfg = self._live_cfg or {}
            for prop, val in ((cv2.CAP_PROP_BUFFERSIZE, 1),
                              (cv2.CAP_PROP_FRAME_WIDTH, cfg.get("cam_width", 640)),
                              (cv2.CAP_PROP_FRAME_HEIGHT, cfg.get("cam_height", 480)),
                              (cv2.CAP_PROP_FPS, cfg.get("cam_fps", 30))):
                try:
                    cap.set(prop, val)
                except Exception:
                    pass
        return cap

    def _capture_worker(self, cap, is_file, src_fps, stop):
        """Selalu simpan frame terbaru; frame basi dibuang (tak menumpuk)."""
        dw = int((self._live_cfg or {}).get("display_width", 640))
        interval = (1.0 / src_fps) if (is_file and src_fps > 0) else 0.0
        t_prev = 0.0
        try:
            while not stop.is_set():
                if interval:
                    sisa = interval - (time.time() - t_prev)
                    if sisa > 0:
                        time.sleep(sisa)
                    t_prev = time.time()
                ok, frame = cap.read()
                if not ok:
                    with self._lock:
                        self.finished = True
                    stop.set()
                    break
                h, w = frame.shape[:2]
                if dw and w > dw:
                    frame = cv2.resize(frame, (dw, max(int(h * dw / w), 1)))
                with self._raw_lock:
                    self._raw_frame = frame
                    self._raw_seq += 1
                with self._lock:
                    self.n_frame += 1
        except Exception as e:
            with self._lock:
                self.error = f"Capture gagal: {e}"
            stop.set()

    def _infer_worker(self, source_type, stop):
        """Jalankan tracking tiap `infer_interval` frame; simpan overlay siap-gambar."""
        try:
            model = get_model(kunci="model_live")
        except Exception as e:
            with self._lock:
                self.error = f"Model live gagal dimuat: {e}"
            stop.set()
            return
        cfg = self._live_cfg or {}
        infer = get_inferensi()
        imgsz = int(cfg.get("imgsz_live", infer.get("imgsz_live", 480)))
        iou = float(cfg.get("iou", infer.get("iou", 0.5)))
        ambang = infer.get("toleransi_kelas")
        conf_run = conf_prediksi(self.conf, ambang)
        interval = max(int(cfg.get("infer_interval", 1)), 1)
        prev_gray = None
        k = 0
        while not stop.is_set():
            with self._raw_lock:
                raw = self._raw_frame
                seq = self._raw_seq
            if raw is None or seq == self._last_raw_infer:
                time.sleep(0.01)
                continue
            self._last_raw_infer = seq
            k += 1
            if interval > 1 and (k % interval) != 0:
                continue
            # Frame differencing: skip inferensi kalau frame hampir sama
            # (tampilan tetap jalan dari compose -- tak lagi mem-freeze).
            try:
                small = cv2.resize(raw, (64, 64))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                dasar = prev_gray is not None and \
                    cv2.absdiff(gray, prev_gray).mean() / 255.0 < FRAME_DIFF_THRESHOLD
                prev_gray = gray
                if dasar:
                    continue
            except Exception:
                pass
            t0 = time.time()
            umpan = cerahkan_malam(raw) if self.malam else raw
            try:
                res = model.track(umpan, persist=True, conf=conf_run,
                                  imgsz=imgsz, iou=iou,
                                  tracker="bytetrack.yaml", verbose=False)[0]
            except Exception as e:
                with self._lock:
                    self.error = f"Tracking gagal: {e}"
                stop.set()
                break
            dt = time.time() - t0
            self._simpan_tracks(res, model)
            with self._boxes_lock:
                self._boxes = self._bangun_overlay(res, model)
            with self._lock:
                if dt > 1e-6:
                    fps = 1.0 / dt
                    self.fps_infer = fps if self.fps_infer == 0 else \
                        0.9 * self.fps_infer + 0.1 * fps
                    self.fps_ema = self.fps_infer

    def _simpan_tracks(self, res, model):
        """Update self.tracks (temporal voting) — sama seperti jalur lama."""
        bs = res.boxes
        n = 0
        if bs is not None and len(bs):
            ids = bs.id
            for i, b in enumerate(bs):
                if ids is None:
                    continue
                tid = int(ids[i])
                if tid < 0:
                    continue
                cls = model.names[int(b.cls[0])]
                x1, y1, x2, y2 = map(float, b.xyxy[0])
                area = abs(x2 - x1) * abs(y2 - y1)
                n += 1
                with self._lock:
                    tr = self.tracks.get(tid)
                    cf = round(float(b.conf[0]), 3)
                    if tr is None:
                        if len(self.tracks) >= MAX_TRACKS:
                            korban = min(self.tracks,
                                         key=lambda kk: self.tracks[kk].get("frames", 0))
                            del self.tracks[korban]
                        self.tracks[tid] = {
                            "kelas": cls, "conf_max": cf,
                            "box_best": (x1, y1, x2, y2), "area_best": area,
                            "frames": 1, "votes": {cls: 1},
                        }
                    elif area > tr["area_best"]:
                        votes = dict(tr["votes"])
                        votes[cls] = votes.get(cls, 0) + 1
                        self.tracks[tid] = {
                            "kelas": cls, "conf_max": cf,
                            "box_best": (x1, y1, x2, y2), "area_best": area,
                            "frames": tr["frames"] + 1, "votes": votes,
                        }
                    else:
                        tr["frames"] += 1
                        tr["conf_max"] = max(tr["conf_max"], cf)
                        tr["votes"][cls] = tr["votes"].get(cls, 0) + 1
        with self._lock:
            self.n_deteksi += n

    def _bangun_overlay(self, res, model):
        """Daftar box siap-gambar (label+warna dihitung SEKALI per inferensi)."""
        if not self.anotasi_aktif:
            return []
        bs = res.boxes
        if bs is None or len(bs) == 0:
            return []
        ids = bs.id
        if ids is None:
            return []
        cfg = get_config()
        boxes = []
        for i, b in enumerate(bs):
            tid = int(ids[i])
            if tid < 0:
                continue
            cls = model.names[int(b.cls[0])]
            x1, y1, x2, y2 = map(int, b.xyxy[0])
            sev = diagnose(cls, x1, y1, x2, y2, cfg)["severity"]
            boxes.append((x1, y1, x2, y2, f"{tid} {cls} {sev}",
                          WARNA.get(sev, (255, 255, 255))))
        return boxes

    def _gambar_overlay(self, frame, boxes):
        out = frame.copy()
        for x1, y1, x2, y2, label, warna in boxes:
            cv2.rectangle(out, (x1, y1), (x2, y2), warna, 2)
            cv2.putText(out, label, (x1, max(y1 - 8, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, warna, 2)
        return out

    def _loop(self, source_type, target):
        """Thread target: buka sumber, jalankan capture+infer, compose di sini."""
        try:
            cap = self._open(source_type, target)
        except Exception as e:
            with self._lock:
                self.error, self.running = str(e), False
            return
        is_file = source_type == "file"
        src_fps = 0.0
        if is_file:
            try:
                src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            except Exception:
                src_fps = 0.0
            if not (1 <= src_fps <= 240):
                src_fps = 25.0
        stop = self._stop
        self._cap_thread = threading.Thread(
            target=self._capture_worker, args=(cap, is_file, src_fps, stop),
            daemon=True)
        self._infer_thread = threading.Thread(
            target=self._infer_worker, args=(source_type, stop), daemon=True)
        self._cap_thread.start()
        self._infer_thread.start()
        cfg = self._live_cfg or {}
        q = int(cfg.get("jpeg_quality", JPEG_Q_DEFAULT))
        interval = 1.0 / max(float(cfg.get("display_fps", 25)), 1.0)
        try:
            while not stop.is_set():
                t0 = time.time()
                with self._raw_lock:
                    raw = self._raw_frame
                    seq = self._raw_seq
                if raw is None or seq == self._last_raw_compose:
                    time.sleep(0.01)
                    continue
                self._last_raw_compose = seq
                with self._boxes_lock:
                    boxes = list(self._boxes)
                out = self._gambar_overlay(raw, boxes) if self.anotasi_aktif and boxes \
                    else raw
                ok, buf = cv2.imencode(".jpg", out,
                                       [cv2.IMWRITE_JPEG_QUALITY, q])
                if ok:
                    now = time.time()
                    with self._lock:
                        self.latest_jpg = buf.tobytes()
                    with self._frame_cond:
                        self._latest_seq += 1
                        self._frame_cond.notify_all()
                    if self._t_publish:
                        d = now - self._t_publish
                        if d > 1e-6:
                            f = 1.0 / d
                            self.fps_tampil = f if self.fps_tampil == 0 else \
                                0.9 * self.fps_tampil + 0.1 * f
                    self._t_publish = now
                sisa = interval - (time.time() - t0)
                if sisa > 0:
                    time.sleep(sisa)
        finally:
            stop.set()
            for t in (self._cap_thread, self._infer_thread):
                if t is not None:
                    t.join(timeout=3)
            try:
                cap.release()
            except Exception:
                pass
            with self._lock:
                self.running = False
            with self._frame_cond:
                self._frame_cond.notify_all()

    # ---- baca (dipakai routes) ----
    def get_frame(self):
        with self._lock:
            return self.latest_jpg, self.running

    def wait_frame(self, seq, timeout=1.0):
        """Tunggu sampai ada frame TERBARU (seq berubah) atau stream berhenti."""
        with self._frame_cond:
            self._frame_cond.wait_for(
                lambda: self._latest_seq != seq or not self.running, timeout)
            return self.latest_jpg, self.running, self._latest_seq

    def stats(self):
        with self._lock:
            return {"running": self.running, "error": self.error,
                    "finished": self.finished, "source": self.source_label,
                    "fps": round(self.fps_infer or self.fps_ema, 1),
                    "fps_tampil": round(self.fps_tampil, 1),
                    "fps_infer": round(self.fps_infer, 1),
                    "frame": self.n_frame,
                    "unik": len(self.tracks), "deteksi": self.n_deteksi}

    def snapshot(self):
        """Ringkasan sesi: rows per track-id (box terbaik) + frame anotasi terakhir.

        Track disaring: min_frames (redam kedip), kelas = suara mayoritas,
        lalu ambang per kelas + prior ukuran seperti jalur gambar.
        """
        with self._lock:
            tracks = dict(self.tracks)
            jpg = self.latest_jpg
            conf_global = self.conf
        import base64
        cfg, prices = get_config(), get_prices()
        infer = get_inferensi()
        min_frames = int(infer.get("live", {}).get("min_frames", 1))
        ambang = infer.get("toleransi_kelas")
        batas = infer.get("batas_ukuran")
        rows = []
        buang = {"ambang": 0, "ukuran": 0, "frame": 0}
        for tid in sorted(tracks):
            tr = tracks[tid]
            if int(tr.get("frames", 0)) < min_frames:
                buang["frame"] += 1
                continue
            kelas = kelas_mayoritas(tr.get("votes") or {}, tr.get("kelas"))
            if tr["conf_max"] < ambang_efektif(kelas, conf_global, ambang):
                buang["ambang"] += 1
                continue
            item = diagnose(kelas, *tr["box_best"], cfg)
            item["conf"] = tr["conf_max"]
            row = estimasi(item, prices)
            if not masuk_akal(row, batas):
                buang["ukuran"] += 1
                continue
            row["track_id"] = tid
            row["frames"] = tr["frames"]
            rows.append(row)
        total = sum(r["total_rp"] for r in rows)
        return {"rows": rows, "total": total, "disaring": buang,
                "image_b64": base64.b64encode(jpg).decode("ascii") if jpg else None}


MANAGER = StreamManager()
