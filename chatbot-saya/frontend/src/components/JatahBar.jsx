/**
 * JatahBar.jsx — satu kotak batas pemakaian bergaya "Plan limits".
 *
 * Bentuknya mengikuti contoh yang diminta pemilik situs:
 *
 *   ┌──────────────────────────────────────────────┐
 *   │ Batas obrolan                         100%   │
 *   │ Diperbarui dalam 5 jam                       │
 *   │ ████████████████████████████████████████████ │
 *   └──────────────────────────────────────────────┘
 *
 * MENGAPA PERSEN, BUKAN ANGKA PESAN
 * --------------------------------
 * "Sisa 47 pesan" tidak berarti banyak bagi pengguna baru: ia tidak tahu
 * 47 itu banyak atau sedikit. "100% sisa" langsung terbaca. Angka
 * aslinya tidak dihilangkan — ia tetap ada di baris keterangan kecil,
 * karena sebagian pengguna ingin tahu hitungan pastinya.
 *
 * ATURAN PENTING — SISA, BUKAN TERPAKAI
 * -------------------------------------
 * Yang ditonjolkan adalah SISA (100% = masih penuh). Itu yang ingin
 * diketahui pengguna: "berapa lagi saya bisa chat?". Bilahnya juga
 * mengisi dari kiri sesuai sisa, sehingga bilah panjang = sisa banyak.
 *
 * WARNA
 * -----
 * Hijau bukan dipakai sebagai "bagus", tetapi sebagai isyarat tenang:
 *   - sisa > 30%  : aksen biasa
 *   - sisa 10-30% : peringatan halus
 *   - sisa < 10%  : peringatan
 * Warna tidak pernah menjadi satu-satunya penanda: angka persennya
 * selalu tertulis, jadi tetap terbaca oleh pengguna buta warna.
 */

/** Membatasi angka ke rentang 0–100 dan membulatkannya. */
function batasi(nilai) {
  const n = Number(nilai)
  if (!Number.isFinite(n)) return 0
  return Math.min(100, Math.max(0, Math.round(n)))
}

/** Menghitung sisa persen dari terpakai/batas. */
function sisaPersen(terpakai, batas) {
  const b = Number(batas) || 0
  if (b <= 0) return 0
  const t = Number(terpakai) || 0
  return batasi(((b - t) / b) * 100)
}

export default function JatahBar({
  judul,
  terpakai = 0,
  batas = 0,
  sisaDetik = 0,
  keterangan,
  catatanReset,
  ikon = null,
  uji = '',
}) {
  const sisa = sisaPersen(terpakai, batas)
  const angkaSisa = Math.max(0, Number(batas) - Number(terpakai))

  // Tingkat peringatan, hanya untuk warna.
  let tingkat = ''
  if (sisa <= 10) tingkat = 'is-kritis'
  else if (sisa <= 30) tingkat = 'is-rendah'

  /* Keterangan waktu reset.
     Dibuat kalimat pendek yang wajar dibaca, bukan "detik: 25123". */
  let resetTeks = 'Diperbarui dalam —'
  if (sisaDetik > 0) {
    const jam = Math.floor(sisaDetik / 3600)
    const menit = Math.floor((sisaDetik % 3600) / 60)
    if (jam >= 1) {
      resetTeks = `Diperbarui dalam ${jam} jam${menit ? ` ${menit} menit` : ''}`
    } else if (menit >= 1) {
      resetTeks = `Diperbarui dalam ${menit} menit`
    } else {
      resetTeks = 'Diperbarui sebentar lagi'
    }
  } else if (sisa > 0) {
    // Masih ada sisa tetapi jendelanya sudah lewat: batasnya tetap boleh
    // dipakai sampai pesan berikutnya memulai jendela baru.
    resetTeks = 'Siap dipakai'
  }

  return (
    <div className={`jatah-bar ${tingkat}`} data-uji={uji || undefined}>
      <div className="jatah-bar__atas">
        <span className="jatah-bar__judul">
          {ikon}
          {judul}
        </span>
        <span className="jatah-bar__persen" data-uji={uji ? `${uji}-persen` : undefined}>
          {sisa}% sisa
        </span>
      </div>

      <div className="jatah-bar__sub">
        {catatanReset || resetTeks}
        {keterangan && (
          <span className="jatah-bar__rinci">
            {' '}
            · {angkaSisa} dari {Number(batas) || 0}
          </span>
        )}
      </div>

      {/* aria: pembaca layar mendapat satu kalimat utuh, bukan hanya
          angka tanpa konteks. */}
      <div
        className="jatah-bar__trek"
        role="progressbar"
        aria-valuenow={sisa}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${judul}: ${sisa} persen tersisa`}
      >
        <div
          className="jatah-bar__isi"
          // Isi minimum 2% saat masih ada sisa, supaya bilah tidak
          // terlihat kosong padahal sisanya tinggal sedikit.
          style={{ width: `${sisa > 0 ? Math.max(2, sisa) : 0}%` }}
        />
      </div>
    </div>
  )
}
