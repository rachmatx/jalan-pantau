"""Smoke test fungsional: detect -> laporan (PDF) -> riwayat simpan -> peta -> hapus."""
import json
import urllib.request

BASE = "http://127.0.0.1:5000"


def post_json(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req)


# 1. POST /api/detect pake multipart manual
boundary = "----smokeboundary123"
img_path = "data/publik/bpid/test/images/0125c08e.jpeg"  # positif: 2 pothole (fixture lama 1.jpg nol deteksi)
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
    BASE + "/api/detect", data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
with urllib.request.urlopen(req) as resp:
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
    "rows": data["rows"], "total": data["total"], "image_b64": data["image_b64"]}) as resp:
    sid = json.loads(resp.read())["id"]
print("riwayat simpan: id", sid)

# 4. peta ada titik
with urllib.request.urlopen(BASE + "/api/peta") as resp:
    print("peta titik:", len(json.loads(resp.read())))

# 5. cleanup
req = urllib.request.Request(f"{BASE}/api/riwayat/{sid}", method="DELETE")
with urllib.request.urlopen(req) as resp:
    print("hapus:", json.loads(resp.read()))
print("SMOKE-PASS")
