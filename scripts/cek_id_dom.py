"""Tes silang ID: setiap getElementById di JS harus ada id= di template.

Latar: bug Simpan (bacaKoordinat mencari ID yang tak ada) lolos karena suite
hanya menembak API. Tes ini menangkap kematian-diam serupa sejak dini.

Pakai: python3 scripts/cek_id_dom.py  (exit 1 bila ada ID hilang)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "web" / "templates"
JS = ROOT / "web" / "static" / "js"

dom_ids = set()
for f in list(TPL.rglob("*.html")):
    dom_ids.update(re.findall(r'id="([^"]+)"', f.read_text(encoding="utf-8")))

# ID yang dibuat dinamis oleh JS sendiri (innerHTML) — bukan dari template
DINAMIS = {
    "pag-prev", "pag-next",  # riwayat.js renderPaginasi() via innerHTML
    "gps-notif",  # peta.js buatMarkerGPS()/notif dibuat via createElement
}
# ID opsional: JS meng-guard dengan if(getElementById(...)) sehingga boleh
# tidak ada di sebagian halaman (mis. sidebar-toggle hanya di dashboard).
OPSIONAL = {
    "sidebar-toggle", "sidebar",
    "peta-navigate-terdekat",  # di dalam kartu terdekat, dicek if(btnNavTerdekat)
    "d-total",  # guarded if(dTotal) di riwayat.js (kini ada, tapi tetap toleran)
}

gagal = 0
for f in sorted(JS.glob("*.js")):
    src = f.read_text(encoding="utf-8")
    for ref in re.findall(r'getElementById\(["\']([^"\']+)["\']\)', src):
        if ref not in dom_ids and ref not in DINAMIS and ref not in OPSIONAL:
            print(f"HILANG: {f.name} memakai #{ref} tapi tidak ada di template")
            gagal += 1
print(f"ID DOM: {len(dom_ids)} | rujukan JS: OK" if not gagal else f"GAGAL: {gagal} ID hilang")
sys.exit(1 if gagal else 0)
