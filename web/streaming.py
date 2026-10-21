"""Live stream Flask: VideoCapture -> YOLO track(persist=True, ByteTrack) -> MJPEG.

Arsitektur decouple (3 peran thread) agar preview tetap halus walau inferensi
berat di CPU:

  capture worker  : baca frame kamera terbaru (buang frame basi, BUFFERSIZE=1)
  infer worker    : jalankan model.track tiap `infer_interval` frame -> tracks + overlay
  compose (loop)  : tempel overlay TERAKHIR ke frame kamera SEGAR -> JPEG, laju `display_fps`

Dulu ketiganya satu loop bloking sehingga FPS tampil == FPS inferensi (~3 FPS)
dan buffer kamera menumpuk -> patah-patah. Pengukuran/snapshot tetap dari
self.tracks (box terbaik per ID), jadi angka severity/skor tak terpengaruh.

Infer worker kini PERSISTEN (satu thread seumur server), bukan dibuat ulang
tiap start(). Alasannya terukur: inferensi CUDA pertama di sebuah thread
membayar inisialisasi per-thread (~3-8 dtk); kalau thread dibuat per sesi,
biaya itu dibayar ulang dan penonton melihat video berjalan tanpa kotak
selama beberapa detik. Dengan thread persisten, biaya dibayar sekali saat
startup (panaskan()), jadi tiap "Mulai" langsung menampilkan kotak.

Satu sesi aktif dalam satu waktu (cukup untuk demo sidang + hemat CPU).
Setiap start() me-reset tracker sehingga ID mulai dari 1 lagi.
"""
import threading
import time
from collections import deque
from pathlib import Path
import logging

import cv2

from deteksi import (alasan_tolak, ambang_efektif, cerahkan_malam,
                     conf_prediksi, get_config, get_inferensi,
                     half_untuk, kelas_mayoritas, model_live_aktif,
                     nama_kelas, nama_model_live, pilih_device)
from severity import diagnose
from prioritas import skor as skor_prioritas

_log = logging.getLogger(__name__)

WARNA = {"Ringan": (0, 180, 0), "Sedang": (0, 200, 200), "Berat": (0, 0, 220)}
MAX_TRACKS = 500  # P1: cegah OOM sesi live berjam-jam
JPEG_Q_DEFAULT = 72  # encode lebih murah dari 85 -> FPS tampil lebih tinggi
FRAME_DIFF_THRESHOLD = 0.02  # fallback; nilai nyata dari config live.frame_diff_threshold

# Preset "Mode Performa" (dikirim UI lewat /api/stream/start).
# Nilai disetel untuk GPU (GTX 1650): inferensi ~15-30 ms, jadi interval 1
# (tanpa skip) masih real-time. Di CPU, pakai "halus" + interval lebih besar.
#
# Hanya DUA titik operasi yang berguna: model dilatih di 640, dan frame sudah
# dibatasi `live.display_width` (640), sehingga imgsz > 640 hanya meng-upscale
# dan dijepit balik oleh jepit_imgsz(). Preset "akurat" (960) dihapus 19 Okt 2026
# karena jadi duplikat "seimbang" sekaligus menyesatkan (lihat docs/Panduan-
# Tuning-Model.md).
PERFORMA = {
    "halus": {"imgsz_live": 320, "infer_interval": 1, "display_fps": 30},
    "seimbang": {"imgsz_live": 640, "infer_interval": 1, "display_fps": 30},
}


def jepit_imgsz(imgsz, lebar_frame):
    """imgsz efektif untuk live: TIDAK PERNAH melebihi lebar frame (cegah upscale).

    Kenapa perlu: `live.display_width` (default 640) sudah memotong frame di
    capture worker, jadi meminta imgsz 960 pada frame 640 hanya membuat
    ultralytics MENG-UPSCALE 640 -> 960 — nol detail baru, ~2,3x lebih mahal, dan
    keluar dari skala latih model (640) sehingga menambah false positive. Ini
    jaring pengaman untuk preset/`imgsz_live` yang disetel di atas lebar frame.
    Terukur di CPU (i5-3470, `model.track`): 157 ms @640 vs 358 ms @960 —
    ~2,3x lebih mahal untuk detail yang tidak bertambah.

    Cap dibulatkan ke BAWAH ke kelipatan 32 (stride YOLO) supaya tidak ada
    padding sia-sia; batas bawah 32. Lebar frame tak masuk akal -> nilai asli
    dikembalikan apa adanya (jangan sampai mengubah perilaku karena data aneh).
    """
    try:
        asli = max(32, int(imgsz))
    except (TypeError, ValueError):
        return 640
    try:
        lebar = int(lebar_frame)
    except (TypeError, ValueError):
        return asli
    if lebar <= 0:
        return asli
    pas = max((lebar // 32) * 32, 32)
    return max(32, min(asli, pas))


class StreamManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        # --- thread inferensi live PERSISTEN (satu seumur proses) ---
        self._infer_lock = threading.Lock()
        self._infer_persisten = None
        self._infer_siap = threading.Event()   # warmup selesai
        self._infer_idle = threading.Event()   # sedang menganggur (aman reset state)
        self._infer_idle.set()
        self._infer_sesi = threading.Event()   # ada sesi aktif yang perlu dilayani
        self._tutup = threading.Event()        # shutdown server
        self._source_type = "webcam"
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
        self.n_inferensi = 0  # jumlah pemanggilan model.track() (penyebut metrik adil)
        # imgsz yang BENAR-BENAR dipakai inferensi terakhir (setelah dijepit
        # agar tak melebihi lebar frame - lihat jepit_imgsz). None = belum ada
        # inferensi. Dipakai stats() supaya UI bisa jujur soal resolusi nyata.
        self.imgsz_live_efektif = None
        self.fps_ema = 0.0        # FPS inferensi (kompat UI lama)
        self.fps_infer = 0.0
        self.fps_tampil = 0.0
        self.tracks = {}          # id -> {kelas, conf_max, box_best, area_best, frames}
        self.latest_jpg = None
        self.latest_jpg_berbox = None  # frame anotasi terakhir yg memuat box
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
        # Perataan tampilan: rata-rata bergerak jumlah box TERLIHAT agar angka
        # live tidak kedip tiap inferensi. DISPLAY-ONLY — snapshot()/riwayat
        # tidak memakai ini (lihat stats()["tampil"]).
        self._tampil_riwayat = deque(maxlen=12)
        self._frame_cond = threading.Condition()
        self._latest_seq = 0
        self._t_publish = 0.0
        self._cap_thread = None

    # ---- kontrol ----
    def start(self, source_type, target, conf=0.25, frame_skip=1, label=None,
              malam=False, performa=None):
        """source_type: webcam | ipcam | file. target: index/url/path.

        performa: 'halus' | 'seimbang' (opsional, override imgsz + interval
        inferensi + batas FPS tampil). Nilai lain diabaikan (pakai config).
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
            self._source_type = source_type
            self.source_label = label or {
                "webcam": f"Webcam {target}", "ipcam": "HP IP-camera",
                "file": Path(str(target)).name}.get(source_type, "-")
            infer = get_inferensi()
            live = dict(infer.get("live") or {})
            device = pilih_device(infer.get("device", "auto"),
                                  nama_model_live())
            # Tanpa pilihan eksplisit: CPU default ke "halus" agar laptop tanpa
            # GPU tetap bergerak. imgsz config non-default dan preset eksplisit
            # tidak ditimpa.
            if (self._performa is None and self.frame_skip == 1
                    and int(infer.get("imgsz_live", 640)) == 640):
                self._performa = "halus" if str(device) == "cpu" else "seimbang"
            pre = PERFORMA.get(self._performa) if self._performa else None
            self._live_cfg = {
                "imgsz_live": int(pre["imgsz_live"]) if pre
                else int(infer.get("imgsz_live", 640)),
                "infer_interval": int(pre["infer_interval"]) if pre
                else int(self.frame_skip),
                "display_fps": float(pre["display_fps"]) if pre
                else float(live.get("display_fps", 30)),
                "jpeg_quality": int(live.get("jpeg_quality", JPEG_Q_DEFAULT)),
                "display_width": int(live.get("display_width", 640)),
                "cam_width": int(live.get("cam_width", 640)),
                "cam_height": int(live.get("cam_height", 480)),
                "cam_fps": int(live.get("cam_fps", 30)),
                "iou": float(infer.get("iou", 0.5)),
                "frame_diff_threshold": float(live.get("frame_diff_threshold",
                                                        FRAME_DIFF_THRESHOLD)),
                "perataan_tampil": int(live.get("perataan_tampil", 12)),
                "device": device,
            }
            # Samakan window perataan dengan config sesi ini.
            self._tampil_riwayat = deque(
                maxlen=max(1, self._live_cfg["perataan_tampil"]))
        self._pastikan_infer()
        # Warmup berjalan di thread inferensi dan menulis predictor/trackers di
        # model live; jangan reset di tengah-tengah. Event ini selalu diset
        # setelah warmup (sukses maupun gagal), jadi tak bisa menggantung.
        self._infer_siap.wait(timeout=120)
        self._reset_tracker()
        self._thread = threading.Thread(target=self._loop,
                                        args=(source_type, target), daemon=True)
        self._thread.start()
        # Aktifkan sesi di thread inferensi persisten (state sudah bersih).
        self._infer_sesi.set()
        return True

    def stop(self):
        # Cegah thread inferensi persisten mengambil sesi baru, lalu hentikan
        # sesi berjalan lewat self._stop.
        self._infer_sesi.clear()
        self._stop.set()
        t, self._thread = self._thread, None
        if t is not None:
            t.join(timeout=5)
        # Tunggu thread inferensi persisten kembali menganggur sebelum state
        # direset oleh start() berikutnya (hindari ia menulis state sesi lama).
        self._infer_idle.wait(timeout=5)
        with self._lock:
            self.running = False
        with self._frame_cond:
            self._frame_cond.notify_all()

    # ---- thread inferensi persisten ----
    def _pastikan_infer(self):
        """Pastikan thread inferensi live persisten hidup (lahirkan bila mati)."""
        t = self._infer_persisten
        if t is not None and t.is_alive():
            return t
        with self._infer_lock:
            t = self._infer_persisten
            if t is not None and t.is_alive():
                return t
            self._infer_siap.clear()
            self._infer_persisten = threading.Thread(
                target=self._infer_loop, name="inferensi-live", daemon=True)
            self._infer_persisten.start()
            return self._infer_persisten

    def panaskan(self):
        """Siapkan + hangatkan thread inferensi live sekali (panggil saat startup).

        Biaya inisialisasi (CUDA per-thread + jalur pasca-deteksi) dibayar di
        sini memakai frame NYATA, bukan di sesi pertama -- sehingga mulai stream
        langsung menampilkan kotak.
        """
        self._pastikan_infer()
        self._infer_siap.wait(timeout=120)

    def _panaskan_infer(self):
        """Warmup CUDA di THREAD INI memakai frame NYATA (bukan zeros).

        Terukur (17 Okt 2026): warmup dengan `np.zeros` TIDAK menghangatkan
        jalur pasca-deteksi (internal `model.warmup` + NMS) yang hanya berjalan
        saat ada objek -> `track` pertama pada frame nyata tetap ~3-4 dtk.
        Setelah satu frame asli, inferensi berikutnya ~0,2 dtk. Karena itu
        warmup memakai frame dari video demo bawaan (pasti ada kerusakan),
        pada tiap imgsz preset (320/640/960) + imgsz_live config; lalu tracker
        dibersihkan agar ID sesi mulai dari 1.
        """
        try:
            model = model_live_aktif()
            infer = get_inferensi()
        except Exception:
            return
        ukuran = {320, 640, 960}
        try:
            ukuran.add(int(infer.get("imgsz_live", 640)))
        except (TypeError, ValueError):
            pass
        device = pilih_device(infer.get("device", "auto"),
                              nama_model_live())
        iou = float(infer.get("iou", 0.5))
        umpan = self._gambar_warmup()
        for k in sorted(ukuran):
            if self._tutup.is_set():
                break
            try:
                model.track(umpan, persist=True, conf=0.25, imgsz=k, iou=iou,
                            device=device, half=half_untuk(device),
                            tracker="bytetrack.yaml", verbose=False)
            except Exception:
                pass
            # Hemat VRAM di GPU kecil: lepas cache antar-ukuran (imgsz 960 bisa
            # memicu peringatan OOM sesaat di GPU 4GB).
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        # Buang track hasil warmup agar ID sesi nyata mulai dari 1.
        self._reset_tracker()

    def _gambar_warmup(self):
        """Ambil 1 frame NYATA untuk warmup (fallback: frame kosong).

        Frame berisi objek penting supaya jalur deteksi/NMS benar-benar jalan.
        Utamakan video demo bawaan; bila tak ada, pakai gambar di folder demo;
        terakhir frame hitam (paling tidak menghangatkan jalur inferensi).
        """
        import numpy as np
        dasar = Path(__file__).resolve().parent / "static" / "demo"
        video = dasar / "demo_jalan.mp4"
        try:
            if video.exists():
                cap = cv2.VideoCapture(str(video))
                ok, fr = cap.read()
                try:
                    cap.release()
                except Exception:
                    pass
                if ok and fr is not None:
                    return fr
        except Exception:
            pass
        try:
            for p in sorted(dasar.glob("*.jpg")):
                fr = cv2.imread(str(p))
                if fr is not None:
                    return fr
        except Exception:
            pass
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def _infer_loop(self):
        """Thread inferensi live PERSISTEN: warmup sekali, lalu layani tiap sesi.

        Antara sesi thread menganggur (tak menyentuh model). Biaya CUDA
        per-thread dibayar sekali di sini saat startup.
        """
        try:
            self._panaskan_infer()
        finally:
            self._infer_siap.set()
            self._infer_idle.set()
        while not self._tutup.is_set():
            if not self._infer_sesi.wait(timeout=0.5):
                continue
            if self._tutup.is_set():
                break
            self._infer_idle.clear()
            try:
                self._infer_worker(self._source_type, self._stop)
            except Exception as e:
                with self._lock:
                    self.error = f"Tracking gagal: {e}"
                self._stop.set()
            finally:
                self._infer_idle.set()
                self._infer_sesi.clear()

    def _reset_tracker(self):
        """Buang tracker lama agar ID sesi baru mulai dari 1 lagi."""
        try:
            model = model_live_aktif()
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
            model = model_live_aktif()
        except Exception as e:
            with self._lock:
                self.error = f"Model live gagal dimuat: {e}"
            stop.set()
            return
        cfg = self._live_cfg or {}
        infer = get_inferensi()
        imgsz = int(cfg.get("imgsz_live", infer.get("imgsz_live", 640)))
        iou = float(cfg.get("iou", infer.get("iou", 0.5)))
        device = cfg.get("device", pilih_device(infer.get("device", "auto"),
                                                nama_model_live()))
        ambang = infer.get("toleransi_kelas")
        conf_run = conf_prediksi(self.conf, ambang)
        interval = max(int(cfg.get("infer_interval", 1)), 1)
        # Frame-differencing hanya untuk kamera langsung (adegan diam -> hemat
        # GPU). Untuk SUMBER VIDEO dimatikan: demo harus segar tiap frame.
        thr = float(cfg.get("frame_diff_threshold", FRAME_DIFF_THRESHOLD))
        pakai_diff = (source_type != "file") and thr > 0
        prev_gray = None
        k = 0
        # Catatan (17 Okt 2026): dulu warmup dummy di sini DICOBA lalu di-revert
        # karena "tidak menolong". Setelah diukur ulang: warmup MEMANG menolong,
        # asalkan (a) dijalankan di THREAD YANG SAMA yang akan menginferensi dan
        # (b) argumen device/imgsz sama dengan inferensi asli (percobaan lama
        # diduga jalan di CPU / ukuran beda). Kini warmup dipusatkan sekali di
        # thread inferensi persisten -> lihat _panaskan_infer().
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
            if pakai_diff:
                try:
                    small = cv2.resize(raw, (64, 64))
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    dasar = prev_gray is not None and \
                        cv2.absdiff(gray, prev_gray).mean() / 255.0 < thr
                    prev_gray = gray
                    if dasar:
                        continue
                except Exception:
                    pass
            t0 = time.time()
            umpan = cerahkan_malam(raw) if self.malam else raw
            # Jepit ke lebar frame NYATA yang diterima model (lihat jepit_imgsz):
            # preset 960 pada frame 640 hanya meng-upscale, bukan menambah detail.
            imgsz_efektif = jepit_imgsz(imgsz, raw.shape[1])
            try:
                res = model.track(umpan, persist=True, conf=conf_run,
                                  imgsz=imgsz_efektif, iou=iou, device=device,
                                  half=half_untuk(device),
                                  tracker="bytetrack.yaml", verbose=False)[0]
            except Exception as e:
                with self._lock:
                    self.error = f"Tracking gagal: {e}"
                stop.set()
                break
            dt = time.time() - t0
            with self._lock:
                # Hitung inferensi sukses (penyebut "rata-rata deteksi per
                # inferensi" — metrik adil antar mode performa).
                self.n_inferensi += 1
                self.imgsz_live_efektif = imgsz_efektif
            self._simpan_tracks(res, model)
            with self._boxes_lock:
                self._boxes = self._bangun_overlay(res, model)
                # Catat jumlah box terlihat untuk perataan tampilan (murah,
                # atomik di CPython; dibaca stats() sebagai rata-rata).
                self._tampil_riwayat.append(len(self._boxes))
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
            if ids is None:
                # Tracker tak mengembalikan ID: semua deteksi frame ini tak bisa
                # di-track. Jangan diam-diam — catat agar mudah didiagnosis.
                _log.warning("live: %d box tanpa track-id (tracker tak memberi ID), "
                             "dilewati", len(bs))
            for i, b in enumerate(bs):
                if ids is None:
                    continue
                tid = int(ids[i])
                if tid < 0:
                    continue
                cls = nama_kelas(model.names, int(b.cls[0]))
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
                            "kelas": cls,
                            "conf_max": max(tr["conf_max"], cf),
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
        # Redam kedip: tampilkan hanya track yang sudah terlihat >= min_frames
        # (aturan yang sama dengan snapshot(); _simpan_tracks dipanggil duluan).
        infer = get_inferensi()
        min_frames = max(int(infer.get("live", {}).get("min_frames", 1)), 1)
        with self._lock:
            frames = {tid: tr.get("frames", 0) for tid, tr in self.tracks.items()}
        cfg = get_config()
        boxes = []
        for i, b in enumerate(bs):
            tid = int(ids[i])
            if tid < 0:
                continue
            if frames.get(tid, 0) < min_frames:
                continue
            cls = nama_kelas(model.names, int(b.cls[0]))
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
        self._cap_thread.start()
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
                    jpg_bytes = buf.tobytes()
                    # Simpan juga frame ber-box terakhir: dipakai snapshot() agar
                    # foto riwayat selalu menampilkan box deteksi walau frame
                    # terakhir saat simpan sudah tidak memuat box.
                    ada_box = self.anotasi_aktif and bool(boxes)
                    with self._lock:
                        self.latest_jpg = jpg_bytes
                        if ada_box:
                            self.latest_jpg_berbox = jpg_bytes
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
            if self._cap_thread is not None:
                self._cap_thread.join(timeout=3)
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
            riw = list(self._tampil_riwayat)
            tampil = round(sum(riw) / len(riw)) if riw else 0
            # Metrik adil antar mode: deteksi & titik unik bersifat kumulatif
            # (mode lambat selalu kalah angka), sedangkan rata-rata per
            # inferensi membandingkan kualitas per frame yang setara.
            rata = (round(self.n_deteksi / self.n_inferensi, 2)
                    if self.n_inferensi else 0)
            return {"running": self.running, "error": self.error,
                    "finished": self.finished, "source": self.source_label,
                    "fps": round(self.fps_infer or self.fps_ema, 1),
                    "fps_tampil": round(self.fps_tampil, 1),
                    "fps_infer": round(self.fps_infer, 1),
                    "frame": self.n_frame,
                    "unik": len(self.tracks), "deteksi": self.n_deteksi,
                    "n_inferensi": self.n_inferensi, "rata_deteksi": rata,
                    # Mode performa aktif + imgsz yang BENAR-BENAR dipakai
                    # (sudah dijepit). `imgsz_live` di sini = efektif, bukan
                    # nilai preset mentah; UI memakainya untuk jujur soal
                    # resolusi nyata (lihat jepit_imgsz).
                    "performa": self._performa,
                    "imgsz_live": self.imgsz_live_efektif,
                    # Rata-rata bergerak box terlihat (display-only, redam
                    # kedip). BUKAN dasar snapshot/riwayat.
                    "tampil": tampil}

    def snapshot(self):
        """Ringkasan sesi: rows per track-id (box terbaik) + frame anotasi terakhir.

        Track disaring: min_frames (redam kedip), kelas = suara mayoritas,
        lalu ambang per kelas + prior ukuran seperti jalur gambar.

        Foto sesi memakai frame ber-box terakhir bila ada (agar foto riwayat
        menampilkan box deteksi); fallback ke frame terakhir biasa.

        CATATAN DESAIN: track TIDAK kedaluwarsa — snapshot adalah gabungan
        seluruh track yang pernah terlihat selama sesi. Ini disengaja untuk
        inventarisasi drive-through (satu sesi = satu ruas). Untuk kamera
        statis, track lama ikut terbawa; bila itu jadi masalah, sesi harus
        di-restart berkala.
        """
        with self._lock:
            tracks = dict(self.tracks)
            jpg = self.latest_jpg_berbox or self.latest_jpg
            conf_global = self.conf
        import base64
        cfg = get_config()
        infer = get_inferensi()
        min_frames = int(infer.get("live", {}).get("min_frames", 1))
        ambang = infer.get("toleransi_kelas")
        batas = infer.get("batas_ukuran")
        rows = []
        buang = {"ambang": 0, "ukuran": 0, "aspek": 0, "frame": 0}
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
            row = skor_prioritas(item)
            alasan = alasan_tolak(row, batas)
            if alasan is not None:
                buang["aspek" if alasan == "aspek" else "ukuran"] += 1
                continue
            row["track_id"] = tid
            row["frames"] = tr["frames"]
            rows.append(row)
        total = sum(r["skor_prioritas"] for r in rows)
        return {"rows": rows, "total": total, "disaring": buang,
                "image_b64": base64.b64encode(jpg).decode("ascii") if jpg else None}


MANAGER = StreamManager()
