"""Export PDF laporan kerusakan + indeks prioritas (fpdf2)."""
from fpdf import FPDF

DISCLAIMER = (
    "Skor prioritas 0-100 per temuan (bobot severity: Ringan=33, Sedang=67, Berat=100). "
    "Formula usulan yang belum tervalidasi; bukan estimasi biaya. "
    "Dimensi diestimasi dari bounding box kamera mono terkalibrasi."
)

class LaporanPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "Laporan Kerusakan Jalan + Indeks Prioritas",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, "Deteksi YOLO + severity terkalibrasi + indeks prioritas",
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.multi_cell(0, 5, DISCLAIMER)

def _aman(teks, maks=48):
    """P2: Helvetica core-font hanya latin-1 + cell() tanpa wrap.
    Collapse whitespace, truncate dengan elipsis, ganti char di luar
    latin-1 (mis. emoji) agar tidak UnicodeEncodeError/overflow tabel."""
    s = " ".join(str(teks if teks is not None else "-").split())
    if len(s) > maks:
        s = s[:max(maks - 1, 0)] + "…"
    return s.encode("latin-1", "replace").decode("latin-1")


def buat_laporan(path, items, total, img_path=None, meta=None):
    pdf = LaporanPDF()
    pdf.add_page()
    if meta:
        pdf.set_font("Helvetica", "", 10)
        for k, v in meta.items():
            pdf.cell(0, 6, _aman(f"{k}: {v}", 120), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    if img_path:
        pdf.image(img_path, w=170)
        pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    widths = [8, 28, 32, 22, 28, 32, 20]
    for c, w in zip(["#", "Kelas", "Ukuran", "Severity", "Bahan", "Skor",
                     "Ket"], widths):
        pdf.cell(w, 7, c, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for i, it in enumerate(items, 1):
        ket = "ubah" if it.get("diubah") else str(it.get("sumber", "AI"))[:8]
        row = [_aman(str(i), 4), _aman(it.get("kelas", "-"), 16),
               _aman(it.get("dasar", "-"), 20), _aman(it.get("severity", "-"), 12),
               _aman(it.get("bahan", "-"), 18), _aman(it.get("skor_prioritas", "-"), 17),
               _aman(ket, 10)]
        for c, w in zip(row, widths):
            pdf.cell(w, 6, c, border=1)
        pdf.ln()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Total indeks prioritas: {int(total or 0)}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.output(path)
    return path
