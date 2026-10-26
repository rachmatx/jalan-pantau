"""Pipeline deteksi Flask: YOLO -> severity -> indeks prioritas (-> PDF di routes).

Modul terverifikasi dipakai ulang TANPA diubah: app/severity.py,
app/prioritas.py, app/laporan.py. File ini hanya adaptor (I/O web) di atasnya.
"""
import logging
import math
import os
import sys
import tempfile
import threading
from pathlib import Path

import cv2
import yaml

# Cegah ultralytics meng-unduh paket saat runtime (mis. `onnxruntime-gpu` saat
# model ONNX diarahkan ke GPU). Saat demo/ujian unduhan diam-diam = hang.
# Harus di-set SEBELUM ultralytics diimpor (impor terjadi malas di get_model).
os.environ.setdefault("YOLO_AUTOINSTALL", "false")

# Redam spam "'half' is deprecated..." dari ultralytics baru (muncul tiap
# predict). Perilaku TIDAK berubah: half=True tetap diteruskan & FP16 tetap
# aktif; yang dibungkam hanya baris log-nya (LOGGER.warning, bukan warnings).
# Bila ultralytics menghapus argumen `half`, migrasinya = set dtype sekali
# saat load (model.model.half()) lalu hapus argumen half dari predict.
class _FilterHalfDeprecated(logging.Filter):
    def filter(self, record):
        return "'half' is deprecated" not in record.getMessage()

logging.getLogger("ultralytics").addFilter(_FilterHalfDeprecated())

_log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
APP_DIR = WEB_DIR.parent / "app"
ROOT = WEB_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from severity import diagnose, load_config, makna_untuk_kelas  # noqa: E402
from prioritas import skor as skor_prioritas  # noqa: E402
from laporan import buat_laporan  # noqa: E402
from scene_gate import (  # noqa: E402
    putuskan_gate, saring_gate_basah, label_id as label_scene_id,
    WET_MIN_BAWAAN as GATE_WET_MIN, AMBANG_LUBANG_BAWAAN as GATE_AMBANG,
    WET_LABEL,
)

MODEL_DEFAULT = APP_DIR / "weights" / "best.pt"
WEIGHTS_DIR = APP_DIR / "weights"
CFG_DEFAULT = ROOT / "config" / "severity.yaml"
INFER_DEFAULT = ROOT / "config" / "inferensi.yaml"

# Nilai sah untuk knob `mode_backend` (lihat backend_live()).
BACKEND_MODE = ("auto", "pt", "onnx")

_models = {}  # key "<ruang>::<path>" (atau path) -> YOLO; lihat get_model()
_cfg = None
_infer = None
_model_lock = threading.Lock()  # jaga load singleton dari Flask thread + worker stream
_kalibrasi_lock = threading.Lock()  # P3: tulis severity.yaml atomik antar-thread

# Fallback bila config/inferensi.yaml hilang/rusak. NILAI HARUS MIRIP config/inferensi.yaml.
# Kalau berbeda, mode degradasi diam-diam mengubah perilaku: tta False menurunkan
# recall (0,69 -> 0,48 pada trial TTA) dan imgsz_live 960 memperlambat live ~2x.
# config/inferensi.yaml: tta=true, imgsz_live=640 (skala latih).
_INFER_FALLBACK = {
    "model_gambar": "best.pt", "model_live": "best.pt",
    "device": "auto",
    # mode_backend: auto = .pt bila ada CUDA, .onnx bila hanya CPU. Berlaku
    # HANYA untuk jalur LIVE (lihat backend_live): jalur gambar tetap .pt
    # karena ONNX mengabaikan TTA dan TTA itu yang menjaga recall.
    "mode_backend": "auto",
    # imgsz_gambar 640 (bukan 960): diukur pada 161 gambar BPID berlabel,
    # F1 pothole 0,630 @640 vs 0,536 @960 (precision 0,63 vs 0,54). Model
    # dilatih imgsz 640 (notebooks/kaggle-retrain-yolo11s-rdd2022.py), jadi
    # 960 = 1,5x skala latih: menambah false positive, bukan recall.
    # Lihat catatan di config/inferensi.yaml.
    "imgsz_gambar": 640, "imgsz_live": 640, "iou": 0.5, "tta": True,
    # half_gambar: FP16 untuk jalur GAMBAR. Default false = FP32. Alasan: FP16
    # + TTA meluap secara numerik pada imgsz besar dan mengeluarkan box NaN
    # (hilang temuan; lihat catatan di config/inferensi.yaml). Jalur live tetap
    # FP16 lewat half_untuk().
    "half_gambar": False,
    # maks_sisi_proses: sisi terpanjang maksimum untuk ANALISIS gambar unggahan.
    # 1536 = pilihan sejak 26 Okt 2026; 0 = nonaktif (resolusi asli). Model
    # tetap letterbox ke imgsz_gambar, jadi memperkecil di sini TIDAK mengubah
    # piksel yang "dilihat" model — yang terpangkas hanya tahap murah yang
    # linier terhadap jumlah piksel (cek gelap, klasifikasi scene, CLAHE malam,
    # anotasi, encode JPEG, base64). Box dikembalikan di koordinat GAMBAR ASLI
    # (lihat skala_box di proses_detections), sehingga kalibrasi px/cm,
    # severity, masuk_akal, dan verifikasi operator tidak berubah sama sekali.
    # Mode teliti SELALU memakai resolusi asli (gunanya memang detail asli).
    # Bukti pemilihan angka: docs/Panduan-Tuning-Model.md §6e.
    "maks_sisi_proses": 1536,
    "teliti": {"aktif_default": False, "tile": 640, "imgsz": 960,
               "overlap": 0.25, "iou_gabung": 0.5, "metode_gabung": "wbf",
               "buang_tepi_tile": True, "iou_agnostik": 0.6},
    # pothole 0 (bukan 0.08): lowering 0,08 membuat ambang efektif 0,17 dan
    # precision pothole jatuh ke 0,32 (BPID, 161 gambar). Tanpa lowering, F1
    # maksimum ada di conf ~0,30-0,35.
    "toleransi_kelas": {"longitudinal_crack": 0.0, "transverse_crack": 0.05,
                        "alligator_crack": 0.05, "other_corruption": 0.10,
                        "pothole": 0.0},
    "live": {"min_frames": 2, "display_fps": 30, "infer_interval": 1,
             "frame_diff_threshold": 0.02, "jpeg_quality": 72,
             "display_width": 640, "cam_width": 640, "cam_height": 480,
             "cam_fps": 30, "perataan_tampil": 12},
    "batas_ukuran": {"diameter_maks_cm": 300, "lebar_retak_maks_cm": 100,
                     "luas_maks_m2": 100, "rasio_aspek_min_retak": 1.5},
    # gabung_fragmen 0.30/0.50 (18 Okt 2026): aturan lama 0.05/0.30 menganggap
    # dua pothole berdampingan sebagai satu fragmen dan menelan salah satunya
    # (F1 0,567 -> 0,597 di ambang 0,25; 0,616 di ambang 0,30).
    "gabung_fragmen": {"aktif": True, "iou_min": 0.3, "inter_min": 0.5,
                       "lintas_kelas": True},
    "saring": {"luas_min_px": 900, "maks_temuan": 20},
    "ensemble": {"aktif": False, "model_kedua": "best.pt", "iou": 0.5,
                 "metode": "wbf"},
}


def _klamp(nilai, bawah, atas, bawaan):
    try:
        v = float(nilai)
    except (TypeError, ValueError):
        return bawaan
    return min(max(v, bawah), atas)


def get_inferensi(path=None):
    """Baca config/inferensi.yaml (cache). Selalu kembalikan dict valid."""
    global _infer
    if _infer is None or path is not None:
        data = {"model_gambar": _INFER_FALLBACK["model_gambar"],
                "model_live": _INFER_FALLBACK["model_live"],
                "device": _INFER_FALLBACK["device"],
                "mode_backend": _INFER_FALLBACK["mode_backend"],
                "imgsz_gambar": _INFER_FALLBACK["imgsz_gambar"],
                "imgsz_live": _INFER_FALLBACK["imgsz_live"],
                "iou": _INFER_FALLBACK["iou"], "tta": _INFER_FALLBACK["tta"],
                "half_gambar": _INFER_FALLBACK["half_gambar"],
                "maks_sisi_proses": _INFER_FALLBACK["maks_sisi_proses"],
                "teliti": dict(_INFER_FALLBACK["teliti"]),
                "toleransi_kelas": dict(_INFER_FALLBACK["toleransi_kelas"]),
                "live": dict(_INFER_FALLBACK["live"]),
                "batas_ukuran": dict(_INFER_FALLBACK["batas_ukuran"]),
                "gabung_fragmen": dict(_INFER_FALLBACK["gabung_fragmen"]),
                "saring": dict(_INFER_FALLBACK["saring"]),
                "ensemble": dict(_INFER_FALLBACK["ensemble"])}
        user = {}
        try:
            with open(str(path or INFER_DEFAULT), encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
        except (OSError, ValueError, yaml.YAMLError) as exc:
            # PENTING: yaml.YAMLError menurunkan dari Exception, BUKAN ValueError.
            # Kalau tidak ditangkap, satu indentasi salah di config/inferensi.yaml
            # membuat setiap request /api/detect balasan 500.
            _log.warning("config inferensi tidak terbaca (%s) - pakai default", exc)
            user = {}
        if isinstance(user, dict):
            for k in ("imgsz_gambar", "imgsz_live", "iou", "tta", "half_gambar",
                      "maks_sisi_proses"):
                if k in user:
                    data[k] = user[k]
            for k in ("model_gambar", "model_live"):
                nama = str(user.get(k, "") or "").strip().replace("\\", "/")
                nama = nama.split("/")[-1]  # hanya basename di weights/
                if nama.lower().endswith((".pt", ".onnx")) and nama != ".":
                    data[k] = nama
            dv = user.get("device", _INFER_FALLBACK["device"])
            dv = (_INFER_FALLBACK["device"] if dv is None
                  else str(dv).strip().lower())
            if dv not in ("auto", "cpu", "gpu") and not (
                    dv and all(c.isdigit() or c == "," for c in dv)):
                dv = _INFER_FALLBACK["device"]
            data["device"] = dv
            # mode_backend hanya auto|pt|onnx; nilai lain -> auto (lihat
            # backend_live). Sengaja terpisah dari validasi `device` di atas
            # karena aturannya berbeda.
            mb = user.get("mode_backend", _INFER_FALLBACK["mode_backend"])
            mb = (_INFER_FALLBACK["mode_backend"] if mb is None
                  else str(mb).strip().lower())
            if mb not in BACKEND_MODE:
                mb = _INFER_FALLBACK["mode_backend"]
            data["mode_backend"] = mb
            if isinstance(user.get("teliti"), dict):
                data["teliti"].update(user["teliti"])
        data["imgsz_gambar"] = int(_klamp(data["imgsz_gambar"], 320, 1536, 640))
        data["imgsz_live"] = int(_klamp(data["imgsz_live"], 320, 1280, 480))
        data["iou"] = _klamp(data["iou"], 0.1, 0.95, 0.5)
        data["tta"] = bool(data["tta"])
        data["half_gambar"] = bool(data["half_gambar"])
        # maks_sisi_proses: 0 = nonaktif, selain itu dijepit 320-4096. Nilai
        # tak masuk akal (teks, negatif, terlalu besar) jatuh ke batas aman.
        _m = _klamp(data.get("maks_sisi_proses"), 0, 8192, 0)
        data["maks_sisi_proses"] = 0 if _m <= 0 else int(_klamp(_m, 320, 4096, 0))
        t = data["teliti"]
        t["tile"] = int(_klamp(t.get("tile"), 320, 1280, 640))
        t["overlap"] = _klamp(t.get("overlap"), 0.0, 0.5, 0.25)
        t["iou_gabung"] = _klamp(t.get("iou_gabung"), 0.1, 0.95, 0.5)
        t["aktif_default"] = bool(t.get("aktif_default"))
        if str(t.get("metode_gabung", "nms")).lower() not in ("nms", "wbf"):
            t["metode_gabung"] = "nms"
        else:
            t["metode_gabung"] = str(t.get("metode_gabung", "nms")).lower()
        t["buang_tepi_tile"] = bool(t.get("buang_tepi_tile", True))
        t["iou_agnostik"] = _klamp(t.get("iou_agnostik", 0.6), 0.1, 0.95, 0.6)
        t["imgsz"] = int(_klamp(t.get("imgsz"), 320, 1536, 960))
        try:
            tk = {(k or ""): _klamp(v, 0.0, 0.9, None)
                  for k, v in dict(user.get("toleransi_kelas") or {}).items()}
            tk = {k: v for k, v in tk.items() if k and v is not None}
            if tk:
                merged = dict(data["toleransi_kelas"])
                merged.update(tk)
                data["toleransi_kelas"] = merged
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            lv = dict(user.get("live") or {})
            lv_default = _INFER_FALLBACK["live"]
            mf = int(lv.get("min_frames", lv_default["min_frames"]))
            data["live"]["min_frames"] = max(mf, 1)
            data["live"]["display_fps"] = int(_klamp(
                lv.get("display_fps", lv_default["display_fps"]), 5, 30,
                lv_default["display_fps"]))
            data["live"]["infer_interval"] = int(_klamp(
                lv.get("infer_interval", lv_default["infer_interval"]), 1, 10,
                lv_default["infer_interval"]))
            data["live"]["frame_diff_threshold"] = _klamp(
                lv.get("frame_diff_threshold", lv_default["frame_diff_threshold"]),
                0.0, 1.0, lv_default["frame_diff_threshold"])
            data["live"]["jpeg_quality"] = int(_klamp(
                lv.get("jpeg_quality", lv_default["jpeg_quality"]), 40, 95,
                lv_default["jpeg_quality"]))
            data["live"]["perataan_tampil"] = int(_klamp(
                lv.get("perataan_tampil", lv_default["perataan_tampil"]), 1, 60,
                lv_default["perataan_tampil"]))
            data["live"]["display_width"] = int(_klamp(
                lv.get("display_width", lv_default["display_width"]), 320, 1280,
                lv_default["display_width"]))
            data["live"]["cam_width"] = int(_klamp(
                lv.get("cam_width", lv_default["cam_width"]), 160, 1920,
                lv_default["cam_width"]))
            data["live"]["cam_height"] = int(_klamp(
                lv.get("cam_height", lv_default["cam_height"]), 120, 1080,
                lv_default["cam_height"]))
            data["live"]["cam_fps"] = int(_klamp(
                lv.get("cam_fps", lv_default["cam_fps"]), 5, 120,
                lv_default["cam_fps"]))
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            bu = dict(user.get("batas_ukuran") or {})
            for k in ("diameter_maks_cm", "lebar_retak_maks_cm", "luas_maks_m2",
                        "rasio_aspek_min_retak"):
                if k in bu:
                    data["batas_ukuran"][k] = max(float(bu[k]), 1.0)
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            gf = dict(user.get("gabung_fragmen") or {})
            data["gabung_fragmen"]["aktif"] = bool(gf.get("aktif", True))
            data["gabung_fragmen"]["iou_min"] = _klamp(gf.get("iou_min", 0.05),
                                                      0.0, 0.95, 0.05)
            data["gabung_fragmen"]["inter_min"] = _klamp(gf.get("inter_min", 0.3),
                                                        0.0, 1.0, 0.3)
            data["gabung_fragmen"]["lintas_kelas"] = bool(gf.get("lintas_kelas",
                                                                True))
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            sr = dict(user.get("saring") or {})
            data["saring"]["luas_min_px"] = max(float(sr.get("luas_min_px",
                                                             900)), 0.0)
            data["saring"]["maks_temuan"] = max(int(sr.get("maks_temuan",
                                                           20)), 0)
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            en = dict(user.get("ensemble") or {})
            data["ensemble"]["aktif"] = bool(en.get("aktif", False))
            kedua = str(en.get("model_kedua", "") or "").strip()
            kedua = kedua.replace("\\", "/").split("/")[-1]
            if kedua.lower().endswith((".pt", ".onnx")) and kedua != ".":
                data["ensemble"]["model_kedua"] = kedua
            data["ensemble"]["iou"] = _klamp(en.get("iou", 0.5),
                                             0.1, 0.95, 0.5)
            if str(en.get("metode", "wbf")).lower() not in ("nms", "wbf"):
                data["ensemble"]["metode"] = "wbf"
            else:
                data["ensemble"]["metode"] = str(en.get("metode",
                                                        "wbf")).lower()
        except (AttributeError, TypeError, ValueError):
            pass
        if path is None:
            _infer = data
        else:
            return data
    return _infer


def pilih_device(nilai="auto", model_file=None):
    """Terjemahkan setelan `device` menjadi argumen ultralytics.

    'auto' (default) -> 0 bila CUDA tersedia, jika tidak 'cpu'.
    'gpu' -> 0; 'cpu' -> 'cpu'; angka / '0,1' diteruskan apa adanya.
    Model .onnx SELALU 'cpu': tanpa paket onnxruntime-gpu hanya ada
    CPUExecutionProvider, dan memaksa GPU membuat ultralytics menuntut
    paket itu (bisa memicu unduhan otomatis).
    Selalu aman: bila torch/cuda tak ada, jatuh ke 'cpu' (bukan error).
    """
    if model_file and str(model_file).lower().endswith(".onnx"):
        return "cpu"
    d = str(nilai if nilai is not None else "auto").strip().lower()
    if d in ("", "auto"):
        try:
            import torch
            return 0 if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    if d == "gpu":
        return 0
    return d


# --- Deteksi perangkat & pemilihan backend otomatis ------------------------
# Kenapa ada: di mesin tanpa GPU (mis. laptop dosen di defense), torch hanya
# bisa jalan di CPU dan .pt jauh lebih lambat. onnxruntime CPU lebih cepat
# (i5-3470, imgsz 640, `model.track`: .pt 343 ms vs .onnx 157 ms).
# Syaratnya ONNX HANYA dipakai untuk jalur LIVE, karena:
#   (1) live memang tidak memakai TTA (pakai model.track, tanpa augment), jadi
#       tidak ada recall yang hilang;
#   (2) ultralytics MEMBUANG augment untuk backend non-PyTorch (onnx) —
#       lihat warning "['augment'] not supported by this model (format='onnx')" —
#       sedangkan jalur gambar bergantung pada TTA (docs §6b: recall 0,48 -> 0,69).
# Jalur gambar karena itu TIDAK pernah dialihkan ke ONNX.
_cuda_tersedia = None


def cuda_tersedia():
    """True bila torch melaporkan CUDA. Di-cache; Exception -> False.

    Dipisah dari pilih_device agar bisa dipatch saat test (hasil nyata
    tergantung mesin) tanpa memuat model.
    """
    global _cuda_tersedia
    if _cuda_tersedia is None:
        try:
            import torch
            _cuda_tersedia = bool(torch.cuda.is_available())
        except Exception:
            _cuda_tersedia = False
    return _cuda_tersedia


def nama_gpu():
    """Nama GPU pertama, atau '-' bila tak ada CUDA/torch tak terpasang."""
    if not cuda_tersedia():
        return "-"
    try:
        import torch
        return str(torch.cuda.get_device_name(0))
    except Exception:
        return "-"


def backend_live(mode=None, ada_cuda=None):
    """Nama bobot jalur live setelah mode_backend + status CUDA.

    mode:
      'pt'   -> selalu .pt (paksa, meski tanpa GPU)
      'onnx' -> selalu .onnx (paksa; fallback .pt bila berkas tak ada)
      'auto' -> .onnx bila TANPA CUDA, .pt bila ada CUDA (default)

    Mode auto tidak pernah membuat hasil KALAH: bila kembar .onnx tidak ada di
    weights/, tetap dipakai .pt (bukan error). `resolve_model` sengaja TIDAK
    disentuh supaya config `model_live` tetap apa adanya — aturan auto hanya
    berlaku di jalur live, bukan di config global.
    """
    inf = get_inferensi()
    m = str(mode if mode is not None else inf.get("mode_backend") or "auto")
    m = m.strip().lower()
    if m not in BACKEND_MODE:
        m = _INFER_FALLBACK["mode_backend"]
    dasar = resolve_model(kunci="model_live").name
    if m == "pt":
        return dasar
    if ada_cuda is None:
        ada_cuda = cuda_tersedia()
    pakai_onnx = (m == "onnx") or (m == "auto" and not ada_cuda)
    if not pakai_onnx:
        return dasar
    kembar = WEIGHTS_DIR / (str(dasar).rsplit(".", 1)[0] + ".onnx")
    return kembar.name if kembar.is_file() else dasar


def ringkasan_perangkat():
    """Info perangkat ringkas untuk /health dan KPI live."""
    cuda = cuda_tersedia()
    return {"cuda": cuda,
            "gpu": nama_gpu() if cuda else "-",
            "mode_backend": str(get_inferensi().get("mode_backend") or "auto"),
            "backend_live": backend_live()}


def half_untuk(device):
    """Half precision (FP16) hanya untuk GPU CUDA; di CPU dimatikan.

    Di CPU, FP16 sering lebih lambat / tak didukung sebagian op — paksa False.
    Model .onnx selalu 'cpu' via pilih_device, jadi otomatis False juga.
    """
    d = str(device).strip().lower()
    return d not in ("cpu", "", "none")


def half_gambar_untuk(device):
    """FP16 untuk JALUR GAMBAR — dipagari knob `half_gambar`.

    Ditemukan 17 Okt 2026: FP16 + TTA meluap (numerik) dan model mengeluarkan
    box NaN -> temuan asli hilang & pesan "ukuran tidak masuk akal" meledak.
    Diukur saat imgsz_gambar masih 960 (107 box, 102 NaN, vs 28 box 0 NaN di
    FP32). Default knob tetap false (FP32) walau kini imgsz 640, karena
    (1) tidak ada urge hemat VRAM di jalur gambar dan (2) FP32 justru lebih
    cepat di sini (tensor NaN membuat NMS/fusion lambat). Jalur live tetap
    memakai half_untuk() karena di imgsz 640 tanpa TTA terbukti 0 NaN.
    """
    if not get_inferensi().get("half_gambar", False):
        return False
    return half_untuk(device)


def _finite(*nilai):
    """True bila semua nilai bisa dikonversi float dan finite (bukan NaN/Inf)."""
    for v in nilai:
        try:
            if not math.isfinite(float(v)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _baris_rusak(row, conf=None):
    """True bila baris deteksi membawa NaN/Inf (box atau conf) dari model.

    Box NaN hanya bisa lolos dari overflow FP16 (lihat half_gambar_untuk).
    Tanpa penjaga ini NaN menyebar: wbf_gabung melebur rata-rata -> satu box
    NaN menulari tetangganya, lalu masuk_akal() menolaknya sebagai "ukuran
    tidak masuk akal" (menyesatkan) dan NaN bisa bocor ke JSON (browser gali
    JSON.parse). Return True = buang.
    """
    if conf is None:
        conf = row.get("conf", 0)
    if not _finite(conf):
        return True
    box = row.get("box")
    if box is not None:  # baris tanpa box (mis. hasil koreksi manual) dilewatkan
        try:
            b = [float(v) for v in box]
        except (TypeError, ValueError):
            return True
        if len(b) != 4 or not _finite(*b):
            return True
    for k in ("panjang_cm", "lebar_cm", "luas_m2"):
        v = row.get(k)
        if v is not None and not _finite(v):
            return True
    return False


def get_config():
    global _cfg
    if _cfg is None:
        _cfg = load_config(str(CFG_DEFAULT))
    return _cfg




PPC_MIN, PPC_MAKS = 0.05, 500.0  # px/cm wajar: 0,05 (jauh) s.d. 500 (makro)


def muat_ulang_config():
    """Buang cache severity agar deteksi berikutnya baca file terbaru."""
    global _cfg
    _cfg = None


def get_kalibrasi():
    """Status kalibrasi nyata dari config/severity.yaml (bukan klaim UI)."""
    cfg = get_config()
    try:
        ppc = float(cfg.get("pixels_per_cm", 8.0))
    except (TypeError, ValueError):
        ppc = 8.0
    kal = cfg.get("kalibrasi") if isinstance(cfg.get("kalibrasi"), dict) else {}
    return {"pixels_per_cm": ppc,
            "metode": str(kal.get("metode", "bawaan")),
            "diperbarui": str(kal.get("diperbarui", "-")),
            "catatan": str(kal.get("catatan", "default pabrik"))}


def hitung_ppc(panjang_px, panjang_cm):
    """Jarak klik (px) + panjang referensi (cm) -> px/cm. Validasi ketat."""
    try:
        px, cm = float(panjang_px), float(panjang_cm)
    except (TypeError, ValueError):
        raise ValueError("panjang_px dan panjang_cm harus angka.")
    if not (px > 0 and cm > 0):
        raise ValueError("panjang_px dan panjang_cm harus > 0.")
    if not (px < float("inf") and cm < float("inf")):
        raise ValueError("nilai tidak hingga.")
    ppc = px / cm
    if not (PPC_MIN <= ppc <= PPC_MAKS):
        raise ValueError(f"hasil {ppc:.2f} px/cm di luar wajar "
                         f"({PPC_MIN}-{PPC_MAKS}); cek titik klik/satuan.")
    return ppc


def simpan_kalibrasi(px_per_cm, metode="manual", catatan="", path=None):
    """Tulis pixels_per_cm + blok kalibrasi ke severity.yaml (preservatif).

    Komentar dan kunci lain dipertahankan; tulis atomik via file temp.
    Mengembalikan status seperti get_kalibrasi().
    """
    try:
        ppc = float(px_per_cm)
    except (TypeError, ValueError):
        raise ValueError("pixels_per_cm harus angka.")
    if not (ppc == ppc and PPC_MIN <= ppc <= PPC_MAKS):  # NaN lolos penalti
        raise ValueError(f"pixels_per_cm harus {PPC_MIN}-{PPC_MAKS}.")
    if metode not in ("manual", "penggaris"):
        raise ValueError("metode harus 'manual' atau 'penggaris'.")
    from datetime import datetime, timezone
    target = Path(path) if path else CFG_DEFAULT
    stempel = datetime.now(timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M %Z")
    # YAML-safe: satu baris, selalu dikutip ganda (catatan "-" polos = sekuens!).
    aman = str(catatan or "-").replace("\\", "\\\\").replace('"', '\\"')
    aman = " ".join(aman.split())
    blok = ["kalibrasi:", f"  metode: {metode}",
            f'  diperbarui: "{stempel}"', f'  catatan: "{aman}"']
    teks = target.read_text(encoding="utf-8").splitlines()
    keluar, tulis_blok = [], False
    for baris in teks:
        if baris.strip().startswith("pixels_per_cm:"):
            komen = baris.split("#", 1)[1] if "#" in baris else ""
            baris = f"pixels_per_cm: {ppc:.4f}"
            if komen.strip():
                baris += f"  # {komen.strip()}"
        if baris.strip() == "kalibrasi:":
            tulis_blok = True
            continue
        if tulis_blok:
            if baris[:1] in (" ", "\t") or not baris.strip():
                continue  # buang blok lama, tulis baru di bawah
            tulis_blok = False
            keluar += blok
        keluar.append(baris)
    if "kalibrasi:" not in keluar:
        keluar += blok
    import os as _os
    with _kalibrasi_lock:
        teks_baru = "\n".join(keluar) + "\n"
        fd, tmp_nama = None, None
        try:
            import tempfile as _tf
            fd, tmp_nama = _tf.mkstemp(dir=str(target.parent),
                                       prefix=target.stem + ".",
                                       suffix=".tmp")
            with _os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(teks_baru)
            _os.replace(tmp_nama, target)
        finally:
            if tmp_nama and _os.path.exists(tmp_nama):
                try:
                    _os.remove(tmp_nama)
                except OSError:
                    pass
    if path is None:
        muat_ulang_config()
    return get_kalibrasi() if path is None else {
        "pixels_per_cm": ppc, "metode": metode, "diperbarui": stempel,
        "catatan": catatan or "-"}


def ambang_efektif(kelas, conf_global, toleransi=None):
    """Ambang per kelas = slider - toleransi (slider tetap batas mutlak).

    Retak tipis boleh lolos di bawah slider, tapi menaikkan slider selalu
    memperketat semua kelas. Kelas tak dikenal / tanpa toleransi = slider.
    """
    try:
        tol = _klamp((toleransi or {})[kelas], 0.0, 0.9, None)
    except (KeyError, TypeError):
        return float(conf_global)
    if tol is None:
        return float(conf_global)
    return max(float(conf_global) - tol, 0.01)


def conf_prediksi(conf_global, toleransi=None):
    """Conf untuk predict: serendah ambang efektif terendah agar tak ada yang lolos."""
    try:
        maks_tol = max(float(v) for v in (toleransi or {}).values())
    except (TypeError, ValueError):
        maks_tol = 0.0
    return max(float(conf_global) - maks_tol, 0.01)


def alasan_tolak(item, batas=None):
    """Alasan penolakan geometri: None (lolos) | "ukuran" | "aspek".

    Dipisah dari boolean agar saring_rows() bisa menghitung "aspek"
    tersendiri — filter rasio aspek retak belum pernah diukur dampaknya
    (klaim "hampir pasti false positive" belum berangka), sehingga
    jumlah yang dibuangnya harus terlihat, bukan lumpuk di "ukuran".
    """
    b = batas or {}
    try:
        d_maks = float(b.get("diameter_maks_cm", 300))
        l_maks = float(b.get("lebar_retak_maks_cm", 100))
        luas_maks = float(b.get("luas_maks_m2", 100))
    except (TypeError, ValueError):
        return None
    c = str(item.get("kelas", "")).lower()
    try:
        pj = float(item.get("panjang_cm", 0))
        lb = float(item.get("lebar_cm", 0))
        luas = float(item.get("luas_m2", 0))
    except (TypeError, ValueError):
        return None
    if "crack" in c and "alligator" not in c:
        if not (lb <= l_maks):
            return "ukuran"
        # Retak longitudinal/transversal yang valid memanjang; box yang
        # near-square (rasio aspek < ambang) diduga false positive
        # (noda, bayangan, tekstur aspal). Alligator & pothole dikecualikan.
        # CATATAN: klaim ini BELUM diukur (lihat P2 rencana audit 2026-10-18);
        # dihitung terpisah sebagai "aspek" agar dampaknya terpantau.
        try:
            rasio_min = float(b.get("rasio_aspek_min_retak", 1.5))
        except (TypeError, ValueError):
            rasio_min = 1.5
        if rasio_min > 1.0 and lb > 0 and pj / lb < rasio_min:
            return "aspek"
        return None
    if "pothole" in c:
        return None if max(pj, lb) <= d_maks else "ukuran"
    return None if luas <= luas_maks else "ukuran"


def masuk_akal(item, batas=None):
    """Tolak box yang mustahil secara fisik menurut kalibrasi px/cm.

    Kompatibilitas: boolean. Untuk alasan penolakan, pakai alasan_tolak().
    """
    return alasan_tolak(item, batas) is None


def luas_px(row):
    """Luas box dalam px citra asli; -1 bila box tak tersedia (diloloskan)."""
    try:
        x1, y1, x2, y2 = (float(v) for v in row["box"])
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)
    except (KeyError, TypeError, ValueError):
        return -1.0


def saring_rows(rows, conf_global, ambang=None, batas=None, luas_min_px=0):
    """Saring rows -> (lolos, {'ambang': n, 'ukuran': n, 'aspek': n,
    'mungil': n, 'rusak': n}).

    'rusak' = box/conf NaN atau Inf (overflow FP16, lihat half_gambar_untuk).
    Dibuang lebih dulu agar lolos dari hitungan "ukuran tidak masuk akal" —
    tanpa ini NaN tersamar sebagai geometri tak wajar dan pesannya menyesatkan.
    'aspek' = retak near-square yang dibuang filter rasio aspek (dihitung
    terpisah karena dampaknya belum pernah diukur — lihat alasan_tolak()).
    """
    ok = []
    buang_ambang = buang_ukuran = buang_aspek = 0
    buang_mungil = buang_rusak = 0
    for r in rows:
        try:
            cf = float(r.get("conf", 0))
        except (TypeError, ValueError):
            buang_ambang += 1
            continue
        if _baris_rusak(r, cf):
            buang_rusak += 1
            continue
        if cf < ambang_efektif(r.get("kelas", ""), conf_global, ambang):
            buang_ambang += 1
            continue
        alasan = alasan_tolak(r, batas)
        if alasan is not None:
            if alasan == "aspek":
                buang_aspek += 1
            else:
                buang_ukuran += 1
            continue
        lp = luas_px(r)
        if luas_min_px > 0 and 0 <= lp < luas_min_px:
            buang_mungil += 1
            continue
        ok.append(r)
    return ok, {"ambang": buang_ambang, "ukuran": buang_ukuran,
                "aspek": buang_aspek, "mungil": buang_mungil,
                "rusak": buang_rusak}


def batas_topk(rows, maks=0):
    """Pagu N conf tertinggi -> (rows, n_dipangkas). maks <= 0 = tanpa batas."""
    if maks <= 0 or len(rows) <= maks:
        return list(rows), 0
    urut = sorted(rows, key=lambda r: -float(r.get("conf", 0)))
    return urut[:maks], len(urut) - maks


SEV_VALID = ("Ringan", "Sedang", "Berat")


def terapkan_koreksi(rows, hapus=None, severity=None):
    """Verifikasi operator: hapus baris + koreksi severity (hitung ulang skor prioritas).

    rows = hasil mentah AI (tak dimutasi). hapus = [idx_asli...],
    severity = {idx_asli: 'Ringan'|'Sedang'|'Berat'}. Koreksi severity
    menghitung ulang bahan + skor dari box (bila ada) lewat config aktif.
    Tiap baris hasil membawa 'sumber' ('AI') + 'idx_asli' + opsional 'diubah'.
    Mengembalikan (rows_baru, total, info {hapus, severity, total}).
    """
    cfg = get_config()
    hapus_set = set()
    for i in (hapus or []):
        try:
            hapus_set.add(int(i))
        except (TypeError, ValueError):
            pass
    sev_map = {}
    for k, v in (severity or {}).items():
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        if v in SEV_VALID:
            sev_map[i] = v
    out, n_hapus, n_sev = [], 0, 0
    for i, r in enumerate(rows or []):
        if i in hapus_set:
            n_hapus += 1
            continue
        r = dict(r)
        r.setdefault("sumber", "AI")
        r["idx_asli"] = i
        if i in sev_map and sev_map[i] != r.get("severity"):
            lama = r.get("severity", "-")
            baru_sev = sev_map[i]
            try:
                x1, y1, x2, y2 = (float(v) for v in r["box"])
                item = diagnose(r.get("kelas", "-"), x1, y1, x2, y2, cfg)
            except (KeyError, TypeError, ValueError):
                item = {"kelas": r.get("kelas", "-"),
                        "panjang_cm": r.get("panjang_cm", 0),
                        "lebar_cm": r.get("lebar_cm", 0),
                        "luas_cm2": r.get("luas_cm2", 0),
                        "makna": makna_untuk_kelas(r.get("kelas", "-")),
                        "dasar": r.get("dasar", "-")}
            item["severity"] = baru_sev
            item["bahan"] = cfg["bahan"][baru_sev]
            item["tebal_asumsi_cm"] = cfg["tebal_asumsi_cm"][baru_sev]
            baru = skor_prioritas(item)
            for k in ("conf", "box", "sumber", "idx_asli", "track_id", "frames"):
                if k in r:
                    baru[k] = r[k]
            baru["diubah"] = f"severity {lama}->{baru_sev}"
            r = baru
            n_sev += 1
        out.append(r)
    total = sum(int(r.get("skor_prioritas", 0)) for r in out)
    return out, total, {"hapus": n_hapus, "severity": n_sev,
                       "total": n_hapus + n_sev}


def kelas_mayoritas(votes, bawaan=None):
    """Kelas dengan suara terbanyak; seri -> yang terlihat lebih dulu."""
    if not votes:
        return bawaan
    return max(votes, key=votes.get)


def _iou_box(a, b):
    xx1, yy1 = max(a[0], b[0]), max(a[1], b[1])
    xx2, yy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])
    return inter / max(area(a) + area(b) - inter, 1e-9)


def wbf_gabung(boxes, skor, iou_thr=0.5):
    """Weighted Box Fusion murni-numpy per kelas -> [(box, skor, anggota)].

    Box bertumpuk dilebur (rata-rata berbobot skor) alih-alih dibuang seperti NMS.
    """
    import numpy as np

    boxes = np.asarray(boxes, dtype=float)
    skor = np.asarray(skor, dtype=float)
    if boxes.ndim != 2 or boxes.shape[1] != 4:
        return []
    # Buang baris non-finite dulu: fusion = rata-rata berbobot, jadi satu box
    # NaN (overflow FP16) membuat SELURUH cluster NaN dan temuan asli hilang.
    baik = np.isfinite(boxes).all(axis=1) & np.isfinite(skor)
    if not bool(baik.all()):
        boxes, skor = boxes[baik], skor[baik]
    if boxes.shape[0] == 0:
        return []
    cluster = []
    for i in np.argsort(-skor):
        for cl in cluster:
            if _iou_box(boxes[i], cl["box"]) > iou_thr:
                cl["anggota"].append(int(i))
                break
        else:
            cluster.append({"anggota": [int(i)], "box": boxes[i].copy()})
    hasil = []
    for cl in cluster:
        m = np.array(cl["anggota"])
        w = skor[m]
        tot = float(w.sum())
        w = (w / tot if (tot > 0 and math.isfinite(tot))
             else np.full(w.shape, 1.0 / len(w)))
        fb = (boxes[m] * w[:, None]).sum(axis=0)
        cl["box"] = fb
        hasil.append((fb, float(skor[m].mean()),
                      [int(x) for x in m]))
    hasil.sort(key=lambda t: -t[1])
    return hasil


def resolve_model(nama=None, kunci="model_gambar"):
    """Nama config -> Path bobot; hilang/rusak -> MODEL_DEFAULT (best.pt)."""
    try:
        nama = str(nama if nama is not None
                   else get_inferensi().get(kunci, "")).strip()
    except Exception:
        nama = ""
    nama = nama.replace("\\", "/").split("/")[-1]
    if nama.lower().endswith((".pt", ".onnx")):
        p = WEIGHTS_DIR / nama
        if p.exists():
            return p
    return MODEL_DEFAULT


def kanonik_kelas(nama):
    """Normalkan nama kelas model ke bentuk kanonik repo (underscore, huruf kecil).

    Bobot RDD2022 menyimpan nama dengan spasi & kapital (`longitudinal crack`,
    `Pothole`), sedangkan kode/config/UI memakai `longitudinal_crack` dst.
    Tanpa normalisasi: lookup `toleransi_kelas` selalu gagal (KeyError -> slider),
    dan UI menampilkan nama mentah alih-alih label Indonesia.
    """
    return "_".join(str(nama).strip().lower().split())


def _kanonik_names(names):
    """Ubah mapping {id: nama} model jadi nama kanonik. Tak mengubah input asli."""
    try:
        return {int(k): kanonik_kelas(v) for k, v in dict(names).items()}
    except (TypeError, ValueError, AttributeError):
        return names


def nama_kelas(names, idx):
    """Nama kelas kanonik untuk indeks `idx` (names: dict/list milik model).

    Satu-satunya jalur baca nama kelas dari model supaya normalisasi tak
    terlewat di salah satu call-site (gambar, teliti, ensemble, live).
    """
    return kanonik_kelas(names[idx])


def get_model(path=None, kunci="model_gambar", ruang=None):
    """Cache per (ruang, path): tiap jalur inferensi punya instance sendiri.

    `ruang` memisahkan instance meski file bobotnya sama. Ini wajib untuk
    live ("live") vs gambar (default): ultralytics menyimpan `predictor` dan
    `trackers` ByteTrack di instance, jadi berbagi satu objek membuat
    `predict()` menimpa state tracking live (dan sebaliknya).

    Lock hanya membungkus blok load (double-checked) — predict/track tetap
    tanpa lock agar FPS live tidak terdampak.
    """
    from ultralytics import YOLO

    lokasi = str(path or resolve_model(kunci=kunci))
    key = f"{ruang}::{lokasi}" if ruang else lokasi
    if key not in _models:
        with _model_lock:
            if key not in _models:
                _models[key] = YOLO(lokasi)
    return _models[key]


def nama_model(kunci="model_gambar"):
    """Nama file backend aktif (untuk label UI)."""
    return resolve_model(kunci=kunci).name


def resolve_model_live():
    """Path bobot live SETELAH aturan mode_backend (lihat backend_live).

    Dipakai seluruh jalur live; `resolve_model(kunci="model_live")` tetap
    tersedia untuk membaca nilai config apa adanya.
    """
    p = WEIGHTS_DIR / backend_live()
    if p.is_file():
        return p
    return resolve_model(kunci="model_live")


def model_live_aktif():
    """Objek model live yang benar-benar dipakai (sudah lewat cache).

    Ruang "live" memisahkan instance dari jalur gambar walau bobotnya sama,
    agar predictor/trackers ByteTrack tidak saling ditimpa.
    """
    return get_model(resolve_model_live(), ruang="live")


def nama_model_live():
    """Nama berkas model live aktif, mis. 'best.pt' atau 'best.onnx'."""
    return resolve_model_live().name


def resolve_scene_model():
    """Path bobot classifier kondisi jalan; None bila tidak tersedia.

    TIDAK fallback ke MODEL_DEFAULT — itu detektor, bukan classifier.
    """
    try:
        nama = str(get_inferensi().get("model_scene", "") or "").strip()
    except Exception:
        nama = ""
    nama = nama.replace("\\", "/").split("/")[-1]
    if nama.lower().endswith(".pt"):
        p = WEIGHTS_DIR / nama
        if p.exists():
            return p
    p = WEIGHTS_DIR / "scene_cls.pt"
    return p if p.exists() else None


_scene_model = None
_scene_lock = threading.Lock()


def get_scene_model():
    """Classifier kondisi jalan (YOLOv11n-cls IROSCD); None bila tak ada."""
    global _scene_model
    if _scene_model is None:
        with _scene_lock:
            if _scene_model is None:
                p = resolve_scene_model()
                if p is None:
                    return None
                from ultralytics import YOLO
                _scene_model = YOLO(str(p))
    return _scene_model


def baca_konfig_gate():
    """Parameter gate dari config/inferensi.yaml + default aman."""
    try:
        g = get_inferensi().get("scene_gate") or {}
    except Exception:
        g = {}
    try:
        aktif = bool(g.get("aktif", True))
    except Exception:
        aktif = True
    try:
        wet_min = float(g.get("wet_min", GATE_WET_MIN))
    except (TypeError, ValueError):
        wet_min = GATE_WET_MIN
    try:
        ambang = float(g.get("ambang_lubang", GATE_AMBANG))
    except (TypeError, ValueError):
        ambang = GATE_AMBANG
    return {"aktif": aktif, "wet_min": wet_min, "ambang_lubang": ambang}


def klasifikasi_scene(img):
    """Klasifikasi kondisi jalan -> {'label','conf','probs'} atau None.

    img: numpy array BGR (hasil decode_image). None bila model tak tersedia.
    'probs': 3 probabilitas teratas {label_kanonik: prob} — dipakai gate agar
    foto ambigu (basah+rusak) tetap terdeteksi sinyal basahnya.
    """
    try:
        m = get_scene_model()
    except Exception:
        return None
    if m is None:
        return None
    try:
        r = m.predict(img, verbose=False)[0]
        idx = int(r.probs.top1)
        import torch
        p = r.probs.data.flatten()
        k = min(3, len(p))
        topk = torch.topk(p, k=k)
        probs = {kanonik_kelas(r.names[int(i)]): round(float(c), 3)
                 for i, c in zip(topk.indices, topk.values)}
        return {"label": kanonik_kelas(r.names[idx]),
                "conf": round(float(r.probs.top1conf), 3),
                "probs": probs}
    except Exception:
        return None


def decode_image(raw: bytes):
    import numpy as np

    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Berkas bukan gambar yang valid (JPG/PNG).")
    return img


def exif_gps(raw: bytes):
    """Ambil (lat, lon) desimal dari EXIF foto HP. Kembalikan (None, None) bila tak ada/rusak."""
    try:
        from PIL import Image, ExifTags
        from io import BytesIO
        gps_tag = {v: k for k, v in ExifTags.GPSTAGS.items()}
        with Image.open(BytesIO(raw)) as im:
            exif = im.getexif()
            if not exif:
                return None, None
            g = exif.get_ifd(0x8825)  # IFD GPS (bukan nama tag — GPSTAGS tak punya "GPSInfo")
            if not g:
                return None, None

            def desimal(nilai, ref, pos, neg):
                d, m, s = (float(x) for x in nilai)
                v = d + m / 60 + s / 3600
                return v if ref == pos else -v

            lat = desimal(g[gps_tag["GPSLatitude"]], g[gps_tag["GPSLatitudeRef"]], "N", "S")
            lon = desimal(g[gps_tag["GPSLongitude"]], g[gps_tag["GPSLongitudeRef"]], "E", "W")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return None, None
            return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


def proses_detections(res, names, conf_digits=3, frame=None, skala_box=1.0):
    """Ubah Boxes ultralytics -> list dict siap JSON (pola app_streamlit.proses_hasil).

    Args:
        res: hasil prediksi ultralytics
        names: nama kelas model
        conf_digits: jumlah digit desimal confidence
        frame: gambar asli (optional, tidak dipakai saat ini)
        skala_box: pengali koordinat box. Dipakai bila inferensi dijalankan pada
            gambar yang sudah diperkecil (maks_sisi_proses): box hasil model ada
            di ruang gambar kecil, dikali 1/faktor agar kembali ke ruang gambar
            ASLI. Dengan begitu kalibrasi px/cm & severity tetap benar tanpa
            perubahan apa pun di hilir (masuk_akal, luas_px, verifikasi operator).
    """
    rows = []
    cfg = get_config()
    for b in res.boxes:
        cls = nama_kelas(names, int(b.cls[0]))
        x1, y1, x2, y2 = (float(v) * skala_box for v in b.xyxy[0])
        item = diagnose(cls, x1, y1, x2, y2, cfg)
        item["conf"] = round(float(b.conf[0]), conf_digits)
        item["box"] = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]

        rows.append(skor_prioritas(item))
    return rows


def gabung_fragmen(rows, iou_min=0.3, inter_min=0.5, lintas_kelas=True):
    """Lebur fragmen satu kerusakan -> satu box utuh (union-find).

    Model sering memecah kerusakan besar jadi kepingan kecil yang IoU-nya
    rendah (lolos NMS). Kepingan yang benar-benar tumpang tindih digabung:
    box = gabungan terluar, kelas/conf = anggota tertinggi, severity + skor
    prioritas DIHITUNG ULANG dari box gabungan (sekaligus menghentikan
    dobel-hitung skor fragmen yang bertumpuk). Mengembalikan (rows_baru,
    n_dilebur).

    **Ambang default 0.30/0.50 dipilih dengan pengukuran, bukan tebakan** (18 Okt 2026,
    BPID 161 gambar berlabel, IoU 0,5): aturan lama 0.05/0.30 menganggap dua
    pothole BERDAMPINGAN sebagai satu fragmen, lalu menyatukannya — satu pothole
    Ground-truth hilang dari hitungan. Diperketat ke 0.30/0.50, recall naik
    (F1 0,567 -> 0,597 di ambang 0,25; 0,616 di ambang 0,30) tanpa menambah FP.
    Kalau `inter_min` diturunkan lagi, dua kerusakan berbeda bisa tertukar lagi.
    """
    try:
        boxes = [[float(v) for v in r["box"]] for r in rows]
    except (KeyError, TypeError, ValueError):
        return list(rows), 0
    n = len(rows)
    induk = list(range(n))

    def cari(a):
        while induk[a] != a:
            induk[a] = induk[induk[a]]
            a = induk[a]
        return a

    def satu(a, b):
        a, b = cari(a), cari(b)
        if a != b:
            induk[max(a, b)] = min(a, b)

    for i in range(n):
        for j in range(i + 1, n):
            if not lintas_kelas and rows[i].get("kelas") != rows[j].get("kelas"):
                continue
            if (_iou_box(boxes[i], boxes[j]) > iou_min
                    or _inter_min(boxes[i], boxes[j]) > inter_min):
                satu(i, j)
    cluster = {}
    for i in range(n):
        cluster.setdefault(cari(i), []).append(i)
    if all(len(m) == 1 for m in cluster.values()):
        return list(rows), 0
    cfg = get_config()
    baru = []
    for m in cluster.values():
        if len(m) == 1:
            baru.append(rows[m[0]])
            continue
        m.sort(key=lambda i: -float(rows[i].get("conf", 0)))
        x1 = min(boxes[i][0] for i in m)
        y1 = min(boxes[i][1] for i in m)
        x2 = max(boxes[i][2] for i in m)
        y2 = max(boxes[i][3] for i in m)
        menang = rows[m[0]]
        item = diagnose(menang.get("kelas", "-"), x1, y1, x2, y2, cfg)
        item["conf"] = menang.get("conf", 0)
        item["box"] = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]
        row = skor_prioritas(item)
        row["fragmen"] = len(m)
        baru.append(row)
    baru.sort(key=lambda r: -float(r.get("conf", 0)))
    return baru, n - len(baru)


WARNA_SEV_BGR = {"Ringan": (74, 163, 22), "Sedang": (6, 119, 217), "Berat": (38, 38, 220)}


def _gambar_label(out, x1, y1, x2, y2, warna, label, fs, tebal):
    """Satu box + label yang dijepit dalam batas gambar (dipakai 2 jalur)."""
    h, w = out.shape[:2]
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, w - 1), min(y2, h - 1)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, tebal)
    cv2.rectangle(out, (x1, y1), (x2, y2), warna, tebal)
    lx, ly = x1, y1 - th - 8
    if ly < 0:  # box mepet atas -> label di DALAM box
        ly = y1 + 2
    lx = min(lx, w - tw - 4)
    cv2.rectangle(out, (lx, ly), (lx + tw + 4, ly + th + 8), warna, -1)
    cv2.putText(out, label, (lx + 2, ly + th + 4),
                cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), tebal, cv2.LINE_AA)


def anotasi_hasil(img_bgr, res, rows):
    """Gambar box + label sendiri (pengganti res.plot() default).

    Alasan: font plot() default bertumpuk/tidak terbaca saat box kecil
    berdekatan. Di sini: warna = severity (konsisten badge web), font scale
    proporsional tinggi gambar, label SELALU dijepit dalam batas gambar.
    Urutan rows == urutan res.boxes (loop yang sama di proses_detections).
    """
    out = img_bgr.copy()
    h, w = out.shape[:2]
    fs = max(0.5, h / 900.0)
    tebal = max(1, round(h / 600))
    for b, r in zip(res.boxes, rows):
        x1, y1, x2, y2 = map(int, map(float, b.xyxy[0]))
        warna = WARNA_SEV_BGR.get(r.get("severity", ""), (0, 102, 204))
        label = f"{r.get('kelas', '?')} {float(r.get('conf', 0)):.2f}"
        _gambar_label(out, x1, y1, x2, y2, warna, label, fs, tebal)
    return out


def anotasi_hasil_terpilih(img_bgr, res, semua_rows, keep_ids):
    """Anotasi hanya rows yang lolos saring (urutan res.boxes == semua_rows)."""
    out = img_bgr.copy()
    h, w = out.shape[:2]
    fs = max(0.5, h / 900.0)
    tebal = max(1, round(h / 600))
    for b, r in zip(res.boxes, semua_rows):
        if id(r) not in keep_ids:
            continue
        x1, y1, x2, y2 = map(int, map(float, b.xyxy[0]))
        warna = WARNA_SEV_BGR.get(r.get("severity", ""), (0, 102, 204))
        label = f"{r.get('kelas', '?')} {float(r.get('conf', 0)):.2f}"
        _gambar_label(out, x1, y1, x2, y2, warna, label, fs, tebal)
    return out


def anotasi_dari_rows(img_bgr, rows, skala_box=1.0):
    """Anotasi untuk jalur tiling (rows membawa kunci 'box').

    `skala_box` = pengali koordinat box saat DIGAMBAR. Dipakai bila `img_bgr`
    adalah gambar yang sudah diperkecil (maks_sisi_proses) sementara `rows`
    memakai koordinat gambar asli: kalikan dengan faktor pengecil agar box
    duduk pas di gambar yang digambar.
    """
    import numpy as np
    out = img_bgr.copy()
    h, w = out.shape[:2]
    fs = max(0.5, h / 900.0)
    tebal = max(1, round(h / 600))
    for r in rows:
        try:
            x1, y1, x2, y2 = (int(float(v) * skala_box) for v in r["box"])
        except (KeyError, TypeError, ValueError):
            continue
        warna = WARNA_SEV_BGR.get(r.get("severity", ""), (0, 102, 204))

        label = f"{r.get('kelas', '?')} {float(r.get('conf', 0)):.2f}"
        _gambar_label(out, x1, y1, x2, y2, warna, label, fs, tebal)
    return out


def grid_tile(w, h, tile=640, overlap=0.25):
    """Daftar pojok (x0, y0) tile persegi yang menutupi gambar (ada overlap)."""
    tile = max(int(tile), 64)
    overlap = min(max(float(overlap), 0.0), 0.5)
    step = max(int(tile * (1 - overlap)), 1)

    def mulai(n):
        if n <= tile:
            return [0]
        xs = list(range(0, n - tile + 1, step))
        if xs[-1] != n - tile:
            xs.append(n - tile)
        return xs

    return [(x, y) for y in mulai(h) for x in mulai(w)]


def sentuh_tepi_dalam(bx, x0, y0, t, w, h, margin=4):
    """True bila box menyentuh tepi tile yang BUKAN tepi gambar.

    Box demikian = objek terpotong tile; versi utuhnya tertangkap tile
    tetangga, jadi yang ini boleh dibuang (redam duplikat lintas tile).
    """
    bx1, by1, bx2, by2 = bx
    if x0 > 0 and bx1 <= margin:
        return True
    if y0 > 0 and by1 <= margin:
        return True
    if x0 + t < w and bx2 >= t - margin:
        return True
    if y0 + t < h and by2 >= t - margin:
        return True
    return False


def _inter_min(a, b):
    """Fraksi iris terhadap box terkecil (1.0 = box kecil tertelan utuh)."""
    xx1, yy1 = max(a[0], b[0]), max(a[1], b[1])
    xx2, yy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])
    return inter / max(min(area(a), area(b)), 1e-9)


def nms_agnostik(gabung, iou_thr=0.6, contain_thr=0.8):
    """NMS lintas kelas: gabung = [(box, conf, cls)] terurut menurun.

    Satu wilayah hanya dimenangi satu box (conf tertinggi) apa pun kelasnya.
    Selain IoU, box kecil yang tertelan box besar (inter/min > contain_thr)
    ikut digabung — kasus khas pothole-di-dalam-alligator.
    """
    simpan = []
    for g in gabung:
        for s in simpan:
            if (_iou_box(g[0], s[0]) > iou_thr
                    or _inter_min(g[0], s[0]) > contain_thr):
                break
        else:
            simpan.append(g)
    return simpan


def nms_gabung(boxes, skor, iou_thr=0.5):
    """Greedy NMS murni-numpy per kelas; kembalikan indeks yang dipertahankan."""
    import numpy as np

    boxes = np.asarray(boxes, dtype=float)
    skor = np.asarray(skor, dtype=float)
    urut = list(np.argsort(-skor))
    simpan = []
    while urut:
        i = urut.pop(0)
        simpan.append(i)
        if not urut:
            break
        sisa = np.array(urut)
        xx1 = np.maximum(boxes[i, 0], boxes[sisa, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[sisa, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[sisa, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[sisa, 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_s = ((boxes[sisa, 2] - boxes[sisa, 0])
                  * (boxes[sisa, 3] - boxes[sisa, 1]))
        iou = inter / np.maximum(area_i + area_s - inter, 1e-9)
        urut = [j for j, v in zip(urut, iou) if v <= iou_thr]
    return simpan


def prediksi_ensemble(ma, mb, img, conf=0.25, imgsz=640, iou=0.5,
                      tta_a=False, tta_b=False, iou_gabung=0.5,
                      metode="wbf", device=None, device_b=None, skala_box=1.0):
    """Dua model -> box gabungan per kelas (jalan Gambar saja).

    Kedua model diprediksi di conf_run yang sama, box per kelas dilebur via
    WBF (rata-rata berbobot) atau NMS (pemenang conf tertinggi). Kembalikan
    (semua_rows, info) — hilir (saring/fragmen/topk) sama seperti jalur tunggal.

    `skala_box` = pengali koordinat box (lihat proses_detections); box diskalakan
    SEKALI di awal, jadi WBF/NMS/diagnose seluruhnya sudah di ruang gambar asli.
    """
    import numpy as np

    ra = ma.predict(img, conf=conf, imgsz=imgsz, iou=iou, augment=bool(tta_a),
                    device=device, half=half_gambar_untuk(device),
                    verbose=False)[0]
    dev_b = device_b if device_b is not None else device
    rb = mb.predict(img, conf=conf, imgsz=imgsz, iou=iou, augment=bool(tta_b),
                    device=dev_b, half=half_gambar_untuk(dev_b),
                    verbose=False)[0]
    na, nb = len(ra.boxes), len(rb.boxes)
    per_kelas = {}
    for res in (ra, rb):
        for b in res.boxes:
            ci = int(b.cls[0])
            per_kelas.setdefault(ci, []).append(
                ([float(v) * skala_box for v in b.xyxy[0]], float(b.conf[0])))
    cfg = get_config()
    names = ma.names
    semua, n_gabung = [], 0
    for ci in sorted(per_kelas):
        grup = per_kelas[ci]
        boxes = [g[0] for g in grup]
        skor = [g[1] for g in grup]
        if len(grup) > 1:
            if metode == "nms":
                keep = nms_gabung(boxes, skor, iou_thr=iou_gabung)
                final = [(boxes[i], skor[i]) for i in keep]
            else:
                final = [(list(fb), fs)
                         for fb, fs, _ in wbf_gabung(boxes, skor,
                                                     iou_thr=iou_gabung)]
            n_gabung += len(grup) - len(final)
        else:
            final = [(boxes[0], skor[0])]
        for (x1, y1, x2, y2), fs in final:
            item = diagnose(nama_kelas(names, ci), x1, y1, x2, y2, cfg)
            item["conf"] = round(float(fs), 3)
            item["box"] = [round(x1, 1), round(y1, 1), round(x2, 1),
                           round(y2, 1)]
            semua.append(skor_prioritas(item))
    return semua, {"n_mentah_a": na, "n_mentah_b": nb, "n_lebur": n_gabung}


def prediksi_teliti(model, img, conf=0.25, iou=0.5, tcfg=None, ambang=None,
                    batas=None, conf_digits=3, conf_slider=None,
                    luas_min_px=0, device=None):
    """Mode teliti: tile overlap -> deteksi per tile -> gabung per kelas.

    Mengembalikan (rows siap JSON, info_saring). Tiap tile dilihat model pada
    resolusi penuh tile, jadi retak kecil yang hilang saat downscale ikut
    terdeteksi. Gabung: 'nms' (buang duplikat) atau 'wbf' (lebur duplikat).

    FITUR INI SEKARANG MANUAL SAJA. Pemicu otomatis untuk gambar besar pernah
    ada (aturan sisi > imgsz x 2) dan sudah DICABUT setelah diukur di BPID
    (161 gambar berlabel, IoU 0,5, kelas pothole, ambang 0,17):

      jalur                         TP   FP   FN      P      R     F1  dtk/gbr
      full-frame @960 + TTA (dulu)  157  347   68  0,312  0,698  0,431     0,12
      tiling 640->960 + buang-tepi    5  705  220  0,007  0,022  0,011     2,56
      tiling 640->960 tanpa buang-tepi 7  847  218  0,008  0,031  0,013     2,56
      gabungan keduanya              158 1181   67  0,118  0,702  0,202     2,68

    Recall pada pothole besar (>600 px): full-frame 71%, tiling 0%. Melepas
    aturan buang-tepi hampir tidak menambah TP (5 -> 7) tapi menambah 142 FP,
    jadi penyebab utamanya bukan aturan tepi, melainkan skala tile 640 yang
    di-upscale ke 960: 1,5x magnifikasi membuat kerikil/daun terbaca pothole
    dan menutupi retak tipis. Angka "tiling menambah recall" yang pernah
    dicatat memakai foto TANPA label, di mana jumlah temuan yang tinggi
    disalahartikan sebagai recall yang baik.

    Mode ini masih berguna sebagai alat eksperimen recall retak (dicentang
    manual), tapi TIDAK boleh diaktifkan diam-diam. Full-frame @640 kini
    memberi F1 0,630 pada ambang 0,35 — jauh di atas tiling.
    """
    import numpy as np

    tcfg = tcfg or get_inferensi()["teliti"]
    if ambang is None or batas is None:
        _inf = get_inferensi()
        if ambang is None:
            ambang = _inf.get("toleransi_kelas")
        if batas is None:
            batas = _inf.get("batas_ukuran")
    h, w = img.shape[:2]
    tile = int(tcfg.get("tile", 640))
    # Resolusi inferensi per tile TERPISAH dari ukuran tile. Bukti empiris
    # (diag_teliti, 17 Okt 2026): model buta total pada imgsz 640 untuk retak
    # tipis (0 box) tapi menemukan 79 box pada 960 — karena itu tile 640
    # di-upscale ke imgsz_tile saat inferensi. Jangan samakan dengan `tile`.
    imgsz_tile = int(tcfg.get("imgsz", 960))
    buang_tepi = bool(tcfg.get("buang_tepi_tile", True))
    iou_ag = float(tcfg.get("iou_agnostik", 0.6))
    kotak, skor, kls = [], [], []
    n_tepi = 0
    n_rusak = 0  # box/conf NaN-Inf (overflow FP16) dibuang SEBELUM wbf_gabung
    for (x0, y0) in grid_tile(w, h, tile, tcfg.get("overlap", 0.25)):
        crop = img[y0:y0 + tile, x0:x0 + tile]
        res = model.predict(crop, conf=conf, imgsz=imgsz_tile, iou=iou,
                            device=device, half=half_gambar_untuk(device),
                            verbose=False)[0]
        for b in res.boxes:
            x1, y1, x2, y2 = map(float, b.xyxy[0])
            cf_b = float(b.conf[0])
            # Wajib duluan: wbf_gabung melebur rata-rata, jadi satu box NaN
            # akan membuat SELURUH box tetangganya NaN -> temuan asli hilang.
            if not _finite(x1, y1, x2, y2, cf_b):
                n_rusak += 1
                continue
            if buang_tepi and sentuh_tepi_dalam((x1, y1, x2, y2),
                                               x0, y0, tile, w, h):
                n_tepi += 1
                continue
            kotak.append([x1 + x0, y1 + y0, x2 + x0, y2 + y0])
            skor.append(cf_b)
            kls.append(int(b.cls[0]))
    info_awal = {"tepi_tile": n_tepi, "rusak": n_rusak}
    if not kotak:
        info_awal.update({"ambang": 0, "ukuran": 0, "aspek": 0,
                          "silang_kelas": 0})
        return [], info_awal
    boxes = np.array(kotak)
    skor = np.array(skor)
    kls = np.array(kls)
    iou_g = float(tcfg.get("iou_gabung", 0.5))
    metode = str(tcfg.get("metode_gabung", "nms")).lower()
    cfg = get_config()
    gabung = []  # (box, conf, cls)
    for c in np.unique(kls):
        m = np.where(kls == c)[0]
        if metode == "wbf":
            for fb, fs, _anggota in wbf_gabung(boxes[m], skor[m], iou_g):
                gabung.append((fb, fs, int(c)))
        else:
            for k in nms_gabung(boxes[m], skor[m], iou_g):
                gi = m[k]
                gabung.append((boxes[gi], float(skor[gi]), int(c)))
    gabung.sort(key=lambda t: -t[1])
    n_sebelum = len(gabung)
    gabung = nms_agnostik(gabung, iou_ag)
    info_awal["silang_kelas"] = n_sebelum - len(gabung)
    rows = []
    for xyxy, cf, ci in gabung:
        x1, y1, x2, y2 = map(float, xyxy)
        item = diagnose(nama_kelas(model.names, int(ci)), x1, y1, x2, y2, cfg)
        item["conf"] = round(float(cf), conf_digits)
        item["box"] = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]
        rows.append(skor_prioritas(item))
    # Saring terhadap ambang SLIDER (predict memakai conf terendah).
    lolos, info_saring = saring_rows(rows, conf if conf_slider is None else conf_slider,
                                     ambang, batas, luas_min_px)
    # Jumlahkan rusak dari penjaga sumber (n_rusak) dengan yang tertangkap
    # saring_rows (kalau-kalau WBF masih meloloskan NaN).
    info_saring["rusak"] = (int(info_saring.get("rusak", 0))
                            + int(info_awal.pop("rusak", 0)))
    info_saring.update(info_awal)
    return lolos, info_saring


def encode_jpg(img_bgr) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Gagal encode JPEG anotasi.")
    return buf.tobytes()


def cerahkan_malam(img_bgr):
    """Bantuan foto gelap: CLAHE di kanal L (ruang LAB).

    Hanya fotometrik (terang/kontras) — geometri piksel tetap, jadi kalibrasi
    pixels_per_cm dan box tidak berubah. BUKAN pengganti data latih malam.
    """
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return cv2.cvtColor(cv2.merge([clahe.apply(l), a, b]), cv2.COLOR_LAB2BGR)


GELAP_AMBANG_L = 60.0  # rata-rata kanal L (0-255) di bawah ini = foto gelap


def deteksi_gelap(img_bgr, ambang=GELAP_AMBANG_L):
    """True bila citra gelap (rata-rata kanal L LAB < ambang).

    Dipakai UI untuk menyarankan opsi 'Pencahayaan Rendah / Malam (CLAHE)'
    saat temuan kosong: model dilatih pada RDD2022 (siang), jadi foto malam
    adalah titik lemahnya dan pengguna sering tidak sadar opsinya ada.
    Murah (satu konversi warna, tanpa inferensi).
    """
    try:
        rerata_l = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)[:, :, 0].mean()
        return float(rerata_l) < float(ambang)
    except cv2.error:
        return False


def analisis_gambar(raw: bytes, conf: float = 0.30, model_path=None,
                    malam: bool = False, teliti: bool = False,
                    imgsz=None, iou=None):
    """Upload bytes -> {rows, total, model, gambar_jpg, gps, malam, teliti,
    gelap, disaring, scene}.

    `gambar_jpg` = byte JPEG anotasi; pemanggil yang menyimpannya (route web
    memakai gambar_sementara bertoken), jadi jalur ini bebas base64.

    `conf` di sini harus SAMA dengan `web/app.py CONF_DEFAULT` (0,30 sejak
    18 Okt 2026). Nilai default yang melenceng adalah jebakan: route selalu
    mengoper conf dari form, tapi pemanggil programatis yang relies on default
    akan diam-diam memakai ambang berbeda. `tests/test_inferensi.py`
    (`test_default_conf_slider_naik_030`) menjaga keduanya tetap sama.
    """
    model_file = str(model_path or resolve_model(kunci="model_gambar"))
    model = get_model(model_file)
    inf = get_inferensi()
    # TTA hanya didukung backend pt; onnx mengabaikannya (warning).
    tta = bool(inf["tta"]) and model_file.lower().endswith(".pt")
    imgsz = int(imgsz or inf["imgsz_gambar"])
    iou = float(iou if iou is not None else inf["iou"])
    ambang = inf.get("toleransi_kelas")
    batas = inf.get("batas_ukuran")
    saring = inf.get("saring") or {}
    try:
        luas_min = max(float(saring.get("luas_min_px", 0)), 0.0)
    except (TypeError, ValueError):
        luas_min = 0.0
    try:
        maks_temuan = max(int(saring.get("maks_temuan", 0)), 0)
    except (TypeError, ValueError):
        maks_temuan = 0
    conf_run = conf_prediksi(conf, ambang)  # predict serendah kelas terendah
    img = decode_image(raw)
    # --- Perkecil gambar untuk ANALISIS (maks_sisi_proses) -----------------
    # CATATAN JUJUR: memperkecil di sini BUKAN tanpa biaya. Model me-letterbox
    # ke imgsz_gambar, tetapi resampling dua tahap (pra-perkecil lalu letterbox)
    # menghilangkan detail frekuensi tinggi dibanding sekali letterbox langsung
    # dari resolusi asli — retak tipis bisa ikut hilang. Penghematannya hanya
    # untuk tahap murah yang linier terhadap jumlah piksel (cek gelap,
    # klasifikasi scene, CLAHE malam, anotasi, encode JPEG, base64). Karena itu
    # default = 0 (nonaktif); aktifkan hanya bila yakin detail kecil tak penting.
    # Box hasil model ada di ruang gambar kecil dan dikali `skala_box` di hilir
    # agar kembali ke koordinat gambar ASLI — kalibrasi px/cm, severity,
    # masuk_akal, dan verifikasi operator tak berubah.
    # Mode teliti DILEWATI: gunanya justru detail resolusi asli.
    h0, w0 = img.shape[:2]
    maks_sisi = int(inf.get("maks_sisi_proses", 0) or 0)
    perkecil = 1.0
    if maks_sisi > 0 and not teliti and max(h0, w0) > maks_sisi:
        perkecil = maks_sisi / float(max(h0, w0))
        img = cv2.resize(
            img,
            (max(1, int(round(w0 * perkecil))),
             max(1, int(round(h0 * perkecil)))),
            interpolation=cv2.INTER_AREA)
    skala_box = 1.0 / perkecil  # box (ruang kecil) -> ruang gambar asli
    # Dicek SEBELUM cerahkan_malam: yang diukur kondisi asli unggahan, karena
    # flag ini justru untuk menyarankan opsi malam ke pengguna.
    gelap = deteksi_gelap(img)
    # CATATAN: dulu ada pemicu "mode teliti otomatis" untuk gambar besar (sisi >
    # imgsz x 2). Sudah DICABUT (18 Okt 2026) setelah diukur di BPID: tiling
    # 640->960 memberi F1 0,011 vs 0,431 untuk full-frame, dengan recall 0% pada
    # pothole besar. Angkanya di docstring prediksi_teliti(). Mode teliti kini
    # hanya jalan bila operator mencentangnya sendiri (alat eksperimen).
    # --- Gate kondisi jalan: klasifikasi scene SEBELUM cerahkan_malam agar
    # classifier melihat foto asli (sesuai data latih IROSCD). ---
    cfg_gate = baca_konfig_gate()
    scene = klasifikasi_scene(img) if cfg_gate["aktif"] else None
    gate_aktif = (scene is not None
                  and putuskan_gate(scene.get("probs"), cfg_gate["wet_min"]))
    if malam:
        img = cerahkan_malam(img)
    lat, lon = exif_gps(raw)
    gf = inf.get("gabung_fragmen") or {}
    model_label = Path(model_file).name
    device = pilih_device(inf.get("device"), model_file)
    if teliti:
        rows, info = prediksi_teliti(model, img, conf=conf_run, iou=iou,
                                     tcfg=inf["teliti"], ambang=ambang,
                                     batas=batas, conf_slider=conf,
                                     luas_min_px=luas_min, device=device)
    else:
        ens = inf.get("ensemble") or {}
        file_b = kedua = None
        if ens.get("aktif", False):
            kedua = resolve_model(ens.get("model_kedua"), kunci="model_live")
            file_b = str(kedua)
            if file_b == model_file:
                kedua = None  # sama dengan utama -> jalur tunggal
        if kedua is not None:
            model_b = get_model(file_b)
            if (_kanonik_names(model_b.names) != _kanonik_names(model.names)):
                kedua = None  # kelas beda -> jalur tunggal (aman)
        if kedua is not None:
            tta_b = bool(inf["tta"]) and file_b.lower().endswith(".pt")
            semua, info = prediksi_ensemble(
                model, model_b, img, conf=conf_run, imgsz=imgsz, iou=iou,
                tta_a=tta, tta_b=tta_b,
                iou_gabung=float(ens.get("iou", 0.5)),
                metode=str(ens.get("metode", "wbf")), device=device,
                device_b=pilih_device(inf.get("device"), file_b),
                skala_box=skala_box)
            info["ensemble"] = {"model_a": Path(model_file).name,
                                "model_b": Path(file_b).name,
                                "metode": str(ens.get("metode", "wbf")),
                                **{k: v for k, v in info.items()
                                   if k != "ensemble"}}
            model_label = f"{Path(model_file).name}+{Path(file_b).name}"
            rows, info_saring = saring_rows(semua, conf, ambang, batas,
                                            luas_min)
            info_saring["ensemble"] = info.pop("ensemble")
            info_saring.update({k: v for k, v in info.items()
                                if k not in info_saring})
            info = info_saring
        else:
            res = model.predict(img, conf=conf_run, imgsz=imgsz, iou=iou,
                                augment=tta, device=device,
                                half=half_gambar_untuk(device),
                                verbose=False)[0]
            semua = proses_detections(res, model.names, skala_box=skala_box)
            rows, info = saring_rows(semua, conf, ambang, batas, luas_min)
    if gf.get("aktif", True):
        rows, n_lebur = gabung_fragmen(rows,
                                       iou_min=float(gf.get("iou_min", 0.05)),
                                       inter_min=float(gf.get("inter_min", 0.3)),
                                       lintas_kelas=bool(gf.get("lintas_kelas",
                                                                True)))
        info["fragmen"] = n_lebur
    # --- Gate jalan basah: buang pothole ber-confidence rendah (kemungkinan
    # bercak air). Hanya saat scene wet_road terdeteksi; kegagalan gate =
    # kembali ke perilaku normal (status quo), bukan kesalahan baru. ---
    n_gate = 0
    if gate_aktif:
        rows, n_gate = saring_gate_basah(rows, cfg_gate["ambang_lubang"])
    info["gate"] = {"aktif": bool(gate_aktif), "disaring": n_gate,
                    "ambang_lubang": (cfg_gate["ambang_lubang"]
                                      if gate_aktif else None)}
    rows, n_pangkas = batas_topk(rows, maks_temuan)
    info["topk"] = n_pangkas
    # Faktor pengecil yang benar-benar dipakai (1,0 = resolusi asli). Terlihat di
    # `disaring` supaya bisa diaudit dari balasan API, bukan cuma dari log.
    info["skala_proses"] = round(perkecil, 4)
    gambar = anotasi_dari_rows(img, rows, skala_box=perkecil)
    total = sum(r["skor_prioritas"] for r in rows)
    return {
        "rows": rows,
        "total": total,
        "model": model_label,
        "gambar_jpg": encode_jpg(gambar),
        "gps": {"lat": lat, "lon": lon},
        "malam": malam,
        "teliti": bool(teliti),
        "gelap": bool(gelap),
        "disaring": info,
        "scene": ({"label": scene.get("label"),
                   "label_id": label_scene_id(scene.get("label")),
                   "conf": scene.get("conf"),
                   "prob_basah": round(float((scene.get("probs") or {})
                                             .get(WET_LABEL, 0.0)), 3),
                   "gate_aktif": bool(gate_aktif)}
                  if scene else None),
    }


def buat_pdf(rows, total, img_path=None, source="-", model_name="-",
             verifikasi=""):
    """rows + total -> path PDF sementara (pemanggil menghapus setelah dikirim).

    `img_path` = gambar bukti yang SUDAH ada di disk (gambar sementara bertoken
    atau gambar sesi tersimpan). Fungsi ini tidak memilikinya dan tidak
    menghapusnya. Gambar tidak valid ditangani buat_laporan seperti sebelumnya.
    """
    pdf_path = None
    try:
        meta = {"Sumber": source, "Model": model_name}
        if verifikasi:
            meta["Verifikasi operator"] = verifikasi
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
        buat_laporan(pdf_path, rows, total, img_path=img_path, meta=meta)
        return pdf_path
    except Exception:
        if pdf_path:
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Worker inferensi GPU khusus (anti "10 detik per request").
#
# Temuan empiris (17 Okt 2026, GTX 1650 4GB): inferensi CUDA PERTAMA di sebuah
# thread memakan ~10 detik (inisialisasi konteks CUDA per-thread), inferensi
# berikutnya di thread yang sama ~0,7 detik. Server dev Werkzeug melahirkan
# thread BARU per request -> setiap /api/detect membayar pajak 10 detik.
# Solusi: satu worker thread permanen; request HTTP mengantrekan kerjaan.
# ---------------------------------------------------------------------------
import queue as _queue

_kunci_pekerja = threading.Lock()
_thread_pekerja = None
_antrean_pekerja = None
_POLL_DETIK = 0.5  # jeda poll balasan worker (deteksi worker mati)


class WorkerInferensiMati(RuntimeError):
    """Worker inferensi berhenti saat sebuah job menunggu balasannya.

    Subclass RuntimeError agar pemanggil lama yang menangkap RuntimeError
    tetap aman, tetapi route bisa membedakannya dari kegagalan lain
    (mis. encode JPEG) dan membalas 503 alih-alih 500.
    """


def _loop_pekerja(antrean):
    # Pemanasan di thread ini: inisialisasi konteks CUDA sekali di awal,
    # sehingga request pertama pengguna tidak membayar biayanya.
    try:
        import numpy as _np
        inf = get_inferensi()
        model = get_model(kunci="model_gambar")
        device = pilih_device(inf.get("device"), str(resolve_model()))
        model.predict(_np.zeros((480, 640, 3), dtype=_np.uint8),
                      device=device, half=half_gambar_untuk(device),
                      verbose=False)
    except Exception:
        _log.exception("warmup worker inferensi gagal (diabaikan)")
    while True:
        fn, args, kwargs, balasan = antrean.get()
        try:
            balasan.put((True, fn(*args, **kwargs)))
        except Exception as e:  # noqa: BLE001 - teruskan ke peminta
            balasan.put((False, e))


def _pastikan_pekerja():
    """Pastikan ada worker hidup; lahirkan (ulang) bila belum ada atau mati.

    Worker hanya benar-benar mati bila thread-nya berhenti (mis. crash native
    di sisi CUDA). Tanpa cek `is_alive`, thread mati tetap dianggap hidup dan
    request baru mengantre pada queue yang tak akan pernah dilayani ->
    menggantung selamanya.
    """
    global _thread_pekerja, _antrean_pekerja
    t = _thread_pekerja
    if t is not None and t.is_alive():
        return
    with _kunci_pekerja:
        t = _thread_pekerja
        if t is not None and t.is_alive():
            return
        if t is not None:
            _log.warning("worker inferensi berhenti; memulai ulang")
        _antrean_pekerja = _queue.Queue()
        _thread_pekerja = threading.Thread(
            target=_loop_pekerja, args=(_antrean_pekerja,),
            name="inferensi-gpu", daemon=True)
        _thread_pekerja.start()


def start_worker_inferensi():
    """Mulai worker thread GPU + warmup. Dipanggil sekali saat startup server
    agar request pertama pun tidak membayar inisialisasi CUDA."""
    _pastikan_pekerja()


def status_sistem():
    """Ringkasan kesehatan TANPA efek samping (untuk endpoint /health).

    Tidak memuat model dan tidak membangunkan worker — hanya melaporkan
    keadaan saat ini. Dipakai monitoring/debugging, bukan bagian klaim naskah.
    """
    t = _thread_pekerja
    try:
        gate = baca_konfig_gate()
    except Exception:
        gate = {}
    try:
        imgsz = get_inferensi().get("imgsz_gambar")
    except Exception:
        imgsz = None
    try:
        perangkat = ringkasan_perangkat()
    except Exception:
        perangkat = {}
    return {
        "worker_inferensi": {
            "dijadwalkan": t is not None,
            "hidup": bool(t is not None and t.is_alive()),
        },
        "model_terload": sorted(str(k) for k in _models.keys()),
        "gate_jalan_basah": {
            "aktif": bool(gate.get("aktif")),
            "wet_min": gate.get("wet_min"),
        },
        "imgsz_gambar": imgsz,
        "perangkat": perangkat,
    }


def analisis_gambar_terjadwal(*args, **kwargs):
    """analisis_gambar via worker thread GPU khusus.

    Dipakai oleh route HTTP (tiap request = thread baru). Bila dipanggil dari
    dalam worker itu sendiri, jalan langsung (anti-deadlock).

    Batas tunggu berbasis LIVENESS, bukan jam dinding: selama worker yang
    melayani masih hidup kita tetap menunggu (job CPU / mode teliti bisa lama
    dan tetap sah). Bila worker mati atau diganti, gagal-cepat dengan
    WorkerInferensiMati alih-alih menggantung menanti balasan yang tak akan
    datang.
    """
    _pastikan_pekerja()
    if threading.current_thread() is _thread_pekerja:
        return analisis_gambar(*args, **kwargs)
    antrean, pekerja = _antrean_pekerja, _thread_pekerja
    balasan = _queue.Queue(maxsize=1)
    antrean.put((analisis_gambar, args, kwargs, balasan))
    while True:
        try:
            ok, hasil = balasan.get(timeout=_POLL_DETIK)
            break
        except _queue.Empty:
            if _thread_pekerja is not pekerja or not pekerja.is_alive():
                raise WorkerInferensiMati(
                    "Worker inferensi berhenti mendadak; coba lagi.")
    if not ok:
        raise hasil
    return hasil
