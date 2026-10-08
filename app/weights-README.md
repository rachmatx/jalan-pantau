# weights/

Bobot model untuk inferences. Jangan commit ke Git.

Semua model di sini adalah mode **deteksi bounding box**, bukan segmentasi.
Lihat `docs/Segmentasi-atau-Bounding-Box.md` untuk alasannya.

## Yang aktif

| Berkas | Ukuran | Peran |
|---|---|---|
| `best_yolo11s.pt` | 18,3 MB | Model gambar (foto statis). 9,4M parameter. Val mAP50 0,648, test RDD 0,526, OOD lokal 0,452. Aktif sebagai `model_gambar`. |
| `best.onnx` | 9,9 MB | Model live (webcam, IP-cam, video). YOLOv11n, lebih cepat di CPU. Aktif sebagai `model_live`. |

## Cadangan

| Berkas | Ukuran | Peran |
|---|---|---|
| `best.pt` | 5,2 MB | Model kedua untuk ensemble di tab Gambar. Nonaktif. |
| `best_yolo11s.onnx` | 36,3 MB | YOLOv11s dalam ONNX. Belum dipakai, live tetap `best.onnx` yang 2-5 kali lebih cepat. |

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