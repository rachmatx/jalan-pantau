# weights/

Bobot model untuk inferences. Jangan commit ke Git.

Semua model di sini adalah mode **deteksi bounding box**, bukan segmentasi.
Lihat `docs/Segmentasi-atau-Bounding-Box.md` untuk alasannya.

## Yang aktif

Model tunggal **YOLOv11s** (retrain 18 Okt 2026, 92 epoch), dipakai untuk
foto statis maupun live.
Val mAP50 0,631 · test RDD2022 0,632 · OOD Bandung (BPID) 0,540
(n=161, indikatif).

| Berkas | Peran |
|---|---|
| `best.pt` | Model YOLOv11s untuk foto statis DAN live, backend Ultralytics. Aktif sebagai `model_gambar` sekaligus `model_live`. |
| `best.onnx` | Ekspor ONNX dari `best.pt` yang SAMA (v11s, 9,4 juta parameter). Cadangan jalur live untuk mesin tanpa GPU — dipilih otomatis oleh `mode_backend: auto` di `config/inferensi.yaml` (ada CUDA → `.pt`; CPU saja → `.onnx`). Jalur gambar tidak pernah dialihkan ke ONNX (TTA dibuang untuk backend non-PyTorch). |
| `scene_cls.pt` | Scene classifier YOLOv11n-cls (kondisi jalan: basah/normal/rusak/bergelombang). Latih sendiri di Kaggle dari dataset IROSCD (CC BY 4.0): test top-1 94,62% (seed 2, 246/260). Dipakai sebagai *gate* jalan basah: bila P(wet_road) ≥ `wet_min` (0,25), temuan pothole ber-conf < `ambang_lubang` (0,45) dibuang untuk menekan false positive bercak air. Aktif sebagai `model_scene`; logika di `app/scene_gate.py`. |

## Cadangan

Tidak ada. Ensemble dua model (`ensemble.model_kedua`) hanya bermakna bila kamu
menambahkan bobot kedua ke folder ini; tanpa itu `model_kedua == model_gambar`
dan deteksi memakai jalur tunggal.

## Catatan

- **ONNX untuk live WAJIB dynamic axes**, supaya `imgsz` benar-benar berubah.
  Ekspor ulang dari `best.pt` (bukan dari `best.onnx` — jangan berekspor dari
  hasil ekspor):

  ```python
  from ultralytics import YOLO
  YOLO("app/weights/best.pt").export(
      format="onnx", imgsz=640, dynamic=True, simplify=False, half=False)
  ```

  Ekspor STATIS 640 diam-diam **mengabaikan `imgsz`**: preset live 320/640/960
  semuanya jatuh ke 640 tanpa error. Teori ini sempat terjadi — berkas yang
  dipakai 18 Okt 2026 adalah ekspor statis, jadi bukan hanya "sebaiknya
  dynamic", tapi memang salah. Diperbaiki 19 Okt 2026; sumbu inputnya kini
  `['batch', 3, 'height', 'width']`.
- **Paritas hasil sudah diukur** (19 Okt 2026, frame nyata dari demo, CPU,
  conf 0,20): jumlah kotak dan nilai conf `.onnx` **identik** dengan `.pt` di
  imgsz 320 / 640 / 960. Yang berbeda hanya kecepatan (i5-3470, jalur CPU):
  `.pt` 92 / 266 / 538 ms vs `.onnx` 40 / 133 / 285 ms. Angka ini metode
  `predict`; benchmark lebih baru (26 Okt 2026) memakai metode `model.track`
  + NMS + ByteTrack dan menghasilkan angka berbeda (`.onnx` 157 ms, `.pt`
  343 ms @640) — lihat komentar `config/inferensi.yaml`. Jangan dicampur:
  metode berbeda, angka berbeda.
- **ONNX tidak bisa TTA.** Ultralytics membuang `augment` untuk backend
  non-PyTorch (warning `['augment'] not supported by this model
  (format='onnx')`). Karena itu `model_gambar` (yang butuh TTA) tidak pernah
  dialihkan ke ONNX — hanya jalur live, yang memang tidak memakai TTA.
- **Integritas:** `SHA256SUMS.txt` berisi sidik jari tiap berkas. Verifikasi
  dengan `python scripts/verifikasi_bobot.py`.
- Pilihan model dan ukurannya diatur di `config/inferensi.yaml`
  (`model_gambar`, `model_live`, `mode_backend`, `model_kedua`).