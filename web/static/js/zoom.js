{/* Zoom gambar ala PCB Inspector (vanilla): fit otomatis, wheel/drag,
   toolbar +/-, persen, 1:1, pas-layar, layar-penuh, keyboard.
   Label hasil SELALU tampil (terbakar di gambar server) — tanpa ambang zoom. */}
(function () {
  const STEP = 1.4, MIN = 0.1, MAX = 12;

  document.querySelectorAll(".zoomable").forEach((root) => {
    const bar = root.querySelector(".zoom-bar");
    const inner = document.createElement("div");
    inner.className = "zoom-inner";
    [...root.childNodes].forEach((n) => {
      if (n === bar) return;
      // Elemen bertanda data-zoom-fixed (mis. toolbar melayang) tetap di luar
      // .zoom-inner supaya posisinya tidak ikut transform pan/zoom.
      if (n.nodeType === 1 && n.hasAttribute("data-zoom-fixed")) return;
      inner.appendChild(n);
    });
    root.insertBefore(inner, bar);
    const pct = bar ? bar.querySelector(".zoom-pct") : null;

    let scale = 1, controlled = false, pos = { x: 0, y: 0 }, panning = false;
    let pan0 = null;

    const img = () => inner.querySelector("img");
    const nat = () => {
      const im = img();
      return im && im.naturalWidth ? { w: im.naturalWidth, h: im.naturalHeight } : null;
    };
    const cw = () => root.clientWidth, ch = () => root.clientHeight;
    const fitScale = () => {
      const n = nat(), pad = 32;
      if (!n || cw() - pad <= 0 || ch() - pad <= 0) return 1;
      return Math.min((cw() - pad) / n.w, (ch() - pad) / n.h);
    };
    const apply = () => {
      const hasImg = !!img();
      // Tanpa gambar (placeholder / overlay "Menganalisis…") state pan/zoom
      // tak bermakna -> paksa identitas agar overlay selalu tepat di tengah,
      // tak mewarisi transform & skala gambar sebelumnya.
      if (!hasImg) {
        controlled = false;
        // Jangan animasikan transisi saat beralih ke state kosong: overlay
        // harus LANGSUNG pas di tengah, bukan meluncur dari posisi gambar lama.
        inner.style.transition = "none";
      }
      inner.classList.toggle("has-img", hasImg);
      const s = controlled ? scale : fitScale();
      const n = nat();
      const p = controlled ? pos : {
        x: n ? (cw() - n.w * s) / 2 : 0,
        y: n ? (ch() - n.h * s) / 2 : 0,
      };
      inner.style.transform = `translate(${p.x}px, ${p.y}px) scale(${s})`;
      // Tulis DOM hanya bila nilainya berubah -> pan/zoom tak membebani main-thread.
      const label = `${Math.round(s * 100)}%`;
      if (pct && pct.textContent !== label) pct.textContent = label;
      const zoomAttr = String(Math.round(s * 100));
      if (root.dataset.zoom !== zoomAttr) root.dataset.zoom = zoomAttr;
    };
    const cur = () => (controlled ? scale : fitScale());
    const curPos = () => {
      const s = cur(), n = nat();
      return controlled ? pos : { x: n ? (cw() - n.w * s) / 2 : 0, y: n ? (ch() - n.h * s) / 2 : 0 };
    };

    const zoomBy = (f, cx, cy) => {
      const r = root.getBoundingClientRect();
      const base = cur(), next = Math.min(MAX, Math.max(MIN, base * f));
      const px = cx !== undefined ? cx - r.left : r.width / 2;
      const py = cy !== undefined ? cy - r.top : r.height / 2;
      const old = curPos(), k = next / (base || 1);
      scale = next; controlled = true;
      pos = { x: px - (px - old.x) * k, y: py - (py - old.y) * k };
      apply();
    };
    const fit = () => { controlled = false; apply(); };
    const reset1 = () => {
      const n = nat();
      scale = 1; controlled = true;
      pos = n ? { x: (cw() - n.w) / 2, y: (ch() - n.h) / 2 } : { x: 0, y: 0 };
      apply();
    };

    root.addEventListener("wheel", (e) => {
      if (!img()) return;
      // Zoom saat scroll — tapi hanya jika tidak sedang drag/pan
      if (panning) return;
      e.preventDefault();
      zoomBy(e.deltaY < 0 ? STEP : 1 / STEP, e.clientX, e.clientY);
    }, { passive: false });
    root.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button") || e.button !== 0 || !img()) return;
      e.preventDefault(); // cegah native image-drag & seleksi teks saat pan
      panning = true;
      inner.style.transition = "none"; // matikan animasi saat drag-pan agar mengikuti kursor
      const o = curPos();
      pan0 = { x: e.clientX, y: e.clientY, ox: o.x, oy: o.y, moved: false };
      try { root.setPointerCapture(e.pointerId); } catch { /* pointer sintetis */ }
      root.style.cursor = "grab";
    });
    // Pan di-koalesensi ke SATU apply() per frame: mouse polling tinggi bisa
    // memicu ratusan pointermove per frame -> main-thread jenuh (terasa berat
    // & patah-patah). Simpan posisi terbaru, gambar sekali di rAF.
    let rafPan = 0;
    root.addEventListener("pointermove", (e) => {
      if (!panning || !pan0) return;
      const dx = e.clientX - pan0.x, dy = e.clientY - pan0.y;
      if (!pan0.moved && Math.hypot(dx, dy) > 3) {
        pan0.moved = true;
        root.style.cursor = "grabbing";
      }
      if (!pan0.moved) return;
      if (!controlled) { controlled = true; scale = cur(); }
      pos = { x: pan0.ox + dx, y: pan0.oy + dy };
      if (rafPan) return;
      rafPan = requestAnimationFrame(() => { rafPan = 0; apply(); });
    });
    const endPan = () => { panning = false; pan0 = null; root.style.cursor = ""; inner.style.transition = ""; };
    root.addEventListener("pointerup", endPan);
    root.addEventListener("pointercancel", endPan);
    root.addEventListener("dblclick", (e) => {
      if (e.target.closest("button") || !img()) return;
      zoomBy(STEP, e.clientX, e.clientY);
    });
    root.addEventListener("keydown", (e) => {
      if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomBy(STEP); }
      else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomBy(1 / STEP); }
      else if (e.key === "0") { e.preventDefault(); fit(); }
      else if (e.key === "1") { e.preventDefault(); reset1(); }
      else if ((e.key === "f" || e.key === "F") && !e.target.closest("input,select,textarea")) {
        e.preventDefault();
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        else if (root.requestFullscreen) root.requestFullscreen().catch(() => {});
      }
    });
    if (bar) bar.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-z]");
      if (!b) return;
      const a = b.dataset.z;
      if (a === "in") zoomBy(STEP);
      else if (a === "out") zoomBy(1 / STEP);
      else if (a === "reset") reset1();
      else if (a === "fit") fit();
      else if (a === "full") {
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        else if (root.requestFullscreen) root.requestFullscreen().catch(() => {});
      }
    });
    // Gambar baru (pratinjau upload / hasil deteksi) -> selalu pas-layar ulang.
    let srcTerakhir = "";
    root.addEventListener("load", (e) => {
      if (e.target.tagName === "IMG") {
        inner.style.transition = ""; // pulihkan animasi fit setelah state kosong
        const src = e.target.currentSrc || e.target.src || "";
        if (src !== srcTerakhir) { srcTerakhir = src; controlled = false; }
        apply();
      }
    }, true);
    new ResizeObserver(() => apply()).observe(root);
    // Isi viewer bisa ditukar (placeholder <-> gambar hasil <-> overlay
    // "Menganalisis…"). Tanpa re-apply, .zoom-inner tetap memakai transform
    // gambar LAMA sehingga overlay tampak tidak di tengah / ikut terskala.
    // Observer dipasang pada `inner` (bukan `root`) agar tak memicu loop
    // lewat pct.textContent di .zoom-bar.
    new MutationObserver(() => apply()).observe(inner, {
      childList: true, subtree: true,
    });
    apply();
  });
})();
