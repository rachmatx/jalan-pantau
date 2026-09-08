# weights/
Taruh `best.pt` hasil Kaggle di sini. Jangan commit ke Git.
- `best_yolo11n_seg.pt` (utama)
- `best_yolov8n_seg.pt` (pembanding)
- `best.onnx` (backend live; WAJIB dynamic-axes agar imgsz bebas — re-export:
  `YOLO('app/weights/best.pt').export(format='onnx', imgsz=960, dynamic=True)`.
  Statis-640 lama tak bisa jalan di 960.)
- `best_yolo11s.pt` (YOLOv11s RDD-only 2026-09-07, 9.4M param; val 0.648/test
  0.526/OOD-lokal 0.452) — AKTIF sebagai `model_gambar` sejak 2026-09-08
  (E2E: label `best_yolo11s.pt`, steady 1,4 dtk/foto dgn TTA).
- `best_yolo11s.onnx` (dinamis, 36 MB) — cadangan, belum dipakai (live tetap
  `best.onnx` n yang 2-5x lebih cepat).
