"""SINKRONKAN DISPOSISI YANG SUDAH KEDALAMAN DITERIMA SPK.

SPK yang sudah "Diterima Dinas" belum tentu menutup disposisi-nya, sehingga
tiket tetap berstatus "Diproses" padahal pekerjaannya sudah selesai dan
sudah diverifikasi. Skrip ini menutup selisih itu.

Idempoten: aman dijalankan berulang kali. Hanya baris yang benar-benar
berbeda yang diubah, dan setiap perubahan tercatat di disposisi_catatan
supaya jejaknya tetap bisa ditelusuri.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web.app as app_mod

KERING = "--kering" in sys.argv


def main():
    app = app_mod.create_app()
    with app.app_context():
        from datetime import datetime
        from database import (_sinkron_semua_disposisi_spk, detail_disposisi,
                              get_db, SPK_STATUS_SELESAI)
        db = get_db()

        spk_diterima = db.execute(
            "SELECT id, nomor, nomor_bast FROM spk WHERE status = ?"
            " ORDER BY id", (SPK_STATUS_SELESAI,)).fetchall()
        if not spk_diterima:
            print("Tidak ada SPK berstatus Diterima Dinas. Tidak ada yang perlu disinkronkan.")
            return 0

        print(f"SPK diterima dinas: {len(spk_diterima)}")
        diubah = 0
        now = datetime.now().isoformat(timespec="seconds")
        for s in spk_diterima:
            disposisi = db.execute(
                "SELECT d.id, d.bap_nomor, d.status FROM spk_tugas t"
                " JOIN disposisi d ON d.id = t.disposisi_id WHERE t.spk_id = ?",
                (s["id"],)).fetchall()
            for d in disposisi:
                n = _sinkron_semua_disposisi_spk(
                    db, s["id"],
                    f"Diselesaikan dari penerimaan SPK {s['nomor']} "
                    f"(BAST {s['nomor_bast']}). Penutupan ulang oleh skrip backfill.",
                    "backfill", now)
                if n:
                    diubah += n
                    print(f"  {d['bap_nomor']}: {d['status']} menjadi Selesai")

        total = diubah
        print()
        if KERING:
            db.rollback()
            print(f"Mode kering: {total} disposisi akan diubah, tidak disimpan.")
        else:
            db.commit()
            print(f"Selesai. {total} disposisi ditutup dari penerimaan SPK.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())