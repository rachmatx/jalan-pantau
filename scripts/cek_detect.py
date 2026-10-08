"""Cek cepat /api/detect pada satu gambar.

Pakai: python scripts/cek_detect.py <path_gambar> [conf]
CSRF-aware: token diambil dari halaman utama lalu dikirim via header.
"""
import http.cookiejar
import json
import re
import sys
import urllib.request

BASE = "http://127.0.0.1:5000"

img_path = sys.argv[1]
conf = sys.argv[2] if len(sys.argv) > 2 else "0.25"

_cj = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
with _opener.open(BASE + "/") as resp:
    _html = resp.read().decode("utf-8", "ignore")
_m = re.search(r'name="csrf-token" content="([^"]+)"', _html)
TOKEN = _m.group(1) if _m else ""

B = "----cek123"
with open(img_path, "rb") as fh:
    img = fh.read()
body = (
    b"--" + B.encode() + b'\r\nContent-Disposition: form-data; name="gambar"; filename="t.jpg"'
    b'\r\nContent-Type: image/jpeg\r\n\r\n' + img +
    b"\r\n--" + B.encode() + b'\r\nContent-Disposition: form-data; name="conf"'
    b"\r\n\r\n" + conf.encode() + b"\r\n--" + B.encode() + b"--\r\n"
)
req = urllib.request.Request(
    BASE + "/api/detect", data=body, method="POST",
    headers={"Content-Type": "multipart/form-data; boundary=" + B,
             "X-CSRF-Token": TOKEN})
j = json.load(_opener.open(req))
print("rows =", len(j["rows"]), "| total =", j.get("total_str"), "| model =", j.get("model"))
for r in j["rows"]:
    print(" -", r["kelas"], r["severity"], r["total_str"])
