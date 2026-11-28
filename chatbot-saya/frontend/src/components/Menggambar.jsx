/**
 * Menggambar.jsx — animasi "sedang menggambar" saat gambar dibuat.
 *
 * MENGAPA DIBUAT
 * --------------
 * Membuat gambar bisa memakan 10–40 detik. Tanpa penanda yang bergerak,
 * pengguna tidak tahu apakah aplikasi masih bekerja atau macet. Animasi
 * titik-titik yang terisi bertahap membuat prosesnya terasa seperti
 * "sedang dilukis", bukan seperti halaman yang menggantung.
 *
 * SOAL PERSENTASE — PENTING
 * -------------------------
 * Server TIDAK bisa melaporkan kemajuan sungguhan: layanan gambar baru
 * mengirim hasilnya SEKALI di akhir, tidak ada kabar di tengah jalan.
 * Karena itu persen di sini adalah PERKIRAAN waktu, bukan kemajuan nyata.
 *
 * Supaya tetap jujur:
 *   1. Angkanya TIDAK PERNAH mencapai 100% sebelum gambar benar-benar
 *      tiba — ia berhenti di 97% dan menunggu. Persen 100% baru muncul
 *      saat komponen ini dilepas (gambar siap).
 *   2. Ia bergerak cepat di awal, lalu melambat. Perasaan "hampir
 *      selesai" tidak datang terlalu dini.
 *   3. Bila melewati perkiraan, animasi berhenti di 97% dan teks berubah
 *      menjadi "hampir selesai" — tidak berpura-pura terus naik.
 *
 * Bentuk visual mengikuti contoh yang diminta pemilik situs: judul kecil
 * "Sedang menggambar", kisi titik-titik yang terisi bertahap, dan lonceng
 * persen di pojok bawah. Warnanya memakai aksen aplikasi.
 */
import { useEffect, useMemo, useRef, useState } from 'react'

/**
 * Perkiraan lama pembuatan gambar (detik). Dipakai untuk menghitung
 * laju persen. Layanan gratis sering antre, jadi angka ini sengaja
 * sedikit lebih longgar daripada waktu nyatanya.
 */
const PERKIRAAN_DETIK = 28

/** Persen maksimum sebelum gambar benar-benar tiba. */
const PERSEN_MAKS = 97

/**
 * Kisi titik: 15 x 9 = 135 titik.
 *
 * Jumlahnya dipilih supaya di layar ponsel sempit pun tetap terbaca
 * sebagai kisi yang rapi, dan supaya tiap titik cukup besar untuk
 * terlihat terisi satu per satu.
 */
const KOLOM = 15
const BARIS = 9
const JUMLAH_TITIK = KOLOM * BARIS

/**
 * Persen saat animasi baru muncul.
 *
 * TIDAK dimulai dari 0%. Dua alasan:
 *   1. Kisi yang masih kosong sama sekali terlihat seperti gambar yang
 *      gagal dimuat, bukan seperti proses yang berjalan.
 *   2. Membaca "0%" padahal prosesnya sudah berjalan terasa tidak
 *      menenangkan.
 *
 * 4% cukup untuk mengisi beberapa titik pertama, jadi mata langsung
 * melihat "ada yang sedang dikerjakan".
 */
const PERSEN_AWAL = 4

/**
 * Menghitung persen perkiraan.
 *
 * Rumusnya sengaja "melambat": akar kuadrat waktu membuat persen naik
 * cepat di detik-detik awal lalu makin pelan. Hasilnya anak tangga yang
 * terasa wajar, bukan garis lurus yang berhenti mendadak.
 */
function persenPerkiraan(detik) {
  if (detik <= 0) return PERSEN_AWAL
  const maju = Math.sqrt(detik / PERKIRAAN_DETIK)
  // Mulai dari PERSEN_AWAL, bukan 0, lalu naik tanpa pernah mundur.
  const naik = PERSEN_AWAL + maju * (PERSEN_MAKS - PERSEN_AWAL)
  return Math.min(PERSEN_MAKS, Math.round(naik))
}

export default function Menggambar({ aktif = true, deskripsi = '' }) {
  /* Waktu dihitung sejak animasi dipasang. Nilai awalnya sengaja bukan 0
     tetapi satu langkah kecil, supaya kisi sudah punya beberapa titik
     terisi pada render PERTAMA — tanpa menunggu 250 ms. */
  const mulaiRef = useRef(Date.now())
  const [detik, setDetik] = useState(0.01)

  /* Penghitung waktu. Direset setiap animasi dimulai ulang, sehingga
     persen selalu dihitung relatif terhadap gambar yang sedang dibuat. */
  useEffect(() => {
    if (!aktif) return undefined
    mulaiRef.current = Date.now()
    // 250 ms cukup halus untuk mata, tetapi tidak membebani render.
    const id = setInterval(() => {
      setDetik((Date.now() - mulaiRef.current) / 1000)
    }, 250)
    return () => clearInterval(id)
  }, [aktif])

  const persen = useMemo(() => persenPerkiraan(detik), [detik])

  /* Berapa titik yang sudah "terisi". Titik diisi berurutan dari atas
     kiri, seperti seseorang mengisi kisi satu per satu. Minimal satu
     titik selalu terisi selama animasi tampil. */
  const terisi = Math.max(1, Math.round((persen / 100) * JUMLAH_TITIK))

  if (!aktif) return null

  // Kalimat kecil di bawah judul: mengikuti tahap yang wajar.
  let ket = 'Menyiapkan kanvas'
  if (detik >= 4) ket = 'Menyusun detail'
  if (detik >= 12) ket = 'Menyempurnakan warna'
  if (detik >= 22) ket = 'Menyelesaikan sentuhan akhir'
  if (detik >= PERKIRAAN_DETIK) ket = 'Hampir selesai, terima kasih menunggu'

  return (
    <div
      className="menggambar"
      role="status"
      aria-live="polite"
      data-uji="menggambar"
      data-persen={persen}
    >
      <div className="menggambar__kepala">
        <span className="menggambar__judul">Sedang menggambar</span>
        <span className="menggambar__elipsis" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </div>

      {deskripsi && (
        <p className="menggambar__deskripsi" title={deskripsi}>
          {deskripsi}
        </p>
      )}

      {/* Kisi titik. Tiap titik diberi status terisi/belum lewat kelas.
          `aria-hidden` karena ini murni hiasan — pembaca layar sudah
          mendapat informasi dari teks dan angka persen di bawahnya. */}
      <div className="menggambar__kanvas" aria-hidden="true">
        <div
          className="menggambar__kisi"
          style={{ gridTemplateColumns: `repeat(${KOLOM}, 1fr)` }}
        >
          {Array.from({ length: JUMLAH_TITIK }, (_, i) => (
            <span
              key={i}
              className={`menggambar__titik ${i < terisi ? 'is-terisi' : ''}`}
            />
          ))}
        </div>

        {/* Lonceng persen, mengikuti contoh desain: menempel di dalam
            kanvas bagian bawah, sedikit keluar dari kisi. */}
        <span className="menggambar__persen" data-uji="menggambar-persen">
          {persen}%
        </span>
      </div>

      <p className="menggambar__ket">
        {ket}
        {detik >= 8 && (
          <span className="menggambar__detik"> · {Math.floor(detik)} dtk</span>
        )}
      </p>
    </div>
  )
}
