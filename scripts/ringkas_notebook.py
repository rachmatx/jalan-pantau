"""Ringkas notebook Jupyter: daftar sel + metrik dari output teks.

Pakai: python3 scripts/ringkas_notebook.py <file.ipynb>
"""
import json
import re
import sys

nb = json.load(open(sys.argv[1], encoding="utf-8"))
cells = nb["cells"]
print(f"JUMLAH SEL: {len(cells)}")
for i, c in enumerate(cells):
    src = "".join(c["source"])
    outs = c.get("outputs", [])
    print(f"\n===== SEL {i} [{c['cell_type']}] src={len(src)}char n_out={len(outs)} =====")
    print(src[:800])
    for o in outs:
        t = o.get("output_type")
        if t == "stream":
            txt = "".join(o.get("text", []))
        elif t in ("execute_result", "display_data"):
            d = o.get("data", {})
            txt = "".join(d.get("text/plain", []))
            if not txt and "text/html" in d:
                txt = "[html-output]"
        elif t == "error":
            txt = f"ERROR {o.get('ename')}: {o.get('evalue')}"
        else:
            continue
        # tampilkan hanya baris yang mengandung angka/metrik/kunci
        kunci = [b for b in txt.splitlines()
                 if re.search(r"(mAP|precision|recall|F1|epoch|best|val|test|Hasil|akurasi|confusion|Ultralytics|Model|Class|P\s+R\b)", b)]
        for b in kunci[:25]:
            print("  |", b.strip()[:200].encode("ascii", "replace").decode())
