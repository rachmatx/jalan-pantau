"""Cetak semua id= di template (untuk kontrak ID di DESIGN.md)."""
import re
from pathlib import Path

ids = {}
for f in sorted(Path("web/templates").glob("*.html")):
    for m in re.findall(r'id="([^"]+)"', f.read_text(encoding="utf-8")):
        ids.setdefault(m, f.name)
print(f"TOTAL: {len(ids)}")
for i, f in sorted(ids.items()):
    print(f"- `{i}` ({f})")
