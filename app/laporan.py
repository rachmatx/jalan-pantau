"""Export PDF laporan kerusakan + SDI-visual per segmen (fpdf2).

Desain "hybrid" (disetujui user 1 Nov 2026): layout kartu KPI + panel
ringkasan + kartu komponen ala rancangan DeepSeek, dipadukan blok
pengesahan + blok validasi lapangan + warna primer aplikasi (#006194)
dari rancangan ASA. Acuan visual: ~/workspace/rancangan-pdf-jalanpantau/
(gaya-hybrid-sesi.png & gaya-hybrid-segmen.png).
"""
import math
import os
from datetime import datetime

from fpdf import FPDF

DISCLAIMER = (
    "Indeks prioritas = SDI-visual per segmen 100 m (Bina Marga 2011b, via "
    "paper sekunder; dokumen primer SMD-03/RCS tidak publik). "
    "Bekas roda tidak terdeteksi sehingga SDI bersifat parsial. "
    "Dimensi diestimasi dari bounding box kamera mono terkalibrasi. "
    "Skor severity per temuan (33/67/100) adalah data legacy dan tidak "
    "dipakai sebagai instrumen prioritas."
)

# --- Palet (samakan civic.css aplikasi) ---
PRIMER = (0, 97, 148)
AKSEN = (53, 182, 232)
INK = (15, 23, 42)
ABU = (90, 107, 126)
ABU2 = (132, 150, 171)
LATAR = (246, 249, 252)
GARIS = (226, 232, 240)
KEPALA_TBL = (234, 241, 248)
TEKS_TBL = (51, 83, 110)
PUTIH = (255, 255, 255)

SEV = {
    "Berat": {"bg": (253, 236, 236), "tx": (179, 38, 30),
              "titik": (217, 54, 54)},
    "Sedang": {"bg": (255, 241, 214), "tx": (138, 90, 0),
               "titik": (217, 119, 6)},
    "Ringan": {"bg": (228, 243, 232), "tx": (30, 123, 52),
               "titik": (30, 158, 74)},
}
SEV_ABU = {"bg": (241, 245, 249), "tx": (71, 85, 105), "titik": (100, 116, 139)}
URUT_SEV = {"Berat": 3, "Sedang": 2, "Ringan": 1}

KAT_WARNA = {"Baik": (30, 158, 74), "Sedang": (217, 119, 6),
             "Rusak Ringan": (239, 125, 26), "Rusak Berat": (217, 54, 54)}
KAT_LATAR = {"Baik": (228, 243, 232), "Sedang": (255, 241, 214),
             "Rusak Ringan": (253, 237, 220), "Rusak Berat": (253, 236, 236)}
PITA_KAT = {"Baik": "<50", "Sedang": "50-100",
            "Rusak Ringan": "100-150", "Rusak Berat": ">150"}

BULAN_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu",
            "Sep", "Okt", "Nov", "Des"]

X0, LEBAR = 10, 190  # margin kiri & lebar konten A4 (mm)
BATAS_BAWAH = 268    # y maks konten sebelum footer


def _aman(teks, maks=48):
    """Sanitasi teks untuk font inti latin-1: collapse whitespace, petakan
    karakter non-latin-1 yang umum (em-dash dsb.) ke padanan ASCII agar
    tidak berubah jadi '?', lalu potong dengan elipsis."""
    s = " ".join(str(teks if teks is not None else "-").split())
    for asal, ganti in (("—", "-"), ("–", "-"), ("→", "->"),
                        ("×", "x"), ("≤", "<="), ("≥", ">="),
                        ("…", "..."), ("•", "-"), ("“", '"'),
                        ("”", '"'), ("‘", "'"), ("’", "'")):
        s = s.replace(asal, ganti)
    if len(s) > maks:
        # ASCII: "…" hasil potong akan menjadi '?' setelah encode latin-1.
        s = s[:max(maks - 3, 0)] + "..."
    return s.encode("latin-1", "replace").decode("latin-1")


def _fmt_angka(v):
    """Format angka ala id-ID: koma desimal, tanpa nol ekor berlebih."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "-"
    s = f"{f:g}".replace(".", ",")
    return s


def _fmt_waktu(iso):
    """'2026-11-01T02:21:26' -> '1 Nov 2026, 02.21'. Gagal: apa adanya."""
    s = str(iso or "").strip()
    for pola in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S",
                 "%Y-%m-%d %H:%M"):
        try:
            d = datetime.strptime(s[:19], pola)
            return (f"{d.day} {BULAN_ID[d.month - 1]} {d.year}, "
                    f"{d.hour:02d}.{d.minute:02d}")
        except ValueError:
            continue
    return _aman(s, 26)


def _sev_dari(nama):
    """Kembalikan (label kanonik, palet) dari teks severity bebas."""
    s = str(nama or "").strip().capitalize()
    for k in ("Berat", "Sedang", "Ringan"):
        if s.startswith(k):
            return k, SEV[k]
    return (s or "-"), SEV_ABU


def _conf_dari(it):
    try:
        c = float(it.get("conf"))
        return c if 0 <= c <= 1 else None
    except (TypeError, ValueError):
        return None


def _potong_lebar(pdf, teks, lebar, maks=60):
    """Potong teks agar muat selebar `lebar` (mm) pada font aktif.

    Memotong per jumlah karakter tidak cukup: huruf courier 8,4 pt memakan
    ~1,8 mm, sehingga 24 karakter meluber dari sel 33 mm dan menutupi badge
    severity di sebelahnya.
    """
    s = _aman(teks, maks)
    if pdf.get_string_width(s) <= lebar:
        return s
    while s and pdf.get_string_width(s + "...") > lebar:
        s = s[:-1]
    return s.rstrip() + "..."


def _bungkus(pdf, teks, lebar):
    """Bungkus teks per kata mengikuti lebar string font aktif."""
    baris, cur = [], ""
    for kata in str(teks).split():
        coba = (cur + " " + kata).strip()
        if pdf.get_string_width(coba) <= lebar or not cur:
            cur = coba
        else:
            baris.append(cur)
            cur = kata
    if cur:
        baris.append(cur)
    return baris or [""]


def _crop_cover(img_path, rasio):
    """Potong tengah gambar ke rasio lebar:tinggi target (cover) menjadi
    berkas sementara; kembalikan path-nya atau None bila gagal / sudah
    sesuai (pemanggil memakai gambar asli). Pemanggil WAJIB menghapus
    berkas sementara setelah pdf.output() karena fpdf membaca gambar
    saat output dirender."""
    try:
        import tempfile
        from PIL import Image
        with Image.open(img_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            r = w / h
            if abs(r - rasio) < 0.02:
                return None
            if r > rasio:
                nw = int(h * rasio)
                x0 = (w - nw) // 2
                im = im.crop((x0, 0, x0 + nw, h))
            else:
                nh = int(w / rasio)
                y0 = (h - nh) // 2
                im = im.crop((0, y0, w, y0 + nh))
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            im.save(tmp, quality=88)
            return tmp
    except Exception:
        return None


class LaporanPDF(FPDF):
    judul_band = "LAPORAN"
    nomor_band = ""

    def header(self):
        if self.page_no() == 1:
            self.set_fill_color(*PRIMER)
            self.rect(0, 0, 210, 24, style="F")
            self.set_fill_color(*AKSEN)
            self.rect(0, 24, 210, 1.6, style="F")
            # logo
            self.set_fill_color(*PUTIH)
            self.rect(10, 5, 14, 14, style="F", round_corners=True,
                      corner_radius=2.5)
            self.set_font("helvetica", "B", 13)
            self.set_text_color(*PRIMER)
            self.set_xy(10, 8.6)
            self.cell(14, 6, "i:", align="C")
            self.set_text_color(*PUTIH)
            self.set_font("helvetica", "B", 13)
            self.set_xy(27, 6.4)
            self.cell(80, 6, "JalanPantau")
            self.set_font("helvetica", "B", 6.3)
            self.set_xy(27, 12.8)
            self.cell(80, 4, "S I S T E M   I N S P E K S I   J A L A N")
            # judul dokumen kanan
            self.set_font("helvetica", "B", 10.5)
            self.set_xy(90, 6.6)
            self.cell(110, 6, _aman(self.judul_band, 60), align="R")
            self.set_font("courier", "", 8.5)
            self.set_xy(90, 13)
            self.cell(110, 4.5, _aman(self.nomor_band, 40), align="R")
            self.set_y(29.5)
        else:
            self.set_fill_color(*PRIMER)
            self.rect(0, 0, 210, 10, style="F")
            self.set_font("helvetica", "B", 8)
            self.set_text_color(*PUTIH)
            self.set_xy(10, 2.6)
            self.cell(120, 5, "JalanPantau - " + _aman(self.judul_band, 50))
            self.set_font("courier", "", 8)
            self.set_xy(140, 2.6)
            self.cell(60, 5, _aman(self.nomor_band, 40), align="R")
            self.set_y(15)

    def footer(self):
        y = 281
        self.set_draw_color(*GARIS)
        self.set_line_width(0.3)
        self.line(X0, y, X0 + LEBAR, y)
        self.set_font("helvetica", "", 7)
        self.set_text_color(*ABU2)
        self.set_xy(X0, y + 1.6)
        self.cell(150, 4, "JalanPantau - Sistem Inspeksi Jalan - "
                          "laporan dibuat otomatis")
        self.set_font("courier", "", 7.5)
        self.set_xy(150, y + 1.6)
        self.cell(50, 4, f"Halaman {self.page_no()}/{{nb}}", align="R")


def _pdf_baru(judul, nomor):
    pdf = LaporanPDF()
    pdf.judul_band = judul
    pdf.nomor_band = nomor
    pdf.alias_nb_pages("{nb}")
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(X0, 10, X0)
    return pdf


def _judul_bagian(pdf, teks):
    y = pdf.get_y()
    if y > BATAS_BAWAH - 14:
        pdf.add_page()
        y = pdf.get_y()
    pdf.set_fill_color(*PRIMER)
    pdf.rect(X0, y + 0.5, 1.7, 4.8, style="F")
    pdf.set_font("helvetica", "B", 10.5)
    pdf.set_text_color(*INK)
    pdf.set_xy(X0 + 4, y)
    pdf.cell(0, 5.6, _aman(teks.upper(), 60))
    pdf.set_y(y + 7.9)


def _chip(pdf, x, y, teks, bg, tx, ukuran=8):
    pdf.set_font("helvetica", "B", ukuran)
    w = pdf.get_string_width(teks) + 6.5
    pdf.set_fill_color(*bg)
    pdf.rect(x, y, w, 5.4, style="F", round_corners=True, corner_radius=2.7)
    pdf.set_text_color(*tx)
    pdf.set_xy(x, y + 0.4)
    pdf.cell(w, 4.6, teks, align="C")
    pdf.set_text_color(*INK)
    return w


def _kotak_catatan(pdf, isi):
    pdf.set_font("helvetica", "", 8)
    baris = _bungkus(pdf, isi, 176)
    h = 4 + 4.6 + len(baris) * 4.15 + 2
    if pdf.get_y() + h > BATAS_BAWAH:
        pdf.add_page()
    y = pdf.get_y()
    pdf.set_fill_color(*LATAR)
    pdf.rect(X0, y, LEBAR, h, style="F")
    pdf.set_fill_color(*PRIMER)
    pdf.rect(X0, y, 1.7, h, style="F")
    pdf.set_font("helvetica", "B", 8.5)
    pdf.set_text_color(*INK)
    pdf.set_xy(X0 + 6, y + 2.2)
    pdf.cell(100, 4.6, "Catatan metodologi.")
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(61, 82, 105)
    pdf.set_xy(X0 + 6, y + 7)
    pdf.multi_cell(176, 4.15, isi)
    pdf.set_y(y + h + 3)


def _kepala_tabel(pdf, kolom):
    y = pdf.get_y()
    pdf.set_fill_color(*KEPALA_TBL)
    pdf.rect(X0, y, LEBAR, 8, style="F")
    pdf.set_font("helvetica", "B", 7.8)
    pdf.set_text_color(*TEKS_TBL)
    x = X0
    for label, w, rata in kolom:
        pdf.set_xy(x + 2, y + 1.2)
        pdf.cell(w - 3, 5.6, label, align=rata)
        x += w
    pdf.set_y(y + 8)
    pdf.set_text_color(*INK)


def _pengesahan(pdf):
    if pdf.get_y() > BATAS_BAWAH - 29:
        pdf.add_page()
    _judul_bagian(pdf, "Pengesahan")
    y = pdf.get_y()
    for x, label in ((X0, "Petugas lapangan,"), (X0 + 96, "Menyetujui,")):
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_text_color(*ABU)
        pdf.set_xy(x, y)
        pdf.cell(80, 5, label)
        pdf.set_draw_color(*INK)
        pdf.set_line_width(0.4)
        pdf.line(x, y + 14.5, x + 78, y + 14.5)
        pdf.set_font("helvetica", "B", 8.5)
        pdf.set_text_color(*INK)
        pdf.set_xy(x, y + 16)
        pdf.cell(80, 5, "( Nama / NIP )")
    pdf.set_y(y + 21.5)


# ============================ LAPORAN SESI ============================

def _nomor_sesi(meta):
    sid = meta.get("SesiID")
    waktu = str(meta.get("Waktu") or "")
    tgl = datetime.now()
    for pola in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            tgl = datetime.strptime(waktu[:19], pola)
            break
        except ValueError:
            continue
    if sid:
        return f"JP-{tgl:%Y%m%d}-{int(sid):03d}"
    return f"JP-{tgl:%Y%m%d}"


def buat_laporan(path, items, total, img_path=None, meta=None):
    """Laporan per sesi foto, desain hybrid. Tanda tangan dipertahankan:
    `total` legacy diabaikan di tampilan; semua ringkasan dihitung dari
    items. meta kini boleh memuat Waktu/Lokasi/Koordinat/Segmen/Nomor/
    SesiID (dari sesi tersimpan) — semua opsional."""
    items = [it for it in (items or []) if isinstance(it, dict)]
    meta = meta or {}
    pdf = _pdf_baru("LAPORAN INSPEKSI KERUSAKAN JALAN",
                    meta.get("Nomor") or _nomor_sesi(meta))
    pdf.add_page()

    # --- hitung ringkasan ---
    hitung_sev = {}
    kelas_ada = {}
    confs, luas_m2 = [], []
    terberat, skor_terberat = "-", 0
    for it in items:
        label, _ = _sev_dari(it.get("severity"))
        hitung_sev[label] = hitung_sev.get(label, 0) + 1
        if URUT_SEV.get(label, 0) > skor_terberat:
            skor_terberat, terberat = URUT_SEV[label], label
        k = str(it.get("kelas", "-"))
        kelas_ada[k] = kelas_ada.get(k, 0) + 1
        c = _conf_dari(it)
        if c is not None:
            confs.append(c)
        try:
            p, l = float(it.get("panjang_cm")), float(it.get("lebar_cm"))
            luas_m2.append(p * l / 10000.0)
        except (TypeError, ValueError):
            pass
    dominan = max(kelas_ada.items(), key=lambda kv: kv[1]) if kelas_ada else None

    # --- judul + chip status ---
    y = pdf.get_y()
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(*INK)
    pdf.set_xy(X0, y)
    pdf.cell(130, 8, "Hasil Deteksi Kerusakan Jalan")
    terverifikasi = bool(meta.get("Verifikasi operator"))
    if terverifikasi:
        teks_chip, bg_c, tx_c = "TERVERIFIKASI OPERATOR", (228, 243, 232), (30, 123, 52)
    else:
        teks_chip, bg_c, tx_c = "DRAF - BELUM DIVERIFIKASI", (253, 246, 233), (180, 83, 9)
    pdf.set_font("helvetica", "B", 7.8)
    w_chip = pdf.get_string_width(teks_chip) + 9
    pdf.set_draw_color(*tx_c)
    pdf.set_line_width(0.35)
    pdf.set_fill_color(*bg_c)
    pdf.rect(X0 + LEBAR - w_chip, y + 1, w_chip, 6.4, style="DF",
             round_corners=True, corner_radius=3)
    pdf.set_text_color(*tx_c)
    pdf.set_xy(X0 + LEBAR - w_chip, y + 1.7)
    pdf.cell(w_chip, 5, teks_chip, align="C")
    pdf.set_text_color(*INK)
    sub = []
    if meta.get("SesiID"):
        sub.append(f"Sesi #{meta['SesiID']}")
    if meta.get("Lokasi"):
        sub.append(_aman(meta["Lokasi"], 46))
    if meta.get("Model"):
        sub.append("model " + _aman(meta["Model"], 30))
    pdf.set_font("helvetica", "", 8.5)
    pdf.set_text_color(*ABU2)
    pdf.set_xy(X0, y + 9)
    pdf.cell(0, 5, "  |  ".join(sub) if sub else "Laporan hasil deteksi otomatis")
    pdf.set_text_color(*INK)
    pdf.set_y(y + 15)

    # --- kartu KPI ---
    rata_conf = (f"{round(sum(confs) / len(confs) * 100)}%"
                 if confs else "-")
    kpis = [("TEMUAN", str(len(items)), ABU2, INK),
            ("SEVERITY TERBERAT", terberat,
             SEV.get(terberat, SEV_ABU)["titik"],
             SEV.get(terberat, SEV_ABU)["tx"]),
            ("RATA-RATA CONF", rata_conf, PRIMER, INK),
            ("KELAS", str(len(kelas_ada)), ABU2, INK)]
    y = pdf.get_y()
    w_kpi = (LEBAR - 6) / 4
    for i, (label, nilai, aksen, warna) in enumerate(kpis):
        x = X0 + i * (w_kpi + 2)
        pdf.set_draw_color(*GARIS)
        pdf.set_line_width(0.35)
        pdf.set_fill_color(*PUTIH)
        pdf.rect(x, y, w_kpi, 13.5, style="DF", round_corners=True,
                 corner_radius=1.6)
        pdf.set_fill_color(*aksen)
        pdf.rect(x + 2, y + 1.4, w_kpi - 4, 1.1, style="F")
        pdf.set_font("helvetica", "B", 6.3)
        pdf.set_text_color(*ABU2)
        pdf.set_xy(x + 3.5, y + 3.4)
        pdf.cell(w_kpi - 6, 3.6, label)
        pdf.set_font("helvetica", "B", 12.5)
        pdf.set_text_color(*warna)
        pdf.set_xy(x + 3.5, y + 6.6)
        pdf.cell(w_kpi - 6, 6, nilai)
    pdf.set_text_color(*INK)
    pdf.set_y(y + 16)

    # --- data sesi ---
    _judul_bagian(pdf, "Data sesi")
    waktu_val = (_fmt_waktu(meta["Waktu"]) if meta.get("Waktu") else
                 f"{datetime.now().day} {BULAN_ID[datetime.now().month - 1]} "
                 f"{datetime.now().year}, {datetime.now():%H.%M}")
    sel = [("WAKTU", waktu_val),
           ("SUMBER", _aman(meta.get("Sumber", "-"), 40)),
           ("LOKASI", _aman(meta.get("Lokasi", "-"), 40)),
           ("KOORDINAT", _aman(meta.get("Koordinat", "-"), 34)),
           ("MODEL", _aman(meta.get("Model", "-"), 40)),
           ("SEGMEN TERKAIT", _aman(meta.get("Segmen", "-"), 40))]
    baris_sel = math.ceil(len(sel) / 3)
    y = pdf.get_y()
    tinggi_panel = baris_sel * 9.2 + 3.5
    pdf.set_fill_color(*LATAR)
    pdf.rect(X0, y, LEBAR, tinggi_panel, style="F", round_corners=True,
             corner_radius=2)
    for i, (k, v) in enumerate(sel):
        cx = X0 + 4 + (i % 3) * 62
        cy = y + 2 + (i // 3) * 9.2
        pdf.set_font("helvetica", "B", 6.3)
        pdf.set_text_color(*ABU2)
        pdf.set_xy(cx, cy)
        pdf.cell(58, 3.6, k)
        pdf.set_font("helvetica", "B", 8.8)
        pdf.set_text_color(*INK)
        pdf.set_xy(cx, cy + 3.6)
        pdf.cell(58, 4.6, v)
    pdf.set_y(y + tinggi_panel + 3.5)

    # --- foto bukti + ringkasan ---
    ada_foto = bool(img_path) and os.path.exists(str(img_path))
    berkas_crop = None
    if ada_foto:
        _judul_bagian(pdf, "Foto bukti")
        y = pdf.get_y()
        # Bingkai tetap 122x46 ala mockup: foto dipotong cover (tengah)
        # ke berkas sementara; berkas asli tidak diubah.
        foto_w, foto_h = 122, 46
        berkas_crop = _crop_cover(img_path, 122 / 46)
        ekstra_awal = []
        if dominan:
            ekstra_awal.append(1)
        if luas_m2:
            ekstra_awal.append(1)
        if confs:
            ekstra_awal.append(1)
        konten_h = 3.5 + 5.5 + 3 * 5.2 + 1.5 + len(ekstra_awal) * 8.4 + 1.5
        panel_h = max(foto_h + 6, konten_h)
        try:
            pdf.image(str(berkas_crop or img_path), x=X0, y=y,
                      w=foto_w, h=foto_h)
        except Exception:
            ada_foto = False
        if ada_foto:
            pdf.set_font("helvetica", "I", 7.3)
            pdf.set_text_color(*ABU2)
            pdf.set_xy(X0, y + foto_h + 1.2)
            pdf.cell(foto_w, 4, "Gambar 1. Overlay bounding box hasil deteksi.")
            px, pw = X0 + 128, LEBAR - 128
            pdf.set_fill_color(*LATAR)
            pdf.rect(px, y, pw, panel_h, style="F", round_corners=True,
                     corner_radius=2)
            ry = y + 3.5
            pdf.set_font("helvetica", "B", 6.5)
            pdf.set_text_color(*ABU2)
            pdf.set_xy(px + 4, ry)
            pdf.cell(pw - 8, 3.8, "RINGKASAN TEMUAN")
            ry += 5.5
            for nama in ("Berat", "Sedang", "Ringan"):
                pal = SEV[nama]
                pdf.set_fill_color(*pal["titik"])
                pdf.ellipse(px + 4, ry + 1, 2.7, 2.7, style="F")
                pdf.set_font("helvetica", "", 8.5)
                pdf.set_text_color(*INK)
                pdf.set_xy(px + 8.5, ry)
                pdf.cell(30, 4.4, nama)
                pdf.set_font("helvetica", "B", 8.5)
                pdf.set_xy(px + 4, ry)
                pdf.cell(pw - 8, 4.4, str(hitung_sev.get(nama, 0)), align="R")
                ry += 5.2
            ry += 1.5
            ekstra = []
            if dominan:
                ekstra.append(("KELAS DOMINAN",
                               f"{_aman(dominan[0], 24)} - {dominan[1]}"))
            if luas_m2:
                ekstra.append(("LUAS TOTAL",
                               _fmt_angka(sum(luas_m2)) + " m2"))
            if confs:
                ekstra.append(("CONFIDENCE",
                               f"{round(min(confs) * 100)}% - "
                               f"{round(max(confs) * 100)}%"))
            for k, v in ekstra:
                pdf.set_font("helvetica", "B", 6.3)
                pdf.set_text_color(*ABU2)
                pdf.set_xy(px + 4, ry)
                pdf.cell(pw - 8, 3.6, k)
                pdf.set_font("helvetica", "B", 9)
                pdf.set_text_color(*INK)
                pdf.set_xy(px + 4, ry + 3.4)
                pdf.cell(pw - 8, 4.6, v)
                ry += 8.4
            pdf.set_y(y + panel_h + 3)

    # --- tabel temuan ---
    _judul_bagian(pdf, "Tabel temuan")
    kolom = [("NO", 10, "C"), ("KELAS", 58, "L"), ("UKURAN", 36, "L"),
             ("SEVERITY", 28, "L"), ("CONF", 16, "C"), ("BAHAN", 42, "L")]
    _kepala_tabel(pdf, kolom)
    n_diubah = 0
    if not items:
        pdf.set_font("helvetica", "I", 9)
        pdf.set_text_color(*ABU)
        pdf.set_xy(X0, pdf.get_y() + 1)
        pdf.cell(LEBAR, 6, "Tidak ada temuan.", align="C")
        pdf.set_y(pdf.get_y() + 8)
        pdf.set_text_color(*INK)
    for i, it in enumerate(items):
        if pdf.get_y() + 7.2 > BATAS_BAWAH:
            pdf.add_page()
            _kepala_tabel(pdf, kolom)
        y = pdf.get_y()
        if i % 2 == 1:
            pdf.set_fill_color(*LATAR)
            pdf.rect(X0, y, LEBAR, 7.2, style="F")
        label_sev, pal = _sev_dari(it.get("severity"))
        if it.get("diubah"):
            n_diubah += 1
        x = X0
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_text_color(*ABU2)
        pdf.set_xy(x, y + 1.2)
        pdf.cell(10, 5.2, str(i + 1), align="C")
        x += 10
        pdf.set_font("helvetica", "B", 8.8)
        pdf.set_text_color(*INK)
        pdf.set_xy(x + 2, y + 1.2)
        pdf.cell(55, 5.2, _aman(it.get("kelas", "-"), 40))
        x += 58
        pdf.set_font("courier", "", 8.4)
        pdf.set_xy(x + 2, y + 1.4)
        pdf.cell(33, 5.2, _potong_lebar(pdf, it.get("dasar", "-"), 33))
        x += 36
        _chip(pdf, x + 2, y + 1.1, label_sev, pal["bg"], pal["tx"], 7.8)
        x += 28
        c = _conf_dari(it)
        pdf.set_font("courier", "", 8.4)
        pdf.set_text_color(*INK)
        pdf.set_xy(x, y + 1.4)
        pdf.cell(16, 5.2, f"{c:.2f}" if c is not None else "-", align="C")
        x += 16
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_xy(x + 2, y + 1.2)
        pdf.cell(39, 5.2, _aman(it.get("bahan", "-"), 26))
        pdf.set_y(y + 7.2)
    if n_diubah:
        pdf.set_font("helvetica", "I", 7.5)
        pdf.set_text_color(*ABU)
        pdf.set_xy(X0, pdf.get_y() + 0.8)
        pdf.cell(0, 4, f"Catatan: {n_diubah} temuan diubah operator "
                       f"(lihat Verifikasi operator).")
        pdf.set_y(pdf.get_y() + 5.5)
        pdf.set_text_color(*INK)
    pdf.ln(2.5)

    # --- catatan + pengesahan ---
    akhir = ("Laporan ini dibuat otomatis dan telah diverifikasi operator."
             if terverifikasi else
             "Laporan ini dibuat otomatis dan belum terverifikasi petugas.")
    isi_catatan = (
        "Prioritas penanganan ditetapkan di tingkat segmen melalui "
        "SDI-visual (menu Segmen), bukan dari tabel temuan. Dimensi berasal "
        "dari bounding box kamera mono terkalibrasi; bekas roda tidak "
        "terdeteksi sehingga SDI bersifat parsial. " + akhir)
    if meta.get("Verifikasi operator"):
        isi_catatan += " Verifikasi operator: " + \
            _aman(meta["Verifikasi operator"], 90) + "."
    _kotak_catatan(pdf, _aman(isi_catatan, 700))
    _pengesahan(pdf)
    pdf.output(path)
    if berkas_crop:
        try:
            os.remove(berkas_crop)
        except OSError:
            pass
    return path


# ============================ LAPORAN SEGMEN ============================

def buat_laporan_segmen(path, detail):
    """Laporan SDI satu segmen, desain hybrid. `detail` = dict
    web.database.detail_segmen()."""
    seg = detail or {}
    sdi = seg.get("sdi") or {}
    total_sdi = sdi.get("sdi_total", 0)
    kategori = sdi.get("kategori") or "-"
    # Tanpa temuan terukur, sdi_total=0 hanyalah artefak komponen kosong;
    # kategori None adalah penanda bahwa segmen memang belum punya data.
    ada_data = kategori != "-"
    tgl = datetime.now()
    nomor = (f"SDI-{tgl:%Y%m%d}-SEG{int(seg['id']):02d}"
             if seg.get("id") else f"SDI-{tgl:%Y%m%d}")
    pdf = _pdf_baru("LAPORAN SDI-VISUAL SEGMEN", nomor)
    pdf.add_page()

    y = pdf.get_y()
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(*INK)
    pdf.set_xy(X0, y)
    pdf.cell(0, 8, "Laporan SDI-Visual Segmen")
    pdf.set_font("helvetica", "", 8.5)
    pdf.set_text_color(*ABU2)
    pdf.set_xy(X0, y + 9)
    pdf.cell(0, 5, _aman(f"{seg.get('nama', '-')}  |  {seg.get('jalan', '-')}", 80))
    pdf.set_text_color(*INK)
    pdf.set_y(y + 15)

    # --- hero SDI + skala ambang ---
    y = pdf.get_y()
    pdf.set_draw_color(*GARIS)
    pdf.set_line_width(0.35)
    pdf.set_fill_color(*PUTIH)
    pdf.rect(X0, y, LEBAR, 33, style="DF", round_corners=True,
             corner_radius=2)
    pdf.set_font("helvetica", "B", 6.5)
    pdf.set_text_color(*ABU2)
    pdf.set_xy(X0 + 4, y + 3.5)
    pdf.cell(50, 3.8, "SDI TOTAL")
    pdf.set_font("helvetica", "B", 30)
    pdf.set_text_color(*INK)
    pdf.set_xy(X0 + 4, y + 7)
    pdf.cell(50, 13, _fmt_angka(total_sdi) if ada_data else "-")
    if ada_data:
        warna_kat = KAT_WARNA.get(kategori, ABU)
        pdf.set_draw_color(*warna_kat)
        pdf.set_fill_color(*KAT_LATAR.get(kategori, LATAR))
        pdf.rect(X0 + 4, y + 21.5, 46, 6.6, style="DF", round_corners=True,
                 corner_radius=2.5)
        pdf.set_font("helvetica", "B", 9)
        pdf.set_text_color(*warna_kat)
        pdf.set_xy(X0 + 4, y + 22.4)
        pdf.cell(46, 5, _aman(kategori, 20), align="C")
    else:
        pdf.set_draw_color(*GARIS)
        pdf.set_fill_color(*LATAR)
        pdf.rect(X0 + 4, y + 21.5, 52, 6.6, style="DF", round_corners=True,
                 corner_radius=2.5)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(*ABU)
        pdf.set_xy(X0 + 4, y + 22.6)
        pdf.cell(52, 5, "Belum ada data terukur", align="C")
    pdf.set_font("helvetica", "", 7)
    pdf.set_text_color(*ABU2)
    pdf.set_xy(X0 + 4, y + 28.6)
    pdf.cell(52, 3.4, "kategori Bina Marga, acuan paper sekunder")
    # skala
    sx, sw = X0 + 66, LEBAR - 70
    pdf.set_font("helvetica", "B", 6.5)
    pdf.set_text_color(*ABU2)
    pdf.set_xy(sx, y + 3.5)
    pdf.cell(sw, 3.8, "POSISI SDI TERHADAP AMBANG")
    if ada_data:
        try:
            v = float(total_sdi)
        except (TypeError, ValueError):
            v = 0
        mx = sx + min(max(v, 0), 200) / 200 * sw
        pdf.set_font("helvetica", "B", 8.5)
        pdf.set_text_color(*INK)
        pdf.set_xy(mx - 10, y + 8.6)
        pdf.cell(20, 4.4, _fmt_angka(total_sdi), align="C")
        pdf.set_fill_color(*INK)
        pdf.polygon([(mx - 2.6, y + 13.6), (mx + 2.6, y + 13.6),
                     (mx, y + 16.6)], style="F")
    seg_w = sw / 4
    for i, nama_kat in enumerate(("Baik", "Sedang", "Rusak Ringan",
                                  "Rusak Berat")):
        pdf.set_fill_color(*KAT_WARNA[nama_kat])
        pdf.rect(sx + i * seg_w, y + 17.4, seg_w - 0.6, 5.2, style="F")
        pdf.set_font("helvetica", "", 6.8)
        pdf.set_text_color(*ABU)
        pdf.set_xy(sx + i * seg_w, y + 23.4)
        pdf.cell(seg_w - 0.6, 3.6,
                 f"{nama_kat} {PITA_KAT[nama_kat]}", align="C")
    pdf.set_text_color(*INK)
    pdf.set_y(y + 37)

    # --- strip info ---
    y = pdf.get_y()
    pdf.set_draw_color(*GARIS)
    pdf.set_fill_color(*PUTIH)
    pdf.rect(X0, y, LEBAR, 13.5, style="DF", round_corners=True,
             corner_radius=2)
    strip = [("RUAS", _aman(seg.get("jalan", "-"), 26)),
             ("DIMENSI", f"{_fmt_angka(seg.get('panjang_m'))} m x "
                         f"{_fmt_angka(seg.get('lebar_m'))} m"),
             ("SESI", str(len(seg.get("anggota", [])))),
             ("TEMUAN", str(sdi.get("n_temuan_total", 0)))]
    w_sel = LEBAR / 4
    for i, (k, v) in enumerate(strip):
        x = X0 + i * w_sel
        if i:
            pdf.set_draw_color(*GARIS)
            pdf.line(x, y + 1.5, x, y + 12)
        pdf.set_font("helvetica", "B", 6.3)
        pdf.set_text_color(*ABU2)
        pdf.set_xy(x + 4, y + 2.2)
        pdf.cell(w_sel - 6, 3.6, k)
        pdf.set_font("helvetica", "B", 9.5)
        pdf.set_text_color(*INK)
        pdf.set_xy(x + 4, y + 6)
        pdf.cell(w_sel - 6, 5, v)
    pdf.set_y(y + 17.5)

    # --- komponen SDI (kartu 2x2) ---
    _judul_bagian(pdf, "Komponen SDI-visual")
    komp = [("SDI1 - LUAS RETAK", sdi.get("sdi1"),
             _ket_sdi1(sdi)),
            ("SDI2 - LEBAR RETAK", sdi.get("sdi2"),
             _aman(sdi.get("sdi2_ket") or "-", 60)),
            ("SDI3 - JUMLAH LUBANG", sdi.get("sdi3"),
             _ket_sdi3(sdi)),
            ("SDI4 - BEKAS RODA", sdi.get("sdi4"),
             _aman(sdi.get("sdi4_ket") or "-", 60))]
    nilai_angka = [v for _, v, _ in komp[:3] if isinstance(v, (int, float))]
    terbesar = max(nilai_angka) if nilai_angka else None
    y = pdf.get_y()
    w_kartu, h_kartu = (LEBAR - 2) / 2, 20
    for i, (label, nilai, ket) in enumerate(komp):
        x = X0 + (i % 2) * (w_kartu + 2)
        cy = y + (i // 2) * (h_kartu + 2)
        pdf.set_draw_color(*GARIS)
        pdf.set_fill_color(*PUTIH)
        pdf.rect(x, cy, w_kartu, h_kartu, style="DF", round_corners=True,
                 corner_radius=2)
        pdf.set_font("helvetica", "B", 6.5)
        pdf.set_text_color(*ABU2)
        pdf.set_xy(x + 4, cy + 2.6)
        pdf.cell(w_kartu - 8, 3.8, label)
        if terbesar is not None and nilai == terbesar and terbesar > 0:
            teks_tag = "PENYUMBANG TERBESAR"
            pdf.set_font("helvetica", "B", 6)
            w_tag = pdf.get_string_width(teks_tag) + 6
            pdf.set_fill_color(*PRIMER)
            pdf.rect(x + w_kartu - w_tag - 3.5, cy + 2.2, w_tag, 4.6,
                     style="F", round_corners=True, corner_radius=2.3)
            pdf.set_text_color(*PUTIH)
            pdf.set_xy(x + w_kartu - w_tag - 3.5, cy + 2.6)
            pdf.cell(w_tag, 3.8, teks_tag, align="C")
        pdf.set_font("helvetica", "B", 15)
        pdf.set_text_color(*INK)
        pdf.set_xy(x + 4, cy + 6.8)
        pdf.cell(40, 8, "-" if nilai is None else _fmt_angka(nilai))
        pdf.set_font("helvetica", "", 7.8)
        pdf.set_text_color(*ABU)
        pdf.set_xy(x + 4, cy + 15)
        pdf.cell(w_kartu - 8, 4, ket)
    pdf.set_text_color(*INK)
    pdf.set_y(y + 2 * h_kartu + 6.5)

    # --- validasi lapangan ---
    manual = seg.get("sdi_manual")
    if manual is not None:
        _judul_bagian(pdf, "Validasi lapangan")
        try:
            selisih = abs(float(manual) - float(total_sdi))
            y = pdf.get_y()
            w_kotak = (LEBAR - 4) / 3
            kotak = [(_fmt_angka(total_sdi), "SDI-VISUAL (APLIKASI)", INK),
                     (_fmt_angka(manual), "SDI MANUAL (SURVEI)", INK),
                     (_fmt_angka(selisih),
                      "SELISIH - SESUAI" if selisih == 0 else "SELISIH",
                      (30, 158, 74) if selisih == 0 else (179, 38, 30))]
            for i, (v, k, warna) in enumerate(kotak):
                x = X0 + i * (w_kotak + 2)
                pdf.set_draw_color(*GARIS)
                pdf.set_fill_color(*PUTIH)
                pdf.rect(x, y, w_kotak, 15.5, style="DF",
                         round_corners=True, corner_radius=2)
                pdf.set_font("helvetica", "B", 13.5)
                pdf.set_text_color(*warna)
                pdf.set_xy(x, y + 2)
                pdf.cell(w_kotak, 7, v, align="C")
                pdf.set_font("helvetica", "B", 6.3)
                pdf.set_text_color(*ABU2)
                pdf.set_xy(x, y + 10)
                pdf.cell(w_kotak, 3.8, k, align="C")
            pdf.set_text_color(*INK)
            pdf.set_y(y + 19.5)
        except (TypeError, ValueError):
            pass

    # --- sesi anggota ---
    _judul_bagian(pdf, "Sesi anggota segmen")
    kolom = [("NO", 10, "C"), ("WAKTU", 36, "L"), ("LOKASI", 70, "L"),
             ("SUMBER", 32, "L"), ("TEMUAN", 16, "C"), ("TERBERAT", 26, "L")]
    _kepala_tabel(pdf, kolom)
    anggota = seg.get("anggota", [])
    if not anggota:
        pdf.set_font("helvetica", "I", 9)
        pdf.set_text_color(*ABU)
        pdf.set_xy(X0, pdf.get_y() + 1)
        pdf.cell(LEBAR, 6, "Belum ada sesi anggota.", align="C")
        pdf.set_y(pdf.get_y() + 8)
        pdf.set_text_color(*INK)
    for i, s in enumerate(anggota):
        if pdf.get_y() + 7.2 > BATAS_BAWAH:
            pdf.add_page()
            _kepala_tabel(pdf, kolom)
        y = pdf.get_y()
        if i % 2 == 1:
            pdf.set_fill_color(*LATAR)
            pdf.rect(X0, y, LEBAR, 7.2, style="F")
        label_sev, pal = _sev_dari(s.get("worst"))
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_text_color(*ABU2)
        pdf.set_xy(X0, y + 1.2)
        pdf.cell(10, 5.2, str(i + 1), align="C")
        pdf.set_font("courier", "", 8.2)
        pdf.set_text_color(*INK)
        pdf.set_xy(X0 + 12, y + 1.4)
        pdf.cell(34, 5.2, _fmt_waktu(s.get("waktu")))
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_xy(X0 + 48, y + 1.2)
        pdf.cell(68, 5.2, _aman(s.get("lokasi", "-"), 42))
        pdf.set_xy(X0 + 118, y + 1.2)
        pdf.cell(30, 5.2, _aman(s.get("sumber", "-"), 20))
        pdf.set_xy(X0 + 150, y + 1.2)
        pdf.cell(16, 5.2, str(s.get("n_temuan", 0)), align="C")
        _chip(pdf, X0 + 168, y + 1.1, label_sev, pal["bg"], pal["tx"], 7.8)
        pdf.set_y(y + 7.2)
    pdf.ln(2.5)

    # --- catatan ---
    penyumbang = "-"
    if terbesar is not None and terbesar > 0:
        for label, nilai, _ in komp:
            if nilai == terbesar:
                penyumbang = label.split(" - ")[0] + " " + \
                    label.split(" - ")[1].lower()
                break
    if ada_data:
        isi = (f"SDI total {_fmt_angka(total_sdi)} termasuk kategori "
               f"{kategori} ({PITA_KAT.get(kategori, '-')}). Komponen "
               f"penyumbang terbesar: {penyumbang}. ")
    else:
        isi = ("Belum ada temuan dengan dimensi terukur pada segmen ini, "
               "sehingga SDI belum dapat dihitung. ")
    if sdi.get("n_tanpa_dimensi"):
        isi += (f"{sdi['n_tanpa_dimensi']} temuan tanpa data dimensi tidak "
                f"masuk perhitungan. ")
    isi += ("Acuan Bina Marga 2011b via paper sekunder - dokumen primer "
            "SMD-03/RCS tidak publik. Bekas roda tidak terdeteksi sehingga "
            "SDI bersifat parsial.")
    _kotak_catatan(pdf, _aman(isi, 600))
    pdf.output(path)
    return path


def _ket_sdi1(sdi):
    ket = str(sdi.get("sdi1_ket") or "-")
    if ket and (ket[0].isdigit() or ket[0] in "<>"):
        return _aman(f"luas retak {ket} luas segmen", 60)
    return _aman(ket, 60)


def _ket_sdi3(sdi):
    ket = _aman(sdi.get("sdi3_ket") or "-", 40)
    lpk = sdi.get("lubang_per_km")
    if lpk is not None:
        return _aman(f"{_fmt_angka(lpk)} lubang/km ({ket})", 60)
    return ket
