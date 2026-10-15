"""Uji deteksi 17 foto RDD memakai best.onnx (onnxruntime) + modul severity/prioritas asli.

Menghasilkan:
  - reports/uji-foto-17/hasil.json  (rekap per foto)
  - reports/uji-foto-17/anotasi/    (gambar beranotasi)
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "app"))

from deteksi import get_config  # noqa: E402
from severity import diagnose  # noqa: E402
from prioritas import skor as skor_prioritas  # noqa: E402

NAMES = {
    0: "longitudinal_crack",
    1: "transverse_crack",
    2: "alligator_crack",
    3: "other_corruption",
    4: "pothole",
}
IMGSZ = 960
CONF = 0.25
IOU = 0.5


def letterbox(img, size=960):
    h, w = img.shape[:2]
    s = min(size / h, size / w)
    nh, nw = int(round(h * s)), int(round(w * s))
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    dh, dw = (size - nh) // 2, (size - nw) // 2
    canvas[dh:dh + nh, dw:dw + nw] = r
    return canvas, s, dw, dh


def nms(boxes, scores, thr):
    idx = scores.argsort()[::-1]
    keep = []
    while len(idx):
        i = idx[0]
        keep.append(i)
        if len(idx) == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[idx[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[idx[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[idx[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[idx[1:], 3])
        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        inter = w * h
        iou = inter / (
            (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
            + (boxes[idx[1:], 2] - boxes[idx[1:], 0]) * (boxes[idx[1:], 3] - boxes[idx[1:], 1])
            - inter + 1e-9
        )
        idx = idx[1:][iou <= thr]
    return keep


def main():
    os.chdir(ROOT)
    cfg = get_config()
    sess = ort.InferenceSession(
        str(ROOT / "app/weights/best.onnx"), providers=["CPUExecutionProvider"]
    )
    foto_dir = ROOT / "test_foto"
    out_dir = ROOT / "reports/uji-foto-17"
    anot_dir = out_dir / "anotasi"
    anot_dir.mkdir(parents=True, exist_ok=True)

    fotos = sorted(foto_dir.glob("China_MotorBike_*.jpg"))
    rekap = []
    for fp in fotos:
        img = cv2.imread(str(fp))
        if img is None:
            continue
        lb, s, dw, dh = letterbox(img, IMGSZ)
        blob = lb[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        pred = sess.run(None, {"images": blob})[0][0]  # [9, anchors]
        pred = pred.transpose(1, 0)  # [anchors, 9]
        boxes_cxcywh = pred[:, :4]
        cls_scores = pred[:, 4:]
        cls_id = cls_scores.argmax(1)
        conf = cls_scores.max(1)
        m = conf >= CONF
        boxes_cxcywh, cls_id, conf = boxes_cxcywh[m], cls_id[m], conf[m]
        # cxcywh -> xyxy dalam koordinat letterbox, lalu petakan ke asli
        x1 = (boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2 - dw) / s
        y1 = (boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2 - dh) / s
        x2 = (boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2 - dw) / s
        y2 = (boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2 - dh) / s
        boxes = np.stack([x1, y1, x2, y2], 1)

        temuan = []
        for c in range(5):
            cm = cls_id == c
            if not cm.any():
                continue
            for k in nms(boxes[cm], conf[cm], IOU):
                i = np.where(cm)[0][k]
                bx1, by1, bx2, by2 = map(float, boxes[i])
                item = diagnose(NAMES[c], bx1, by1, bx2, by2, cfg)
                item["conf"] = round(float(conf[i]), 3)
                item = skor_prioritas(item)
                item["box_xy"] = [round(bx1, 1), round(by1, 1), round(bx2, 1), round(by2, 1)]
                temuan.append(
                    {
                        "kelas": NAMES[c],
                        "conf": item["conf"],
                        "severity": item.get("severity"),
                        "luas_cm2": item.get("luas_cm2"),
                        "skor_prioritas": item.get("skor_prioritas"),
                        "box": item["box_xy"],
                    }
                )
        temuan.sort(key=lambda t: -t["skor_prioritas"])
        rekap.append({"foto": fp.name, "n_temuan": len(temuan), "temuan": temuan})

        # anotasi
        warna = {"Ringan": (46, 139, 87), "Sedang": (0, 165, 255), "Berat": (0, 0, 255)}
        an = img.copy()
        for t in temuan:
            bx1, by1, bx2, by2 = t["box"]
            sev = t["severity"] or "-"
            w = warna.get(sev, (200, 200, 200))
            p1, p2 = (int(bx1), int(by1)), (int(bx2), int(by2))
            cv2.rectangle(an, p1, p2, w, 2)
            cv2.putText(an, f"{t['kelas'][:12]} {t['conf']:.2f} {sev}", (p1[0], max(0, p1[1] - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, w, 1, cv2.LINE_AA)
        cv2.imwrite(str(anot_dir / fp.name), an)
        print(f"{fp.name}: {len(temuan)} temuan", flush=True)

    (out_dir / "hasil.json").write_text(
        json.dumps(rekap, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    total = sum(r["n_temuan"] for r in rekap)
    print(f"\nSELESAI: {len(rekap)} foto, {total} temuan -> {out_dir}/hasil.json")


if __name__ == "__main__":
    main()
