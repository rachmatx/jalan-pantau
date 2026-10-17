"""Export PDF laporan kerusakan + SDI-visual per segmen (fpdf2)."""
from fpdf import FPDF

DISCLAIMER = (
    "Indeks prioritas = SDI-visual per segmen 100 m (Bina Marga 2011b, via "
    "paper sekunder; dokumen primer SMD-03/RCS tidak publik). "
    "Bekas roda tidak terdeteksi sehingga SDI bersifat parsial. "
    "Dimensi diestimasi dari bounding box kamera mono terkalibrasi. "
    "Skor severity per temuan (33/67/100) adalah data legacy dan tidak "
    "dipakai sebagai instrumen prioritas."
)


class LaporanPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "Laporan Kerusakan Jalan + SDI Segmen",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, "Deteksi YOLO + dimensi terkalibrasi + SDI-visual",
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
    """Laporan per sesi foto: tabel temuan (tanpa kolom skor).

    `total` (legacy: jumlah skor severity) diabaikan di tampilan; jumlah
    temuan dihitung dari items. Tanda tangan dipertahankan agar pemanggil
    lama (web/deteksi.py::buat_pdf) tidak berubah.
    """
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
    widths = [8, 34, 36, 24, 34, 34]
    for c, w in zip(["#", "Kelas", "Ukuran", "Severity", "Bahan", "Ket"],
                    widths):
        pdf.cell(w, 7, c, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for i, it in enumerate(items, 1):
        ket = "ubah" if it.get("diubah") else str(it.get("sumber", "AI"))[:8]
        row = [_aman(str(i), 4), _aman(it.get("kelas", "-"), 20),
               _aman(it.get("dasar", "-"), 22), _aman(it.get("severity", "-"), 14),
               _aman(it.get("bahan", "-"), 20), _aman(ket, 20)]
        for c, w in zip(row, widths):
            pdf.cell(w, 6, c, border=1)
        pdf.ln()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Jumlah temuan: {len(items or [])}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _aman(
        "Prioritas penanganan ditentukan di tingkat segmen via SDI-visual "
        "(menu Segmen), bukan dari tabel di atas.", 200))
    pdf.output(path)
    return path


def buat_laporan_segmen(path, detail):
    """Laporan SDI satu segmen. `detail` = dict web.database.detail_segmen()."""
    seg = detail
    sdi = detail.get("sdi") or {}
    pdf = LaporanPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, _aman(f"SDI Segmen: {seg.get('nama', '-')}", 90),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for k, v in (("Ruas", seg.get("jalan", "-")),
                 ("Panjang x lebar",
                  f"{seg.get('panjang_m')} m x {seg.get('lebar_m')} m"),
                 ("Jumlah sesi", str(len(seg.get("anggota", [])))),
                 ("Jumlah temuan", str(sdi.get("n_temuan_total", 0)))):
        pdf.cell(0, 6, _aman(f"{k}: {v}", 120), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Komponen SDI-visual", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    widths = [70, 30, 70]
    for c, w in zip(["Komponen", "Nilai", "Keterangan"], widths):
        pdf.cell(w, 7, c, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    baris = [
        ("SDI1 - luas retak", sdi.get("sdi1"), sdi.get("sdi1_ket")),
        ("SDI2 - lebar retak", sdi.get("sdi2"), sdi.get("sdi2_ket")),
        ("SDI3 - jumlah lubang", sdi.get("sdi3"), sdi.get("sdi3_ket")),
        ("SDI4 - bekas roda", sdi.get("sdi4"), sdi.get("sdi4_ket")),
    ]
    for nama, nilai, ket in baris:
        row = [_aman(nama, 40),
               _aman("-" if nilai is None else str(nilai), 16),
               _aman(ket or "-", 40)]
        for c, w in zip(row, widths):
            pdf.cell(w, 7, c, border=1)
        pdf.ln()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _aman(
        f"SDI total: {sdi.get('sdi_total', 0)}  ({sdi.get('kategori', '-')})", 90),
        new_x="LMARGIN", new_y="NEXT")
    manual = seg.get("sdi_manual")
    if manual is not None:
        try:
            selisih = abs(float(manual) - float(sdi.get("sdi_total", 0)))
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 7, _aman(
                f"SDI manual (lapangan): {manual} | selisih: {selisih:g}", 90),
                new_x="LMARGIN", new_y="NEXT")
        except (TypeError, ValueError):
            pass
    if sdi.get("n_tanpa_dimensi"):
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 5, _aman(
            f"Catatan: {sdi['n_tanpa_dimensi']} temuan tanpa data dimensi "
            "tidak masuk perhitungan.", 200))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Sesi anggota segmen", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    widths = [10, 45, 60, 25, 30]
    for c, w in zip(["#", "Waktu", "Lokasi", "Temuan", "Worst"], widths):
        pdf.cell(w, 7, c, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for i, s in enumerate(seg.get("anggota", []), 1):
        row = [_aman(str(i), 5), _aman(s.get("waktu", "-"), 26),
               _aman(s.get("lokasi", "-"), 34),
               _aman(str(s.get("n_temuan", 0)), 12),
               _aman(s.get("worst", "-"), 16)]
        for c, w in zip(row, widths):
            pdf.cell(w, 6, c, border=1)
        pdf.ln()
    pdf.output(path)
    return path
