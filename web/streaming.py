"""Live stream Flask: VideoCapture -> YOLO track(persist=True, ByteTrack) -> MJPEG.

Satu sesi aktif dalam satu waktu (cukup untuk demo sidang + hemat CPU).
Setiap start() me-reset tracker sehingga ID mulai dari 1 lagi.
"""
import threading
import time
from pathlib import Path

import cv2

from deteksi import (ambang_efektif, conf_prediksi, encode_jpg, get_config,
                     get_inferensi, get_model, get_prices, kelas_mayoritas,
                     masuk_akal)
from severity import diagnose
from biaya import estimasi

WARNA = {"Ringan": (0, 180, 0), "Sedang": (0, 200, 200), "Berat": (0, 0, 220)}
JPEG_Q = [cv2.IMWRITE_JPEG_QUALITY, 85]
MAX_TRACKS = 500  # P1: cegah OOM sesi live berjam-jam


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
        self.fps_ema = 0.0
        self.tracks = {}  # id -> {kelas, conf_max, box_best, area_best, frames}
        self.latest_jpg = None
        self.finished = False
        self.anotasi_aktif = True

    # ---- kontrol ----
    def start(self, source_type, target, conf=0.25, frame_skip=1, label=None, malam=False):
        """source_type: webcam | ipcam | file. target: index/url/path."""
        self.stop()
        with self._lock:
            self.reset_state()
            self.conf = min(max(float(conf), 0.05), 0.8)
            self.frame_skip = min(max(int(frame_skip), 1), 30)
            self.malam = bool(malam)
            self.running = True
            self.source_label = label or {"webcam": f"Webcam {target}", "ipcam": "HP IP-camera",
                                 "file": Path(str(target)).name}.get(source_type, "-")
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
        self._stop.clear()
        with self._lock:
            self.running = False

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
        return cap

    def _loop(self, source_type, target):
        try:
            cap = self._open(source_type, target)
        except Exception as e:
            with self._lock:
                self.error, self.running = str(e), False
            return
        model = get_model(kunci="model_live")
        cfg, prices = get_config(), get_prices()
        infer = get_inferensi()  # dibaca sekali per sesi; ubahan yaml berlaku start berikut
        imgsz_live, iou_live = infer["imgsz_live"], infer["iou"]
        ambang = infer.get("toleransi_kelas")
        conf_run = conf_prediksi(self.conf, ambang)  # kelas sensitif ikut terdeteksi
        # Optimalasi: resize frame besar sebelum inferensi agar lebih cepat
        max_infer_size = imgsz_live  # batas maksimum sisi panjang untuk inferensi
        # Frame differencing: skip inferensi kalau frame hampir sama (webcam statis)
        prev_frame_gray = None
        frame_diff_threshold = 0.02  # 2% berbeda = baru diinferensi
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    with self._lock:
                        self.finished = True
                    break
                with self._lock:
                    self.n_frame += 1
                    skip = (self.n_frame - 1) % self.frame_skip != 0
                if skip and self.latest_jpg is not None:
                    continue
                # Cek apakah frame berubah signifikan (hemat inferensi untuk webcam statis)
                frame_small = cv2.resize(frame, (64, 64))  # kecilkan untuk cepat compare
                frame_gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
                if prev_frame_gray is not None:
                    diff = cv2.absdiff(frame_gray, prev_frame_gray)
                    mean_diff = diff.mean() / 255.0
                    if mean_diff < frame_diff_threshold:
                        # Frame hampir sama, skip inferensi tapi tetap update display
                        continue
                prev_frame_gray = frame_gray.copy()
                t0 = time.time()
                from deteksi import cerahkan_malam
                # Resize frame yang terlalu besar untuk mempercepat inferensi
                h, w = frame.shape[:2]
                scale = min(max_infer_size / max(w, h), 1.0) if max(w, h) > max_infer_size else 1.0
                if scale < 1.0:
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                umpan = cerahkan_malam(frame) if self.malam else frame
                try:
                    res = model.track(umpan, persist=True, conf=conf_run,
                                      imgsz=imgsz_live, iou=iou_live,
                                      tracker="bytetrack.yaml", verbose=False)[0]
                except Exception as e:
                    with self._lock:
                        self.error = f"Tracking gagal: {e}"
                    break
                dt = time.time() - t0
                boxes = res.boxes
                n = 0
                if boxes is not None and len(boxes):
                    ids = boxes.id
                    for i, b in enumerate(boxes):
                        # Box tanpa ID = track belum confirmed ByteTrack -> lewati
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
                                    # Evict track dengan frames terkecil (paling tidak relevan)
                                    korban = min(self.tracks, key=lambda k: self.tracks[k].get("frames", 0))
                                    del self.tracks[korban]
                                votes = {}
                                votes[cls] = 1
                                self.tracks[tid] = {
                                    "kelas": cls, "conf_max": cf,
                                    "box_best": (x1, y1, x2, y2), "area_best": area,
                                    "frames": 1, "votes": votes,
                                }
                            elif area > tr["area_best"]:
                                votes = dict(tr["votes"])
                                votes[cls] = votes.get(cls, 0) + 1
                                self.tracks[tid] = {
                                    "kelas": cls, "conf_max": cf,
                                    "box_best": (x1, y1, x2, y2), "area_best": area,
                                    "frames": tr["frames"] + 1,
                                    "votes": votes,
                                }
                            else:
                                tr["frames"] += 1
                                tr["conf_max"] = max(tr["conf_max"], cf)
                                tr["votes"][cls] = tr["votes"].get(cls, 0) + 1
                if self.anotasi_aktif:
                    frame = self._anotasi(frame, res, model, cfg)
                ok, buf = cv2.imencode(".jpg", frame, JPEG_Q)
                with self._lock:
                    self.n_deteksi += n
                    if dt > 1e-6:  # P1: guard dt==0 agar _loop tak mati ZeroDivision
                        fps = 1.0 / dt
                        self.fps_ema = fps if self.fps_ema == 0 else \
                            0.9 * self.fps_ema + 0.1 * fps
                    if ok:
                        self.latest_jpg = buf.tobytes()
        finally:
            try:
                cap.release()
            except Exception:
                pass
            with self._lock:
                self.running = False

    def _anotasi(self, frame, res, model, cfg):
        out = frame
        boxes = res.boxes
        if boxes is not None and len(boxes):
            ids = boxes.id
            if ids is None:
                return out
            for i, b in enumerate(boxes):
                tid = int(ids[i])
                if tid < 0:
                    continue
                cls = model.names[int(b.cls[0])]
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                sev = diagnose(cls, *map(float, b.xyxy[0]), cfg)["severity"]
                warna = WARNA.get(sev, (255, 255, 255))
                cv2.rectangle(out, (x1, y1), (x2, y2), warna, 2)
                cv2.putText(out, f"{tid} {cls} {sev}", (x1, max(y1 - 8, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, warna, 2)
        # OSD teks dihapus - data FPS/unik/frame sudah ada di KPI cards UI
        return out

    # ---- baca (dipakai routes) ----
    def get_frame(self):
        with self._lock:
            return self.latest_jpg, self.running

    def stats(self):
        with self._lock:
            return {"running": self.running, "error": self.error,
                    "finished": self.finished, "source": self.source_label,
                    "fps": round(self.fps_ema, 1), "frame": self.n_frame,
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
