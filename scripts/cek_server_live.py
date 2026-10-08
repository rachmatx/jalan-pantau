"""Cek cepat endpoint lewat HTTP sungguhan (bukan test client).

Dipakai untuk memastikan server yang sedang berjalan benar-benar memuat
route terbaru, bukan hanya berkas di disk.
"""
import http.cookiejar
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:5000"
PASS = os.environ.get("JP_DEMO_PASS", "jalanpantau2026")


def buat_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)), cj


def ambil_token(op):
    """Token CSRF dari halaman login.

    Halaman login berdiri sendiri (tidak extends base.html), jadi token ada
    di hidden input `_csrf`, bukan di meta tag seperti halaman lain.
    """
    html = op.open(BASE + "/login").read().decode("utf-8", "ignore")
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return m.group(1) if m else None


def login(op, user, pw):
    token = ambil_token(op)
    if not token:
        return None, "token CSRF tidak ditemukan di halaman login"
    data = urllib.parse.urlencode(
        {"username": user, "password": pw, "_csrf": token}).encode()
    try:
        r = op.open(urllib.request.Request(BASE + "/login", data=data))
        return r.geturl(), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:200])


def cek(op, path):
    try:
        r = op.open(BASE + path)
        return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, 0


def main():
    gagal = 0
    op, cj = buat_opener()
    url, galat = login(op, "admin", PASS)
    print("login dinas  ->", url or ("GAGAL " + str(galat)))
    if not url:
        return 1
    print("cookie sesi :", [c.name for c in cj])

    target = ["/pupr-bandung/dashboard",
              "/pupr-bandung/dashboard/spk",
              "/pupr-bandung/dashboard/kontraktor",
              "/pupr-bandung/dashboard/verifikasi"]
    print()
    for p in target:
        kode, n = cek(op, p)
        tanda = "OK " if kode == 200 else "GAGAL"
        if kode != 200:
            gagal += 1
        print(f"  {tanda} {kode}  {p}  ({n} byte)")

    print()
    op2, _ = buat_opener()
    url2, galat2 = login(op2, "kt_mitrakarya", PASS)
    print("login kontraktor ->", url2 or ("GAGAL " + str(galat2)))
    if url2:
        for p in ["/kontraktor/dashboard"]:
            kode, n = cek(op2, p)
            tanda = "OK " if kode == 200 else "GAGAL"
            if kode != 200:
                gagal += 1
            print(f"  {tanda} {kode}  {p}  ({n} byte)")

    print()
    print("kesimpulan:", "SEMUA OK" if gagal == 0 else f"{gagal} endpoint gagal")
    return 1 if gagal else 0


if __name__ == "__main__":
    sys.exit(main())