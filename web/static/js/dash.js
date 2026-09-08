/**
 * dash.js - Shared UI glue untuk Dashboard Pemerintah JalanPantau.
 *
 * Catatan: polling auto-refresh 30 detik + render tabel disposisi dilakukan
 * inline di masing-masing template (dashboard/index.html & disposisi.html)
 * karena tiap halaman butuh state filter/sort/peta sendiri. File ini hanya
 * utilitas bersama; jangan duplikasi polling di sini (pernah terjadi:
 * polling mati total karena membaca data-daerah yang tidak pernah dirender).
 */
document.addEventListener("DOMContentLoaded", function() {
  // Toggle sidebar mobile (bila tombol ada di halaman)
  var toggle = document.getElementById("sidebar-toggle");
  if (toggle) {
    toggle.addEventListener("click", function() {
      var sb = document.getElementById("sidebar");
      if (sb) sb.classList.toggle("show");
    });
  }
});
