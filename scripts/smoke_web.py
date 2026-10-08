"""Smoke test fungsional: detect -> laporan (PDF) -> riwayat simpan -> peta -> hapus.

CSRF-aware. Login admin demo sebelum DELETE (hapus riwayat butuh login), dan
membersihkan sesi uji walau ada langkah yang gagal.
"""
import http.cookiejar
import json
import os
import re
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:5000"

_cj = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))

def _ambil_token():
    """GET halaman utama -> simpan cookie sesi + baca token CSRF dari meta."""
    with _opener.open(BASE + "/") as resp:
        html = resp.read().decode("utf-8", "ignore")
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


TOKEN = _ambil_token()


def _headers(extra=None):
    h = {"X-CSRF-Token": TOKEN}
    if extra:
        h.update(extra)
    return h


def post_json(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers=_headers({"Content-Type": "application/json"}), method="POST")
    return _opener.open(req)


def login_admin():
    body = urllib.parse.urlencode({
        "username": "admin",
        "password": os.environ.get("JP_DEMO_PASS", "jalanpantau2026"),
    }).encode()
    req = urllib.request.Request(
        BASE + "/login", data=body, method="POST",
        headers=_headers({"Content-Type": "application/x-www-form-urlencoded"}))
    _opener.open(req)
    # login_post memanggil session.clear() -> token CSRF lama hangus; ambil ulang.
    global TOKEN
    TOKEN = _ambil_token()


def hapus_sesi(sid):
    req = urllib.request.Request(f"{BASE}/api/riwayat/{sid}", method="DELETE",
                                 headers=_headers())
    return json.loads(_opener.open(req).read())


sid = None
try:
    # 1. POST /api/detect pake multipart manual
    boundary = "----smokeboundary123"
    img_path = "data/publik/bpid/test/images/0125c08e.jpeg"  # positif: 2 pothole
    with open(img_path, "rb") as f:
        img = f.read()
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="conf"\r\n\r\n0.25\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="gambar"; filename="1.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode() + img + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + "/api/detect", data=body, method="POST",
        headers=_headers({"Content-Type": f"multipart/form-data; boundary={boundary}"}))
    with _opener.open(req) as resp:
        data = json.loads(resp.read())
    print("detect: rows =", len(data["rows"]), "| total =", data["total"], "| model =", data.get("model"))
    assert "rows" in data and "total" in data and "image_b64" in data, "shape detect berubah"

    # 2. laporan -> PDF
    with post_json("/api/laporan", {
        "rows": data["rows"], "total": data["total"], "image_b64": data["image_b64"],
        "source": "smoke.jpg", "model": data.get("model")}) as resp:
        pdf = resp.read()
        print("laporan:", resp.status, resp.headers["Content-Type"], "magic:", pdf[:5])
        assert resp.headers["Content-Type"] == "application/pdf"
        assert pdf[:5] == b"%PDF-"

    # 3. simpan riwayat
    with post_json("/api/riwayat", {
        "sumber": "Gambar (smoke.jpg)", "lokasi": "Smoke Test Jl.",
        "lat": -6.9, "lon": 107.6, "model": data.get("model"),
        "rows": data["rows"], "total": data["total"], "image_b64": data["image_b64"],
        "izinkan_duplikat": True}) as resp:
        sid = json.loads(resp.read())["id"]
    print("riwayat simpan: id", sid)

    # 4. peta ada titik
    with _opener.open(BASE + "/api/peta") as resp:
        print("peta titik:", len(json.loads(resp.read())))

    # 5. login admin lalu hapus (hapus riwayat = butuh login)
    login_admin()
    print("hapus:", hapus_sesi(sid))
    sid = None
    print("SMOKE-PASS")
finally:
    if sid is not None:
        try:
            login_admin()
            hapus_sesi(sid)
            print("cleanup: hapus id", sid)
        except Exception as e:  # pragma: no cover
            print("cleanup gagal:", e)
