"""Prototype Streamlit: deteksi kerusakan jalan + severity + biaya + PDF.

Urutan uji: gambar -> file video -> webcam -> HP IP-camera.
Run dari root repo: streamlit run app/app_streamlit.py
Butuh: best.pt di app/weights/ (hasil Kaggle, Sel 11).
"""
import tempfile
from pathlib import Path

import cv2
import pandas as pd
import streamlit as st

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

from severity import diagnose, load_config
from biaya import estimasi, load_harga
from laporan import buat_laporan

APP_DIR = Path(__file__).parent
ROOT = APP_DIR.parent

st.set_page_config(page_title="Deteksi Kerusakan Jalan Live", layout="wide")
st.title("Deteksi Kerusakan Jalan Real-Time (YOLOv11n prototype)")

with st.sidebar:
    st.header("Konfigurasi")
    model_path = st.text_input("Model", str(APP_DIR / "weights" / "best.pt"))
    cfg_path = st.text_input("Ambang severity", str(ROOT / "config" / "severity.yaml"))
    price_path = st.text_input("Tabel harga", str(ROOT / "config" / "harga_acuan.csv"))
    conf = st.slider("Confidence", 0.05, 0.8, 0.25, 0.05)

try:
    cfg = load_config(cfg_path)
    prices = load_harga(price_path)
except Exception as e:
    st.error(f"Gagal load config/harga: {e}")
    st.stop()

st.subheader("Harga acuan (editable di config/harga_acuan.csv)")
st.dataframe(pd.DataFrame(prices), use_container_width=True)

mode = st.radio("Sumber", ["Gambar", "File video", "Webcam", "HP IP-camera"], horizontal=True)

if YOLO is None:
    st.error("ultralytics belum terinstall. Jalankan: pip install -r requirements.txt")
    st.stop()

@st.cache_resource
def load_model(path):
    return YOLO(path)

def proses_hasil(res, names):
    rows = []
    for b in res.boxes:
        cls = names[int(b.cls[0])]
        x1, y1, x2, y2 = map(float, b.xyxy[0])
        item = diagnose(cls, x1, y1, x2, y2, cfg)
        item["conf"] = round(float(b.conf[0]), 3)
        rows.append(estimasi(item, prices))
    return rows

if mode == "Gambar":
    f = st.file_uploader("Upload foto jalan", type=["jpg", "jpeg", "png"])
    if f and st.button("Deteksi"):
        import numpy as np
        model = load_model(model_path)
        img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        res = model.predict(img, conf=conf, verbose=False)[0]
        rows = proses_hasil(res, model.names)
        st.image(res.plot(), channels="BGR", use_container_width=True)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            total = sum(r["total_rp"] for r in rows)
            st.success(f"Total estimasi: Rp{total:,}".replace(",", "."))
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                ann_path = tmp.name + ".jpg"
                cv2.imwrite(ann_path, res.plot())
                buat_laporan(tmp.name, rows, total, img_path=ann_path,
                             meta={"Sumber": f.name, "Model": Path(model_path).name})
                st.download_button("Unduh laporan PDF", open(tmp.name, "rb"),
                                   file_name="laporan_jalan.pdf")
        else:
            st.info("Tidak ada kerusakan terdeteksi pada confidence ini.")
else:
    st.warning("Mode video/webcam/IP-camera: pakai model.track(persist=True) + ByteTrack (F3). "
               "Selesaikan mode Gambar + kalibrasi pixels_per_cm dulu.")
    if mode == "HP IP-camera":
        st.text_input("URL stream HP", "http://192.168.1.10:8080/video")
