"""Uji sinkronisasi SPK ke disposisi.

Setelah dinas menerima hasil kerja, disposisi yang titik pekerjaannya
sudah diterima ikut ditutup. Tanpa itu, tiket tetap tampil "sedang
ditangani" padahal pekerjaannya sudah selesai dan terverifikasi.

Fokus pengujian: kedua arah sinkronisasi, syaratnya, dan idempotensi.
"""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())

PASS = os.environ.get("JP_DEMO_PASS", "jalanpantau2026")


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        from database import (init_admin, migrasi_admin_v2, migrasi_disposisi_v2,
                              migrasi_sesi_v2, migrasi_urgensi_v1,
                              migrasi_spk_penerimaan_v3,
                              init_kontraktor, simpan_disposisi, rekap_temuan,
                              simpan_sesi)
        migrasi_admin_v2()
        migrasi_disposisi_v2()
        migrasi_sesi_v2()
        migrasi_urgensi_v1()
        migrasi_spk_penerimaan_v3()
        init_admin()
        init_kontraktor()
        rows = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
                 "total_rp": 1500000, "total_str": "Rp1.500.000"}]
        sid = simpan_sesi("uji", "Jl. Uji km 1", "m", rows, 0, lat=-6.9, lon=107.6)
        r = rekap_temuan(sid)
        app.extensions["d1"] = simpan_disposisi(
            sid, "BAP-001", "Jl. Uji km 1", -6.9, 107.6, r["n_temuan"],
            r["total_rp"], r["worst"], None, "Dinas Uji", "Bandung",
            "uji@example.go.id", "Kritis")
        app.extensions["d2"] = simpan_disposisi(
            sid, "BAP-002", "Jl. Uji km 2", -6.91, 107.61, r["n_temuan"],
            r["total_rp"], r["worst"], None, "Dinas Uji", "Bandung",
            "uji@example.go.id", "Tinggi")
    return app


def _jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 30, 30)).save(buf, format="JPEG")
    buf.seek(0)
    return buf


class _Dasar(unittest.TestCase):
    """Satu SPK milik kontraktor dengan dua titik pekerjaan."""

    def setUp(self):
        self.app = _app()
        self.d1 = self.app.extensions["d1"]
        self.d2 = self.app.extensions["d2"]
        self.dinas = self.app.test_client()
        r = self.dinas.post("/login", data={"username": "admin", "password": PASS})
        self.assertEqual(r.status_code, 302)
        self.spk = self._terbitkan([self.d1, self.d2])
        self.kontraktor = self._kontraktor()

    def _terbitkan(self, disposisi_ids, judul="Perbaikan"):
        # Di alur nyata disposisi sudah "Diproses" (dinas memverifikasi
        # laporan) sebelum SPK diterbitkan. Disetel di sini supaya tes
        # mencerminkan keadaan sebenarnya, bukan default saat pembuatan.
        with self.app.app_context():
            from database import get_db
            db = get_db()
            for did in disposisi_ids:
                db.execute("UPDATE disposisi SET status = 'Diproses' WHERE id = ?", (did,))
            db.commit()
        r = self.dinas.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": judul,
            "disposisi_ids": disposisi_ids})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def _kontraktor(self, username="kt_mitrakarya"):
        c = self.app.test_client()
        r = c.post("/login", data={"username": username, "password": PASS})
        self.assertEqual(r.status_code, 302, f"login {username} gagal")
        return c

    def _tugas_pertama(self, sid):
        """ID titik pertama milik SPK tertentu.

        ID spk_tugas itu global, jadi tidak boleh diasumsikan mulai dari 1
        untuk setiap SPK.
        """
        with self.app.app_context():
            from database import daftar_tugas_spk
            return daftar_tugas_spk(sid)[0]["id"]

    def _kerja_sampai_diajukan(self, n_tugas=2):
        """Kontraktor menyelesaikan semua titik lalu mengajukan hasil."""
        for s in ("Diterima", "Dikerjakan"):
            r = self.kontraktor.post(f"/api/kontraktor/spk/{self.spk}/status",
                                     json={"status": s})
            self.assertEqual(r.status_code, 200, s)
        for tid in range(1, n_tugas + 1):
            self.kontraktor.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}/foto",
                                 data={"foto": (_jpeg(), "b.jpg")},
                                 content_type="multipart/form-data")
            self.kontraktor.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}",
                                 json={"status": "Dikerjakan"})
            self.kontraktor.post(f"/api/kontraktor/spk/{self.spk}/tugas/{tid}",
                                 json={"status": "Selesai"})
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["status"], "Menunggu Penerimaan")

    def _terima(self, bast="BAST/1"):
        return self.dinas.post(f"/api/spk/{self.spk}/terima", json={"nomor_bast": bast})

    def _disposisi(self, did=None):
        with self.app.app_context():
            from database import detail_disposisi
            return detail_disposisi(did if did is not None else self.d1)


class TestNaikKeSelesai(_Dasar):
    def test_terima_menutup_disposisi(self):
        self._kerja_sampai_diajukan()
        self.assertEqual(self._terima().status_code, 200)
        d = self._disposisi()
        self.assertEqual(d["status"], "Selesai")
        self.assertIsNotNone(d["waktu_selesai"])

    def test_catatan_audit_memuat_asal(self):
        """Catatan harus menyebut SPK dan BAST, bukan sekadar "Selesai"."""
        self._kerja_sampai_diajukan()
        self._terima("BAST/77/2026")
        with self.app.app_context():
            from database import riwayat_catatan
            isi = " ".join(c["catatan"] for c in riwayat_catatan(self.d1))
        self.assertIn("SPK/", isi)
        self.assertIn("BAST/77/2026", isi)

    def test_penanggung_jawab_terisi(self):
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertEqual(self._disposisi()["penanggung_jawab"], "admin")

    def test_penanggung_jawab_lama_tidak_ditimpa(self):
        """PJ yang sudah diisi manual tidak boleh hilang oleh sinkronisasi."""
        with self.app.app_context():
            from database import get_db
            db = get_db()
            db.execute("UPDATE disposisi SET penanggung_jawab = 'Pak Budi'"
                       " WHERE id = ?", (self.d1,))
            db.commit()
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertEqual(self._disposisi()["penanggung_jawab"], "Pak Budi")

    def test_semua_disposisi_tertutup(self):
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertEqual(self._disposisi(self.d1)["status"], "Selesai")
        self.assertEqual(self._disposisi(self.d2)["status"], "Selesai")

    def test_transaksi_utuh_saat_sinkronisasi_gagal(self):
        """Kalau sinkronisasi disposisi gagal, perubahan status SPK ikut batal.

        Kalau SPK lebih dulu tersimpan lalu sinkronisasi gagal, SPK akan
        tercatat sudah diterima sementara tiket masih menggantung. Dua
        sumber kebenaran jadi berbeda dan selisihnya tidak terlihat.
        """
        from unittest.mock import patch
        import database

        self._kerja_sampai_diajukan()
        with patch.object(database, "_sinkron_semua_disposisi_spk",
                          side_effect=RuntimeError("koneksi terputus")):
            try:
                self.dinas.post(f"/api/spk/{self.spk}/terima",
                                json={"nomor_bast": "BAST/1"})
            except RuntimeError:
                # Mode test meneruskan exception; di server menjadi 500.
                pass

        with self.app.app_context():
            from database import detail_spk
            spk = detail_spk(self.spk)
        self.assertNotEqual(spk["status"], "Diterima Dinas")
        self.assertNotEqual(self._disposisi()["status"], "Selesai")

    def test_idempoten(self):
        """Menjalankan sinkronisasi dua kali tidak mengubah apa pun lagi."""
        self._kerja_sampai_diajukan()
        self._terima()
        with self.app.app_context():
            from database import (_sinkron_semua_disposisi_spk, get_db)
            db = get_db()
            n = _sinkron_semua_disposisi_spk(db, self.spk, "ulangi", "admin",
                                             "2026-01-01T00:00:00")
        self.assertEqual(n, 0)
        self.assertEqual(self._disposisi()["status"], "Selesai")


class TestTidakNaikKalauBelumSemua(_Dasar):
    def test_disposisi_tanpa_spk_tidak_tersentuh(self):
        """Tiket yang tidak punya SPK tidak boleh ikut berubah."""
        with self.app.app_context():
            from database import simpan_disposisi
            sendir = simpan_disposisi(
                1, "BAP-999", "Jl. Lain", -6.9, 107.6, 1, 1000, "Ringan",
                None, "Dinas Uji", "Bandung", "u@example.go.id", "Rutin")
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertEqual(self._disposisi(sendir)["status"], "Terkirim")

    def test_spk_lain_yang_masih_jalan_menahan(self):
        """Satu disposisi di dua SPK: belum boleh ditutup sebelum keduanya selesai."""
        spk2 = self._terbitkan([self.d1], judul="Pekerjaan kedua")
        self._kerja_sampai_diajukan()
        self._terima()
        # SPK pertama selesai, tapi SPK kedua masih Diterbitan, jadi tiket
        # TIDAK boleh naik ke Selesai.
        self.assertNotEqual(self._disposisi()["status"], "Selesai")
        self.assertEqual(self._disposisi()["status"], "Diproses")

        # Setelah SPK kedua juga selesai, barulah tiket boleh ditutup.
        c2 = self._kontraktor()
        for s in ("Diterima", "Dikerjakan"):
            c2.post(f"/api/kontraktor/spk/{spk2}/status", json={"status": s})
        tid = self._tugas_pertama(spk2)
        c2.post(f"/api/kontraktor/spk/{spk2}/tugas/{tid}/foto",
                data={"foto": (_jpeg(), "b.jpg")}, content_type="multipart/form-data")
        c2.post(f"/api/kontraktor/spk/{spk2}/tugas/{tid}", json={"status": "Dikerjakan"})
        c2.post(f"/api/kontraktor/spk/{spk2}/tugas/{tid}", json={"status": "Selesai"})
        self.dinas.post(f"/api/spk/{spk2}/terima", json={"nomor_bast": "BAST/2"})
        self.assertEqual(self._disposisi()["status"], "Selesai")


class TestTurunKeDiproses(_Dasar):
    def test_revisi_tidak_menutup_tiket(self):
        """Sedang ditolak berarti pekerjaan belum selesai, jadi jangan naik."""
        self._kerja_sampai_diajukan()
        self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "Aspal kurang"})
        self.assertEqual(self._disposisi()["status"], "Diproses")

    def test_pembatalan_mengembalikan_tiket(self):
        """Tiket yang sudah ditutup harus dibuka lagi kalau SPK-nya dibatalkan.

        SPK yang sudah diterima tidak bisa langsung dibatalkan: arahnya
        harus withdrawal of acceptance dulu supaya keputusan yang sudah
        tercatat tetap punya alasan.
        """
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertEqual(self._disposisi()["status"], "Selesai")

        # Batalkan langsung ditolak.
        self.assertEqual(self.dinas.post(f"/api/spk/{self.spk}/batal").status_code, 400)
        self.assertEqual(self._disposisi()["status"], "Selesai")

        # Tarik penerimaan, lalu batalkan.
        self.dinas.post(f"/api/spk/{self.spk}/batalkan-terima",
                        json={"alasan": "pekerjaan memang tidak dikerjakan"})
        self.assertEqual(self._disposisi()["status"], "Diproses")
        self.dinas.post(f"/api/spk/{self.spk}/batal")
        self.assertEqual(self._disposisi()["status"], "Diproses")

    def test_pembatalan_membuka_pintu_yang_tadinya_tertahan(self):
        """Membatalkan SPK yang menghalangi harus membuka jalan ke penutupan.

        Satu disposisi ada di dua SPK. SPK pertama selesai, tapi SPK kedua
        masih jalan sehingga tiket tertahan. Setelah SPK kedua dibatalkan,
        tidak ada lagi yang menghalangi, jadi tiket boleh ditutup.
        """
        spk2 = self._terbitkan([self.d1], judul="Pekerjaan kedua")
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertNotEqual(self._disposisi()["status"], "Selesai")

        self.dinas.post(f"/api/spk/{spk2}/batal")
        self.assertEqual(self._disposisi()["status"], "Selesai")

    def test_revisi_mencatat_alasan(self):
        """Alasan revisi harus tersimpan di jejak audit SPK."""
        self._kerja_sampai_diajukan()
        self.dinas.post(f"/api/spk/{self.spk}/revisi", json={"alasan": "Aspal kurang padat"})
        with self.app.app_context():
            from database import riwayat_spk
            isi = " ".join((c["catatan"] or "") for c in riwayat_spk(self.spk))
        self.assertIn("Aspal kurang padat", isi)


class TestTarikPenerimaan(_Dasar):
    """Keputusan penerimaan harus bisa ditarik kalau ternyata keliru."""

    def test_menunggu_diterima_menutup_tiket(self):
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertEqual(self._disposisi()["status"], "Selesai")

    def test_tarik_penerimaan_membuka_kembali(self):
        self._kerja_sampai_diajukan()
        self._terima("BAST/9")
        r = self.dinas.post(f"/api/spk/{self.spk}/batalkan-terima",
                            json={"alasan": "Ternyata retak di titik 2"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._disposisi()["status"], "Diproses")
        with self.app.app_context():
            from database import detail_spk
            item = detail_spk(self.spk)
        self.assertEqual(item["status"], "Menunggu Penerimaan")
        self.assertIsNone(item["waktu_diterima"])
        self.assertEqual(item["nomor_bast"], "-")

    def test_tarik_wajib_alasan(self):
        self._kerja_sampai_diajukan()
        self._terima()
        r = self.dinas.post(f"/api/spk/{self.spk}/batalkan-terima", json={"alasan": " "})
        self.assertEqual(r.status_code, 400)

    def test_kontraktor_tidak_bisa_menarik(self):
        self._kerja_sampai_diajukan()
        self._terima()
        r = self.kontraktor.post(f"/api/spk/{self.spk}/batalkan-terima",
                                 json={"alasan": "saya berubah pikiran"})
        self.assertEqual(r.status_code, 401)

    def test_masih_bisa_diterima_ulang(self):
        """Setelah ditarik, dinas dapat menerima ulang dengan BAST baru."""
        self._kerja_sampai_diajukan()
        self._terima("BAST/1")
        self.dinas.post(f"/api/spk/{self.spk}/batalkan-terima", json={"alasan": "salah"})
        r = self._terima("BAST/2")
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            from database import detail_spk
            self.assertEqual(detail_spk(self.spk)["nomor_bast"], "BAST/2")
        self.assertEqual(self._disposisi()["status"], "Selesai")


class TestFotoBukti(_Dasar):
    """Foto yang bisa dilihat publik hanya yang sudah diverifikasi."""

    def test_tidak_ada_foto_sebelum_diterima(self):
        self._kerja_sampai_diajukan()
        with self.app.app_context():
            from database import foto_bukti_disposisi
            self.assertIsNone(foto_bukti_disposisi(self.d1))

    def test_foto_tersedia_setelah_diterima(self):
        self._kerja_sampai_diajukan()
        self._terima()
        with self.app.app_context():
            from database import foto_bukti_disposisi
            self.assertTrue(foto_bukti_disposisi(self.d1))

    def test_foto_hilang_setelah_penerimaan_ditarik(self):
        self._kerja_sampai_diajukan()
        self._terima()
        self.dinas.post(f"/api/spk/{self.spk}/batalkan-terima", json={"alasan": "salah"})
        with self.app.app_context():
            from database import foto_bukti_disposisi
            self.assertIsNone(foto_bukti_disposisi(self.d1))

    def test_rute_publik_menolak_belum_diterima(self):
        """Pengunjung anonim tidak boleh melihat bukti yang belum diverifikasi."""
        self._kerja_sampai_diajukan()
        anonim = self.app.test_client()
        r = anonim.get(f"/api/disposisi/{self.d1}/foto-bukti")
        self.assertEqual(r.status_code, 404)

    def test_rute_publik_melayani_tanpa_login(self):
        self._kerja_sampai_diajukan()
        self._terima()
        anonim = self.app.test_client()
        r = anonim.get(f"/api/disposisi/{self.d1}/foto-bukti")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/jpeg")


class TestDaftarSpkDisposisi(_Dasar):
    def test_menampilkan_spk_terkait(self):
        hasil = self._daftar()
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["nomor"].startswith("SPK/"), True)

    def test_kosong_bila_tanpa_spk(self):
        with self.app.app_context():
            from database import simpan_disposisi
            sendir = simpan_disposisi(
                1, "BAP-888", "Jl. Kosong", -6.9, 107.6, 1, 1000, "Ringan",
                None, "Dinas Uji", "Bandung", "u@example.go.id", "Rutin")
        with self.app.app_context():
            from database import daftar_spk_disposisi
            self.assertEqual(daftar_spk_disposisi(sendir), [])

    def _daftar(self):
        with self.app.app_context():
            from database import daftar_spk_disposisi
            return daftar_spk_disposisi(self.d1)


class TestStatusDitolakTidakTersentuh(_Dasar):
    def test_ditolak_tidak_naik_dan_tidak_turun(self):
        """"Ditolak" berarti laporan ditolak, bukan pekerjaan berjalan."""
        with self.app.app_context():
            from database import get_db
            db = get_db()
            db.execute("UPDATE disposisi SET status = 'Ditolak' WHERE id = ?", (self.d1,))
            db.commit()
        self._kerja_sampai_diajukan()
        self._terima()
        self.assertEqual(self._disposisi()["status"], "Ditolak")


if __name__ == "__main__":
    unittest.main()