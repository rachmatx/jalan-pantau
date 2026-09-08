"""Cek cepat /api/detect pada satu gambar. Pakai: python3 scripts/cek_detect.py <path_gambar> [conf]"""
import json
import sys
import urllib.request

img_path = sys.argv[1]
conf = sys.argv[2] if len(sys.argv) > 2 else "0.25"
B = "----cek123"
img = open(img_path, "rb").read()
body = (
    b"--" + B.encode() + b'\r\nContent-Disposition: form-data; name="gambar"; filename="t.jpg"'
    b'\r\nContent-Type: image/jpeg\r\n\r\n' + img +
    b"\r\n--" + B.encode() + b'\r\nContent-Disposition: form-data; name="conf"'
    b"\r\n\r\n" + conf.encode() + b"\r\n--" + B.encode() + b"--\r\n"
)
req = urllib.request.Request(
    "http://127.0.0.1:5000/api/detect", data=body,
    headers={"Content-Type": "multipart/form-data; boundary=" + B})
j = json.load(urllib.request.urlopen(req))
print("rows =", len(j["rows"]), "| total =", j.get("total_str"), "| model =", j.get("model"))
for r in j["rows"]:
    print(" -", r["kelas"], r["severity"], r["total_str"])
