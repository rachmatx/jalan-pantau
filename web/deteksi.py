"""Pipeline deteksi Flask: YOLO -> severity -> biaya (-> PDF di routes).

Modul terverifikasi dipakai ulang TANPA diubah: app/severity.py, app/biaya.py,
app/laporan.py. File ini hanya adaptor (I/O web) di atasnya.
"""
import base64
import sys
import tempfile
import threading
from pathlib import Path

import cv2

WEB_DIR = Path(__file__).parent
APP_DIR = WEB_DIR.parent / "app"
ROOT = WEB_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from severity import diagnose, load_config  # noqa: E402
from biaya import estimasi, load_harga  # noqa: E402
from laporan import buat_laporan  # noqa: E402

MODEL_DEFAULT = APP_DIR / "weights" / "best.pt"
WEIGHTS_DIR = APP_DIR / "weights"
CFG_DEFAULT = ROOT / "config" / "severity.yaml"
PRICE_DEFAULT = ROOT / "config" / "harga_acuan.csv"
INFER_DEFAULT = ROOT / "config" / "inferensi.yaml"

_models = {}  # path str -> YOLO (gambar pt + live onnx bisa hidup berdampingan)
_cfg = None
_prices = None
_infer = None
_model_lock = threading.Lock()  # jaga load singleton dari Flask thread + worker stream
_kalibrasi_lock = threading.Lock()  # P3: tulis severity.yaml atomik antar-thread

# Fallback bila config/inferensi.yaml hilang/rusak (perilaku mendekati setelan lama).
_INFER_FALLBACK = {
    "model_gambar": "best_yolo11s.pt", "model_live": "best.onnx",
    "imgsz_gambar": 960, "imgsz_live": 960, "iou": 0.5, "tta": False,
    "teliti": {"aktif_default": False, "tile": 640, "overlap": 0.25,
               "iou_gabung": 0.5, "metode_gabung": "nms",
               "buang_tepi_tile": True, "iou_agnostik": 0.6},
    "toleransi_kelas": {"longitudinal_crack": 0.13, "transverse_crack": 0.13,
                        "alligator_crack": 0.10, "other_corruption": 0.10,
                        "pothole": 0.0},
    "live": {"min_frames": 1},
    "batas_ukuran": {"diameter_maks_cm": 300, "lebar_retak_maks_cm": 100,
                     "luas_maks_m2": 100},
    "gabung_fragmen": {"aktif": True, "iou_min": 0.05, "inter_min": 0.3,
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
                "imgsz_gambar": _INFER_FALLBACK["imgsz_gambar"],
                "imgsz_live": _INFER_FALLBACK["imgsz_live"],
                "iou": _INFER_FALLBACK["iou"], "tta": _INFER_FALLBACK["tta"],
                "teliti": dict(_INFER_FALLBACK["teliti"]),
                "toleransi_kelas": dict(_INFER_FALLBACK["toleransi_kelas"]),
                "live": dict(_INFER_FALLBACK["live"]),
                "batas_ukuran": dict(_INFER_FALLBACK["batas_ukuran"]),
                "gabung_fragmen": dict(_INFER_FALLBACK["gabung_fragmen"]),
                "saring": dict(_INFER_FALLBACK["saring"]),
                "ensemble": dict(_INFER_FALLBACK["ensemble"])}
        user = {}
        try:
            import yaml
            with open(str(path or INFER_DEFAULT), encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            for k in ("imgsz_gambar", "imgsz_live", "iou", "tta"):
                if k in user:
                    data[k] = user[k]
            for k in ("model_gambar", "model_live"):
                nama = str(user.get(k, "") or "").strip().replace("\\", "/")
                nama = nama.split("/")[-1]  # hanya basename di weights/
                if nama.lower().endswith((".pt", ".onnx")) and nama != ".":
                    data[k] = nama
            if isinstance(user.get("teliti"), dict):
                data["teliti"].update(user["teliti"])
        except (OSError, ValueError):
            pass
        data["imgsz_gambar"] = int(_klamp(data["imgsz_gambar"], 320, 1536, 960))
        data["imgsz_live"] = int(_klamp(data["imgsz_live"], 320, 1280, 960))
        data["iou"] = _klamp(data["iou"], 0.1, 0.95, 0.5)
        data["tta"] = bool(data["tta"])
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
            mf = int((user.get("live") or {}).get("min_frames",
                                                  data["live"]["min_frames"]))
            data["live"]["min_frames"] = max(mf, 1)
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            bu = dict(user.get("batas_ukuran") or {})
            for k in ("diameter_maks_cm", "lebar_retak_maks_cm", "luas_maks_m2"):
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


def get_config():
    global _cfg
    if _cfg is None:
        _cfg = load_config(str(CFG_DEFAULT))
    return _cfg


def get_prices():
    global _prices
    if _prices is None:
        _prices = load_harga(str(PRICE_DEFAULT))
    return _prices


PPC_MIN, PPC_MAKS = 0.05, 500.0  # px/cm wajar: 0,05 (jauh) s.d. 500 (makro)


def muat_ulang_config():
    """Buang cache severity/harga agar deteksi berikutnya baca file terbaru."""
    global _cfg, _prices
    _cfg, _prices = None, None


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


def masuk_akal(item, batas=None):
    """Tolak box yang mustahil secara fisik menurut kalibrasi px/cm."""
    b = batas or {}
    try:
        d_maks = float(b.get("diameter_maks_cm", 300))
        l_maks = float(b.get("lebar_retak_maks_cm", 100))
        luas_maks = float(b.get("luas_maks_m2", 100))
    except (TypeError, ValueError):
        return True
    c = str(item.get("kelas", "")).lower()
    try:
        pj = float(item.get("panjang_cm", 0))
        lb = float(item.get("lebar_cm", 0))
        luas = float(item.get("luas_m2", 0))
    except (TypeError, ValueError):
        return True
    if "crack" in c and "alligator" not in c:
        return lb <= l_maks
    if "pothole" in c:
        return max(pj, lb) <= d_maks
    return luas <= luas_maks


def luas_px(row):
    """Luas box dalam px citra asli; -1 bila box tak tersedia (diloloskan)."""
    try:
        x1, y1, x2, y2 = (float(v) for v in row["box"])
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)
    except (KeyError, TypeError, ValueError):
        return -1.0


def saring_rows(rows, conf_global, ambang=None, batas=None, luas_min_px=0):
    """Saring rows -> (lolos, {'ambang': n, 'ukuran': n, 'mungil': n})."""
    ok, buang_ambang, buang_ukuran, buang_mungil = [], 0, 0, 0
    for r in rows:
        try:
            cf = float(r.get("conf", 0))
        except (TypeError, ValueError):
            buang_ambang += 1
            continue
        if cf < ambang_efektif(r.get("kelas", ""), conf_global, ambang):
            buang_ambang += 1
            continue
        if not masuk_akal(r, batas):
            buang_ukuran += 1
            continue
        lp = luas_px(r)
        if luas_min_px > 0 and 0 <= lp < luas_min_px:
            buang_mungil += 1
            continue
        ok.append(r)
    return ok, {"ambang": buang_ambang, "ukuran": buang_ukuran,
                "mungil": buang_mungil}


def batas_topk(rows, maks=0):
    """Pagu N conf tertinggi -> (rows, n_dipangkas). maks <= 0 = tanpa batas."""
    if maks <= 0 or len(rows) <= maks:
        return list(rows), 0
    urut = sorted(rows, key=lambda r: -float(r.get("conf", 0)))
    return urut[:maks], len(urut) - maks


SEV_VALID = ("Ringan", "Sedang", "Berat")


def terapkan_koreksi(rows, hapus=None, severity=None):
    """Verifikasi operator: hapus baris + koreksi severity (hitung ulang biaya).

    rows = hasil mentah AI (tak dimutasi). hapus = [idx_asli...],
    severity = {idx_asli: 'Ringan'|'Sedang'|'Berat'}. Koreksi severity
    menghitung ulang bahan + estimasi dari box (bila ada) lewat config aktif.
    Tiap baris hasil membawa 'sumber' ('AI') + 'idx_asli' + opsional 'diubah'.
    Mengembalikan (rows_baru, total, info {hapus, severity, total}).
    """
    cfg, prices = get_config(), get_prices()
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
                        "dasar": r.get("dasar", "-")}
            item["severity"] = baru_sev
            item["bahan"] = cfg["bahan"][baru_sev]
            item["tebal_asumsi_cm"] = cfg["tebal_asumsi_cm"][baru_sev]
            baru = estimasi(item, prices)
            for k in ("conf", "box", "sumber", "idx_asli", "track_id", "frames"):
                if k in r:
                    baru[k] = r[k]
            baru["diubah"] = f"severity {lama}->{baru_sev}"
            r = baru
            n_sev += 1
        out.append(r)
    total = sum(int(r.get("total_rp", 0)) for r in out)
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
        w = w / max(w.sum(), 1e-9)
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


def get_model(path=None, kunci="model_gambar"):
    """Cache per path: backend gambar (pt) + live (onnx) bisa berdampingan.

    Lock hanya membungkus blok load (double-checked) — predict/track tetap
    tanpa lock agar FPS live tidak terdampak.
    """
    from ultralytics import YOLO

    key = str(path or resolve_model(kunci=kunci))
    if key not in _models:
        with _model_lock:
            if key not in _models:
                _models[key] = YOLO(key)
    return _models[key]


def nama_model(kunci="model_gambar"):
    """Nama file backend aktif (untuk label UI)."""
    return resolve_model(kunci=kunci).name


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


def proses_detections(res, names, conf_digits=3):
    """Ubah Boxes ultralytics -> list dict siap JSON (pola app_streamlit.proses_hasil)."""
    rows = []
    cfg, prices = get_config(), get_prices()
    for b in res.boxes:
        cls = names[int(b.cls[0])]
        x1, y1, x2, y2 = map(float, b.xyxy[0])
        item = diagnose(cls, x1, y1, x2, y2, cfg)
        item["conf"] = round(float(b.conf[0]), conf_digits)
        item["box"] = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]
        rows.append(estimasi(item, prices))
    return rows


def gabung_fragmen(rows, iou_min=0.05, inter_min=0.3, lintas_kelas=True):
    """Lebur fragmen satu kerusakan -> satu box utuh (union-find).

    Model sering memecah kerusakan besar jadi kepingan kecil yang IoU-nya
    rendah (lolos NMS). Kepingan yang bersentuhan/tumpang tindih digabung:
    box = gabungan terluar, kelas/conf = anggota tertinggi, severity + biaya
    DIHITUNG ULANG dari box gabungan (sekaligus menghentikan dobel-hitung
    biaya fragmen yang bertumpuk). Mengembalikan (rows_baru, n_dilebur).
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
    cfg, prices = get_config(), get_prices()
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
        row = estimasi(item, prices)
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


def anotasi_dari_rows(img_bgr, rows):
    """Anotasi untuk jalur tiling (rows membawa kunci 'box')."""
    out = img_bgr.copy()
    h, w = out.shape[:2]
    fs = max(0.5, h / 900.0)
    tebal = max(1, round(h / 600))
    for r in rows:
        try:
            x1, y1, x2, y2 = (int(v) for v in r["box"])
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


def prediksi_ensemble(ma, mb, img, conf=0.25, imgsz=960, iou=0.5,
                      tta_a=False, tta_b=False, iou_gabung=0.5,
                      metode="wbf"):
    """Dua model -> box gabungan per kelas (jalan Gambar saja).

    Kedua model diprediksi di conf_run yang sama, box per kelas dilebur via
    WBF (rata-rata berbobot) atau NMS (pemenang conf tertinggi). Kembalikan
    (semua_rows, info) — hilir (saring/fragmen/topk) sama seperti jalur tunggal.
    """
    import numpy as np

    ra = ma.predict(img, conf=conf, imgsz=imgsz, iou=iou, augment=bool(tta_a),
                    verbose=False)[0]
    rb = mb.predict(img, conf=conf, imgsz=imgsz, iou=iou, augment=bool(tta_b),
                    verbose=False)[0]
    na, nb = len(ra.boxes), len(rb.boxes)
    per_kelas = {}
    for res in (ra, rb):
        for b in res.boxes:
            ci = int(b.cls[0])
            per_kelas.setdefault(ci, []).append(
                (list(map(float, b.xyxy[0])), float(b.conf[0])))
    cfg, prices = get_config(), get_prices()
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
            item = diagnose(names[ci], x1, y1, x2, y2, cfg)
            item["conf"] = round(float(fs), 3)
            item["box"] = [round(x1, 1), round(y1, 1), round(x2, 1),
                           round(y2, 1)]
            semua.append(estimasi(item, prices))
    return semua, {"n_mentah_a": na, "n_mentah_b": nb, "n_lebur": n_gabung}


def prediksi_teliti(model, img, conf=0.25, iou=0.5, tcfg=None, ambang=None,
                    batas=None, conf_digits=3, conf_slider=None,
                    luas_min_px=0):
    """Mode teliti: tile overlap -> deteksi per tile -> gabung per kelas.

    Mengembalikan (rows siap JSON, info_saring). Tiap tile dilihat model pada
    resolusi penuh tile, jadi retak kecil yang hilang saat downscale ikut
    terdeteksi. Gabung: 'nms' (buang duplikat) atau 'wbf' (lebur duplikat).
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
    buang_tepi = bool(tcfg.get("buang_tepi_tile", True))
    iou_ag = float(tcfg.get("iou_agnostik", 0.6))
    kotak, skor, kls = [], [], []
    n_tepi = 0
    for (x0, y0) in grid_tile(w, h, tile, tcfg.get("overlap", 0.25)):
        crop = img[y0:y0 + tile, x0:x0 + tile]
        res = model.predict(crop, conf=conf, imgsz=tile, iou=iou,
                            verbose=False)[0]
        for b in res.boxes:
            x1, y1, x2, y2 = map(float, b.xyxy[0])
            if buang_tepi and sentuh_tepi_dalam((x1, y1, x2, y2),
                                               x0, y0, tile, w, h):
                n_tepi += 1
                continue
            kotak.append([x1 + x0, y1 + y0, x2 + x0, y2 + y0])
            skor.append(float(b.conf[0]))
            kls.append(int(b.cls[0]))
    info_awal = {"tepi_tile": n_tepi}
    if not kotak:
        info_awal.update({"ambang": 0, "ukuran": 0, "silang_kelas": 0})
        return [], info_awal
    boxes = np.array(kotak)
    skor = np.array(skor)
    kls = np.array(kls)
    iou_g = float(tcfg.get("iou_gabung", 0.5))
    metode = str(tcfg.get("metode_gabung", "nms")).lower()
    cfg, prices = get_config(), get_prices()
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
        item = diagnose(model.names[int(ci)], x1, y1, x2, y2, cfg)
        item["conf"] = round(float(cf), conf_digits)
        item["box"] = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]
        rows.append(estimasi(item, prices))
    # Saring terhadap ambang SLIDER (predict memakai conf terendah).
    lolos, info_saring = saring_rows(rows, conf if conf_slider is None else conf_slider,
                                     ambang, batas, luas_min_px)
    info_saring.update(info_awal)
    return lolos, info_saring


def encode_jpg(img_bgr) -> str:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Gagal encode JPEG anotasi.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def cerahkan_malam(img_bgr):
    """Bantuan foto gelap: CLAHE di kanal L (ruang LAB).

    Hanya fotometrik (terang/kontras) — geometri piksel tetap, jadi kalibrasi
    pixels_per_cm dan box tidak berubah. BUKAN pengganti data latih malam.
    """
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return cv2.cvtColor(cv2.merge([clahe.apply(l), a, b]), cv2.COLOR_LAB2BGR)


def analisis_gambar(raw: bytes, conf: float = 0.25, model_path=None,
                    malam: bool = False, teliti: bool = False,
                    imgsz=None, iou=None):
    """Upload bytes -> {rows, total, model, image_b64, gps, malam, teliti, disaring}."""
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
    if malam:
        img = cerahkan_malam(img)
    lat, lon = exif_gps(raw)
    gf = inf.get("gabung_fragmen") or {}
    model_label = Path(model_file).name
    if teliti:
        rows, info = prediksi_teliti(model, img, conf=conf_run, iou=iou,
                                     tcfg=inf["teliti"], ambang=ambang,
                                     batas=batas, conf_slider=conf,
                                     luas_min_px=luas_min)
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
            if (dict(model_b.names) != dict(model.names)):
                kedua = None  # kelas beda -> jalur tunggal (aman)
        if kedua is not None:
            tta_b = bool(inf["tta"]) and file_b.lower().endswith(".pt")
            semua, info = prediksi_ensemble(
                model, model_b, img, conf=conf_run, imgsz=imgsz, iou=iou,
                tta_a=tta, tta_b=tta_b,
                iou_gabung=float(ens.get("iou", 0.5)),
                metode=str(ens.get("metode", "wbf")))
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
                                augment=tta, verbose=False)[0]
            semua = proses_detections(res, model.names)
            rows, info = saring_rows(semua, conf, ambang, batas, luas_min)
    if gf.get("aktif", True):
        rows, n_lebur = gabung_fragmen(rows,
                                       iou_min=float(gf.get("iou_min", 0.05)),
                                       inter_min=float(gf.get("inter_min", 0.3)),
                                       lintas_kelas=bool(gf.get("lintas_kelas",
                                                                True)))
        info["fragmen"] = n_lebur
    rows, n_pangkas = batas_topk(rows, maks_temuan)
    info["topk"] = n_pangkas
    gambar = anotasi_dari_rows(img, rows)
    total = sum(r["total_rp"] for r in rows)
    return {
        "rows": rows,
        "total": total,
        "model": model_label,
        "image_b64": encode_jpg(gambar),
        "gps": {"lat": lat, "lon": lon},
        "malam": malam,
        "teliti": bool(teliti),
        "disaring": info,
    }


def buat_pdf(rows, total, image_b64=None, source="-", model_name="-",
             verifikasi=""):
    """rows + total -> path PDF sementara (pemanggil menghapus setelah dikirim).

    P1: b64 tidak valid -> ValueError(400); kegagalan di tengah -> temp
    yang sudah dibuat dibersihkan agar tidak bocor di /tmp.
    """
    ann_path, pdf_path = None, None
    try:
        if image_b64:
            try:
                raw = base64.b64decode(image_b64, validate=True)
            except Exception:
                raise ValueError("Gambar anotasi rusak (base64 tidak valid).")
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(raw)
                ann_path = f.name
        meta = {"Sumber": source, "Model": model_name}
        if verifikasi:
            meta["Verifikasi operator"] = verifikasi
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
        buat_laporan(pdf_path, rows, total, img_path=ann_path, meta=meta)
        return pdf_path, ann_path
    except Exception:
        import os as _os
        for p in (pdf_path, ann_path):
            try:
                if p:
                    _os.remove(p)
            except OSError:
                pass
        raise
