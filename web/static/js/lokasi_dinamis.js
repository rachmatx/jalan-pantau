/**
 * Sistem Lokasi Dinamis JalanPantau
 * 
 * Menentukan instansi dan lokasi default berdasarkan:
 * 1. GPS pengguna (jika diizinkan)
 * 2. Koordinat dari laporan/BAP
 * 3. Default fallback (Bogor)
 * 
 * Daftar instansi ditentukan berdasarkan radius dari kota/daerah.
 */

var LOKASI = {
  // Daftar kota/daerah yang didukung dengan instansi terkait
  // (selaras dengan SLUG_DAERAH di web/app.py; tanpa Medan karena
  // belum ada kantornya di tabel instansi_pemerintah)
  DAERAH: {
    bogor: {
      nama: "Bogor",
      ll: [-6.5956, 106.7916],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Bogor",
        alamat: "Jl. Raya Bogor No. 1, Kota Bogor",
        telepon: "(0251) 8321234"
      }
    },
    sukabumi: {
      nama: "Sukabumi",
      ll: [-6.9200, 106.9300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Sukabumi",
        alamat: "Jl. Raya Sukabumi No. 1, Sukabumi",
        telepon: "(0266) 212345"
      }
    },
    cianjur: {
      nama: "Cianjur",
      ll: [-6.8200, 107.1400],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Cianjur",
        alamat: "Jl. Raya Cianjur No. 1, Cianjur",
        telepon: "(0263) 212345"
      }
    },
    bandung: {
      nama: "Bandung",
      ll: [-6.9175, 107.6191],
      zoom: 13,
      instansi: {
        utama: "DSDABM Kota Bandung",
        alamat: "Jl. Cianjur No. 34, Kacapiring, Batununggal, Bandung",
        telepon: "(022) 7278819"
      }
    },
    garut: {
      nama: "Garut",
      ll: [-7.2200, 107.9100],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Garut",
        alamat: "Jl. Raya Garut No. 1, Garut",
        telepon: "(0262) 212345"
      }
    },
    tasikmalaya: {
      nama: "Tasikmalaya",
      ll: [-7.3500, 108.2200],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Tasikmalaya",
        alamat: "Jl. Raya Tasikmalaya No. 1, Tasikmalaya",
        telepon: "(0265) 312345"
      }
    },
    ciamis: {
      nama: "Ciamis",
      ll: [-7.3300, 108.3500],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Ciamis",
        alamat: "Jl. Raya Ciamis No. 1, Ciamis",
        telepon: "(0265) 712345"
      }
    },
    kuningan: {
      nama: "Kuningan",
      ll: [-6.9800, 108.4800],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Kuningan",
        alamat: "Jl. Raya Kuningan No. 1, Kuningan",
        telepon: "(0232) 812345"
      }
    },
    cirebon: {
      nama: "Cirebon",
      ll: [-6.7300, 108.5500],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Cirebon",
        alamat: "Jl. Raya Cirebon No. 1, Cirebon",
        telepon: "(0231) 212345"
      }
    },
    majalengka: {
      nama: "Majalengka",
      ll: [-6.8400, 108.2300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Majalengka",
        alamat: "Jl. Raya Majalengka No. 1, Majalengka",
        telepon: "(0233) 212345"
      }
    },
    sumedang: {
      nama: "Sumedang",
      ll: [-6.8600, 107.9200],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Sumedang",
        alamat: "Jl. Raya Sumedang No. 1, Sumedang",
        telepon: "(0261) 212345"
      }
    },
    indramayu: {
      nama: "Indramayu",
      ll: [-6.3300, 108.3200],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Indramayu",
        alamat: "Jl. Raya Indramayu No. 1, Indramayu",
        telepon: "(0234) 212345"
      }
    },
    subang: {
      nama: "Subang",
      ll: [-6.5700, 107.7600],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Subang",
        alamat: "Jl. Raya Subang No. 1, Subang",
        telepon: "(0260) 412345"
      }
    },
    purwakarta: {
      nama: "Purwakarta",
      ll: [-6.5500, 107.4300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Purwakarta",
        alamat: "Jl. Raya Purwakarta No. 1, Purwakarta",
        telepon: "(0264) 212345"
      }
    },
    karawang: {
      nama: "Karawang",
      ll: [-6.3000, 107.3000],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Karawang",
        alamat: "Jl. Raya Karawang No. 1, Karawang",
        telepon: "(0267) 412345"
      }
    },
    bekasi: {
      nama: "Bekasi",
      ll: [-6.2333, 106.9833],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Bekasi",
        alamat: "Jl. Ir. H. Juanda No. 1, Bekasi",
        telepon: "(021) 8801234"
      }
    },
    depok: {
      nama: "Depok",
      ll: [-6.4000, 106.8186],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Depok",
        alamat: "Jl. Margonda Raya No. 1, Depok",
        telepon: "(021) 7712345"
      }
    },
    cimahi: {
      nama: "Cimahi",
      ll: [-6.8800, 107.5400],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Cimahi",
        alamat: "Jl. Rd. Demang No. 1, Cimahi",
        telepon: "(022) 6612345"
      }
    },
    banjar: {
      nama: "Banjar",
      ll: [-7.3700, 108.5300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Banjar",
        alamat: "Jl. Raya Banjar No. 1, Banjar",
        telepon: "(0265) 912345"
      }
    },
    "kab-bogor": {
      nama: "Kabupaten Bogor",
      ll: [-6.4800, 106.8300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Bogor",
        alamat: "Jl. Raya Cibinong No. 1, Cibinong",
        telepon: "(021) 8751234"
      }
    },
    "kab-sukabumi": {
      nama: "Kabupaten Sukabumi",
      ll: [-6.8700, 106.9800],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Sukabumi",
        alamat: "Jl. Raya Cisaat No. 1, Sukabumi",
        telepon: "(0266) 221234"
      }
    },
    "kab-cianjur": {
      nama: "Kabupaten Cianjur",
      ll: [-6.8700, 107.1300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Cianjur",
        alamat: "Jl. Raya Cianjur No. 1, Cianjur",
        telepon: "(0263) 221234"
      }
    },
    "kab-bandung": {
      nama: "Kabupaten Bandung",
      ll: [-7.0333, 107.5167],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Bandung",
        alamat: "Jl. Raya Soreang No. 1, Soreang",
        telepon: "(022) 8771234"
      }
    },
    "kab-bandung-barat": {
      nama: "Kabupaten Bandung Barat",
      ll: [-6.8400, 107.4800],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Bandung Barat",
        alamat: "Jl. Raya Padalarang No. 1, Padalarang",
        telepon: "(022) 6801234"
      }
    },
    "kab-garut": {
      nama: "Kabupaten Garut",
      ll: [-7.2500, 107.9100],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Garut",
        alamat: "Jl. Raya Bayongbong No. 1, Garut",
        telepon: "(0262) 221234"
      }
    },
    "kab-tasikmalaya": {
      nama: "Kabupaten Tasikmalaya",
      ll: [-7.3500, 108.1100],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Tasikmalaya",
        alamat: "Jl. Raya Singaparna No. 1, Singaparna",
        telepon: "(0265) 321234"
      }
    },
    "kab-ciamis": {
      nama: "Kabupaten Ciamis",
      ll: [-7.3400, 108.3500],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Ciamis",
        alamat: "Jl. Raya Ciamis No. 1, Ciamis",
        telepon: "(0265) 721234"
      }
    },
    "kab-kuningan": {
      nama: "Kabupaten Kuningan",
      ll: [-6.9900, 108.4800],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Kuningan",
        alamat: "Jl. Raya Kuningan No. 1, Kuningan",
        telepon: "(0232) 821234"
      }
    },
    "kab-cirebon": {
      nama: "Kabupaten Cirebon",
      ll: [-6.7500, 108.5500],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Cirebon",
        alamat: "Jl. Raya Cirebon No. 1, Cirebon",
        telepon: "(0231) 221234"
      }
    },
    "kab-majalengka": {
      nama: "Kabupaten Majalengka",
      ll: [-6.8100, 108.2300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Majalengka",
        alamat: "Jl. Raya Majalengka No. 1, Majalengka",
        telepon: "(0233) 221234"
      }
    },
    "kab-sumedang": {
      nama: "Kabupaten Sumedang",
      ll: [-6.8300, 107.9800],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Sumedang",
        alamat: "Jl. Raya Sumedang No. 1, Sumedang",
        telepon: "(0261) 221234"
      }
    },
    "kab-indramayu": {
      nama: "Kabupaten Indramayu",
      ll: [-6.3500, 108.3200],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Indramayu",
        alamat: "Jl. Raya Indramayu No. 1, Indramayu",
        telepon: "(0234) 221234"
      }
    },
    "kab-subang": {
      nama: "Kabupaten Subang",
      ll: [-6.5500, 107.7600],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Subang",
        alamat: "Jl. Raya Subang No. 1, Subang",
        telepon: "(0260) 421234"
      }
    },
    "kab-purwakarta": {
      nama: "Kabupaten Purwakarta",
      ll: [-6.5400, 107.4300],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Purwakarta",
        alamat: "Jl. Raya Purwakarta No. 1, Purwakarta",
        telepon: "(0264) 221234"
      }
    },
    "kab-karawang": {
      nama: "Kabupaten Karawang",
      ll: [-6.3200, 107.3000],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Karawang",
        alamat: "Jl. Raya Karawang No. 1, Karawang",
        telepon: "(0267) 421234"
      }
    },
    "kab-bekasi": {
      nama: "Kabupaten Bekasi",
      ll: [-6.2500, 107.0800],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Bekasi",
        alamat: "Jl. Raya Cibitung No. 1, Cibitung",
        telepon: "(021) 8812345"
      }
    },
    "kab-pangandaran": {
      nama: "Kabupaten Pangandaran",
      ll: [-7.6833, 108.4900],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kabupaten Pangandaran",
        alamat: "Jl. Raya Parigi No. 1, Parigi",
        telepon: "(0265) 621234"
      }
    },
    jakarta: {
      nama: "Jakarta",
      ll: [-6.2088, 106.8456],
      zoom: 12,
      instansi: {
        utama: "Dinas Bina Marga DKI Jakarta",
        alamat: "Jl. Raya Bogor Km 28, Cimanggis, Jakarta Timur",
        telepon: "(021) 8001234"
      }
    },
    tangerang: {
      nama: "Tangerang",
      ll: [-6.1700, 106.6400],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Tangerang",
        alamat: "Jl. Raya Serpong No. 1, Tangerang",
        telepon: "(021) 5521234"
      }
    },
    semarang: {
      nama: "Semarang",
      ll: [-6.9667, 110.4167],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Semarang",
        alamat: "Jl. Pemuda No. 145, Semarang",
        telepon: "(024) 3541234"
      }
    },
    surabaya: {
      nama: "Surabaya",
      ll: [-7.2500, 112.7500],
      zoom: 13,
      instansi: {
        utama: "Dinas Bina Marga Kota Surabaya",
        alamat: "Jl. Jimerto No. 1, Surabaya",
        telepon: "(031) 5341234"
      }
    }
  },
  
  // Default fallback
  DEFAULT_DAERAH: "bogor",
  
  /**
   * Hitung jarak 2 koordinat dalam km (Haversine formula)
   */
  jarakKm: function(lat1, lon1, lat2, lon2) {
    var R = 6371; // radius bumi km
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  },
  
  /**
   * Tentukan daerah terdekat berdasarkan koordinat
   */
  cariDekat: function(lat, lon) {
    var dekat = null;
    var minJarak = Infinity;
    for (var key in this.DAERAH) {
      var d = this.DAERAH[key];
      var jarak = this.jarakKm(lat, lon, d.ll[0], d.ll[1]);
      if (jarak < minJarak) {
        minJarak = jarak;
        dekat = key;
      }
    }
    return dekat;
  },
  
  /**
   * Get lokasi default (dari localStorage atau fallback)
   */
  getDefault: function() {
    try {
      var saved = localStorage.getItem("jp_lokasi_default");
      if (saved && this.DAERAH[saved]) {
        return { key: saved, data: this.DAERAH[saved] };
      }
    } catch(e) {}
    return { key: this.DEFAULT_DAERAH, data: this.DAERAH[this.DEFAULT_DAERAH] };
  },
  
  /**
   * Set lokasi default
   */
  setDefault: function(key) {
    if (this.DAERAH[key]) {
      try { localStorage.setItem("jp_lokasi_default", key); } catch(e) {}
      return true;
    }
    return false;
  },
  
  /**
   * Update instansi berdasarkan koordinat laporan
   * @param {number} lat - Latitude
   * @param {number} lon - Longitude
   * @param {function} callback - function(daerahKey, instansiData)
   */
  updateInstansiByKoordinat: function(lat, lon, callback) {
    var daerah = this.cariDekat(lat, lon);
    var data = this.DAERAH[daerah];
    if (callback) callback(daerah, data);
    return { daerah: daerah, data: data };
  },
  
  /**
   * Update UI instansi di halaman disposisi/laporan
   */
  updateUIInstansi: function(daerahKey) {
    var d = this.DAERAH[daerahKey];
    if (!d) return;
    
    // Update semua elemen dengan class jp-instansi
    var els = document.querySelectorAll("[data-jp-instansi]");
    els.forEach(function(el) {
      var field = el.getAttribute("data-jp-instansi");
      if (d.instansi[field]) {
        el.textContent = d.instansi[field];
      }
    });
    
    // Update nama daerah
    var daerahEls = document.querySelectorAll("[data-jp-daerah]");
    daerahEls.forEach(function(el) {
      el.textContent = d.nama;
    });
  }
};

// Expose ke global scope
window.LOKASI = LOKASI;
