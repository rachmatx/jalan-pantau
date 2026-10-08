"""Ukur kalibrasi (px/cm) dari FOTO keramik berpetak: deteksi garis nat.

Metode: garis nat (grout) gelap diasumsikan berjarak seragam = ukuran keramik
(30 cm). Jarak antar-garis dihitung dalam piksel -> px/cm.

Verifikasi: skrip menulis gambar overlay (garis terdeteksi) supaya bisa dicek
mata sebelum angkanya dipakai.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts/ukur_kalibrasi_foto.py --gambar "web/static/demo/jarak foto 49 - 53 cm.jpg"
    ... --tulis --nama "keramik30_pocoM6pro_50cm"
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "docs" / "contoh-validasi" / "kalibrasi.csv"


def _garis(profil, ambang_rasio=0.5, jarak_min=None):
    """Dari profil 1D (jumlah piksel per baris/kolom) -> posisi pusat garis."""
    p = profil.astype(float)
    if p.max() <= 0:
        return []
    aktif = p >= (p.max() * ambang_rasio)
    pusat, mulai = [], None
    for i, a in enumerate(aktif):
        if a and mulai is None:
            mulai = i
        elif not a and mulai is not None:
            pusat.append((mulai + i - 1) / 2)
            mulai = None
    if mulai is not None:
        pusat.append((mulai + len(aktif) - 1) / 2)
    if jarak_min:
        return [c for c in pusat if True]  # biarkan; penyaringan di pemanggil
    return pusat


def ukur(path, cm, tulis=False, nama=None, kernel_fraksi=3, rasio=0.5, roi=None):
    img = cv2.imread(str(path))
    if img is None:
        raise SystemExit(f"Gagal membuka: {path}")
    if roi:
        x1, y1, x2, y2 = roi
        img = img[y1:y2, x1:x2]
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # nat gelap -> threshold invers; blok besar agar toleran bayangan
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, 51, 7)

    # Garis horizontal: kernel lebar (fraksi lebar gambar); bisa dilenturkan
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // kernel_fraksi), 1))
    hor = cv2.morphologyEx(th, cv2.MORPH_OPEN, hk)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // kernel_fraksi)))
    ver = cv2.morphologyEx(th, cv2.MORPH_OPEN, vk)

    ys = _garis(hor.sum(axis=1) / 255.0, rasio)
    xs = _garis(ver.sum(axis=0) / 255.0, rasio)

    def spasial(positions):
        return [b - a for a, b in zip(positions, positions[1:])]

    semua = [v for v in (spasial(sorted(ys)) + spasial(sorted(xs))) if v >= 40]
    if not semua:
        raise SystemExit("Tidak ada garis nat terdeteksi. Coba foto lebih datar/terang.")
    # Ambil KLASTER jarak yang paling sering muncul (pitch keramik berulang),
    # lebih tahan terhadap kekacauan latar daripada median sederhana.
    semua.sort()
    klaster = []
    for v in semua:
        if klaster and v <= klaster[-1][-1] * 1.15:
            klaster[-1].append(v)
        else:
            klaster.append([v])
    terbaik = max(klaster, key=len)
    jarak_px = float(np.median(terbaik))
    ppc = jarak_px / cm

    # overlay verifikasi
    vis = img.copy()
    for y in ys:
        cv2.line(vis, (0, int(y)), (w, int(y)), (0, 0, 255), max(2, w // 500))
    for x in xs:
        cv2.line(vis, (int(x), 0), (int(x), h), (255, 0, 0), max(2, h // 500))
    out_dir = ROOT / "artifacts" / "ukur-kalibrasi"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (path.stem + "-overlay.jpg")
    cv2.imwrite(str(out), vis)

    print(f"gambar      : {path.name} ({w}x{h})")
    print(f"garis nat   : {len(ys)} horizontal, {len(xs)} vertikal")
    print(f"klaster px  : {len(terbaik)} dari {len(semua)} jarak  "
          f"(contoh {[round(v,1) for v in terbaik[:6]]})")
    print(f"jarak terpilih: {jarak_px:.1f} px  ->  {cm} cm")
    print(f"px/cm       : {ppc:.4f}")
    print(f"overlay     : {out.relative_to(ROOT)}")

    if tulis:
        nm = nama or f"keramik{int(cm)}_otomatis"
        with open(CSV, "a", encoding="utf-8") as f:
            f.write(f"{nm},{jarak_px:.1f},{cm},{ppc:.4f}\n")
        print(f"CSV         : +1 baris -> {CSV.relative_to(ROOT)}")
    return ppc


def main():
    ap = argparse.ArgumentParser(description="Ukur px/cm dari foto keramik berpetak.")
    ap.add_argument("--gambar", required=True)
    ap.add_argument("--cm", type=float, default=30.0, help="ukuran sisi keramik (cm)")
    ap.add_argument("--tulis", action="store_true", help="tambahkan baris ke CSV validasi")
    ap.add_argument("--nama", default=None)
    ap.add_argument("--kernel-fraksi", type=int, default=3,
                    help="panjang kernel = lebar/gambar dibagi nilai ini (kecil = lebih lentur)")
    ap.add_argument("--rasio", type=float, default=0.5,
                    help="ambang profil garis (kecil = lebih lentur)")
    ap.add_argument("--roi", default=None,
                    help='batasi ke area bersih: "x1,y1,x2,y2" (piksel gambar asli)')
    args = ap.parse_args()

    p = Path(args.gambar)
    if not p.is_absolute():
        p = ROOT / args.gambar
    if not p.is_file():
        raise SystemExit(f"Tidak ditemukan: {p}")
    roi = None
    if args.roi:
        roi = tuple(int(v) for v in args.roi.split(","))
        if len(roi) != 4:
            raise SystemExit('Format --roi: "x1,y1,x2,y2"')
    ukur(p, args.cm, args.tulis, args.nama,
         kernel_fraksi=args.kernel_fraksi, rasio=args.rasio, roi=roi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
