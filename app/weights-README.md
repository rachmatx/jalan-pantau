# weights/

Bobot model untuk inferences. Jangan commit ke Git.

Semua model di sini adalah mode **deteksi bounding box**, bukan segmentasi.
Lihat `docs/Segmentasi-atau-Bounding-Box.md` untuk alasannya.

## Yang aktif

Model tunggal **YOLOv11s**, dipakai untuk foto statis maupun live.
Val mAP50 0,616 · test RDD2022 0,617 · OOD Bandung (BPID) 0,581.

| Berkas | Peran |
|---|---|
| `best_yolo11s.pt` | Model gambar (foto statis), backend Ultralytics. Aktif sebagai `model_gambar`. |
| `best.onnx` | Ekspor ONNX model yang sama untuk live (webcam, IP-cam, video). Aktif sebagai `model_live`. |

## Cadangan

| Berkas | Peran |
|---|---|
| `best.pt` | Model kedua untuk ensemble di tab Gambar (`ensemble.model_kedua`). Nonaktif. |
| `best_yolo11s.onnx` | Ekspor ONNX `best_yolo11s.pt`, belum dipakai. |

## Catatan

- **ONNX untuk live wajib dynamic axes**, supaya `imgsz` bebas diubah.
  Cara export ulang:

  ```python
  from ultralytics import YOLO
  YOLO("app/weights/best.onnx").export(format="onnx", imgsz=480, dynamic=True)
  ```

  Ekspor statis ukuran 640 lama tidak bisa jalan di 960.
- **Integritas:** `SHA256SUMS.txt` berisi sidik jari tiap berkas. Verifikasi
  dengan `python scripts/verifikasi_bobot.py`.
- Pilihan model dan ukurannya diatur di `config/inferensi.yaml`
  (`model_gambar`, `model_live`, `model_kedua`).