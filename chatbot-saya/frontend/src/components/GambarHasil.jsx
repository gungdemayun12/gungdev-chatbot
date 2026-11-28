/**
 * GambarHasil.jsx â€” menampilkan gambar yang DIBUAT oleh AI.
 *
 * Ini berbeda dari gambar yang diunggah pengguna: gambarnya baru
 * dihasilkan server, lalu dikirim sebagai data URL.
 *
 * Kenapa data URL (bukan tautan): gambar hasil layanan gratis hanya
 * tersedia sesaat. Bila UI memakai tautan, gambarnya bisa hilang saat
 * halaman dimuat ulang. Data URL membuat gambar ikut tersimpan di
 * riwayat, jadi tetap terlihat kapan pun.
 *
 * Tampilannya sengaja sederhana: gambar besar yang bisa diklik untuk
 * diunduh, dengan keterangan deskripsi di bawahnya. Tanpa nama layanan
 * pembuat gambar â€” label publiknya hanya "GungDev".
 */
import { useState } from 'react'
import { AlertCircle, Check, Download, Image as ImageIcon } from './icons.jsx'

/**
 * Apakah gambar ini dibuat sebelum perbaikan tanda air?
 *
 * MENGAPA PERLU: gambar lama di riwayat dibuat oleh kode lama yang masih
 * memakai layanan gratis, sehingga tanda air penyedia masih menempel di
 * pikselnya. Gambar itu tersimpan permanen sebagai JPEG di data URL dan
 * TIDAK berubah dengan sendirinya ketika kodenya diperbaiki.
 *
 * Pengguna berhak tahu mengapa gambarnya berbeda dari yang baru. Tanpa
 * penjelasan, ia akan mengira fiturnya masih rusak.
 *
 * CARA MENENTUKANNYA — SENGAJA TIDAK MENEBAK:
 * server menyimpan `mesin` ("utama"/"cadangan") saat gambar dibuat.
 * Gambar yang dibuat kode baru SELALU membawa penanda itu.
 *
 * Percobaan pertama memakai ukuran berkas sebagai patokan, dan itu SALAH:
 * gambar baru dari mesin cadangan (JPEG 1x1 pada uji, atau gambar yang
 * sangat terkompresi di produksi) juga kecil, sehingga gambar BARU diberi
 * peringatan "gambar lama". Peringatan palsu lebih buruk daripada tidak
 * ada peringatan — pengguna jadi meragukan gambar yang sebenarnya bersih.
 *
 * Karena itu: tanpa penanda `mesin`, gambar dianggap lama. Data lama memang
 * disimpan tanpa field itu, jadi aturan ini tepat sasaran tanpa menebak.
 */
function kemungkinanLama(gambar) {
  if (!gambar || typeof gambar !== 'object') return false
  const mesin = gambar.mesin
  return mesin !== 'utama' && mesin !== 'cadangan'
}

/** Membuat nama berkas yang aman dari deskripsi gambar. */
function namaBerkas(deskripsi, tipe) {
  const ekstensi = tipe.includes('png') ? 'png' : tipe.includes('webp') ? 'webp' : 'jpg'
  const bersih = (deskripsi || 'gambar')
    .toLowerCase()
    // Hanya huruf, angka, dan tanda hubung â€” aman di semua sistem.
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
  return `gungdev-${bersih || 'gambar'}.${ekstensi}`
}

function GambarHasil({ gambar }) {
  const [terbuka, setTerbuka] = useState(false)
  const [tersimpan, setTersimpan] = useState(false)
  const [gagalMuat, setGagalMuat] = useState(false)

  const dataUrl = gambar?.data_url || ''
  if (!dataUrl.startsWith('data:image/')) return null

  const tipe = dataUrl.slice(5, dataUrl.indexOf(';'))
  const lama = kemungkinanLama(gambar)

  /** Mengunduh gambar. Memakai data URL langsung, tanpa permintaan baru. */
  const unduh = () => {
    try {
      const tautan = document.createElement('a')
      tautan.href = dataUrl
      tautan.download = namaBerkas(gambar?.deskripsi, tipe)
      document.body.appendChild(tautan)
      tautan.click()
      document.body.removeChild(tautan)
      setTersimpan(true)
      setTimeout(() => setTersimpan(false), 1800)
    } catch {
      /* Bila peramban menolak unduhan, gambar tetap bisa dibuka
         dengan mengekliknya. Tidak perlu menampilkan galat. */
    }
  }

  if (gagalMuat) {
    return (
      <div className="hasil-gambar hasil-gambar--gagal">
        <ImageIcon size={16} aria-hidden="true" />
        <span>Gambar tidak bisa ditampilkan. Coba minta lagi ya.</span>
      </div>
    )
  }

  return (
    <figure className="hasil-gambar">
      <button
        type="button"
        className="hasil-gambar__bingkai"
        onClick={() => setTerbuka(true)}
        aria-label="Lihat gambar lebih besar"
        title="Klik untuk memperbesar"
      >
        <img
          className="hasil-gambar__img"
          src={dataUrl}
          alt={gambar?.deskripsi || 'Gambar buatan GungDev'}
          loading="lazy"
          onError={() => setGagalMuat(true)}
        />
      </button>

      <figcaption className="hasil-gambar__kaki">
        <span className="hasil-gambar__ket">
          {gambar?.sunting ? 'Gambar hasil suntingan' : 'Gambar buatan GungDev'}
        </span>
        <button
          type="button"
          className="hasil-gambar__unduh"
          onClick={unduh}
          title="Unduh gambar"
          aria-label="Unduh gambar"
        >
          {tersimpan ? <Check size={14} /> : <Download size={14} />}
          <span>{tersimpan ? 'Tersimpan' : 'Unduh'}</span>
        </button>
      </figcaption>

      {/* Penanda gambar lama â€” lihat kemungkinanLama(). Kalimatnya
          menjelaskan SEBABNYA, bukan sekadar menyalahkan gambar. */}
      {lama && (
        <div className="hasil-gambar__lama" data-uji="gambar-lama">
          <AlertCircle size={13} aria-hidden="true" />
          <span>
            Gambar ini dibuat sebelum kualitas gambar ditingkatkan, jadi tanda
            airnya mungkin masih terlihat. Minta gambar yang sama lagi untuk
            mendapat versi baru yang bersih.
          </span>
        </div>
      )}

      {/* Tampilan besar: cukup lapisan penuh, ditutup dengan klik di mana
          saja atau tombol Esc (lihat onKeyDown pada lapisan). */}
      {terbuka && (
        <div
          className="hasil-gambar__layar"
          role="dialog"
          aria-label="Gambar ukuran penuh"
          onClick={() => setTerbuka(false)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setTerbuka(false)
          }}
          tabIndex={-1}
          ref={(el) => el && el.focus()}
        >
          <img
            className="hasil-gambar__penuh"
            src={dataUrl}
            alt={gambar?.deskripsi || 'Gambar buatan GungDev'}
          />
        </div>
      )}
    </figure>
  )
}

export default GambarHasil

// Diekspor untuk pengujian logika penanda gambar lama (bukan untuk UI).
export { kemungkinanLama }
