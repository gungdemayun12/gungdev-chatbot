/**
 * Berpikir.jsx — animasi "sedang berpikir" saat AI menyiapkan jawaban.
 *
 * Kenapa dibuat:
 *   Jawaban panjang atau riset web bisa memakan puluhan detik. Tanpa
 *   penanda yang bergerak, pengguna tidak tahu apakah aplikasi masih
 *   bekerja atau sudah macet. Animasi ini memberi kepastian itu.
 *
 * Prinsip:
 *   1. JUJUR — labelnya mengikuti tahap yang BENAR-BENAR terjadi
 *      (menyiapkan → menelusuri web → menyusun jawaban). Tidak menampilkan
 *      tahap palsu yang tidak dikerjakan.
 *   2. TENANG — titik kecil yang berdenyut lembut, bukan animasi ramai.
 *      Tetap nyaman dibaca dan tidak mencolok.
 *   3. TAHAN LAMA — tidak ada progress bar yang mengarang persentase.
 *      Setelah beberapa detik, tambahan kalimat muncul agar pengguna
 *      tenang saat menunggu lama (mis. riset web).
 *
 * Tampilan mengikuti gaya yang sudah ada: teks abu-abu kecil, aksen
 * sebagai satu-satunya warna.
 */
import { useEffect, useState } from 'react'

/**
 * Tahap yang dikenal. `label` sengaja pendek (satu kata) seperti contoh
 * desain: "Menyiapkan", "Menelusuri", "Menyusun".
 */
const TAHAP = {
  menunggu: { label: 'Menyiapkan', ket: 'Membaca pesan Anda' },
  research: { label: 'Menelusuri', ket: 'Mencari di web' },
  berpikir: { label: 'Berpikir', ket: 'Menimbang jawaban terbaik' },
  menulis: { label: 'Menyusun', ket: 'Menulis jawaban' },
}

/**
 * Pesan tambahan yang muncul bila menunggu cukup lama.
 * Ditampilkan bertahap supaya pengguna tahu prosesnya masih jalan, bukan
 * macet — tanpa mengarang angka persentase.
 */
const TENANG = [
  { setelah: 8, teks: 'Masih bekerja, terima kasih sudah menunggu.' },
  { setelah: 20, teks: 'Pertanyaan ini butuh sedikit lebih lama.' },
  { setelah: 40, teks: 'Masih berjalan — jawaban panjang memang begini.' },
  { setelah: 75, teks: 'Hampir selesai. Anda bisa menghentikan kapan saja.' },
]

/**
 * @param {object} props
 * @param {'menunggu'|'research'|'berpikir'|'menulis'} props.fase
 * @param {boolean} props.aktif   Tampilkan animasi (biasanya saat loading).
 * @param {boolean} props.ringkas Hanya titik + label, tanpa kalimat bantu.
 *                                Dipakai di hint bawah kotak pesan.
 */
export default function Berpikir({ fase = 'menunggu', aktif = true, ringkas = false }) {
  const [detik, setDetik] = useState(0)

  /* Penghitung waktu tunggu. Direset setiap animasi dimulai ulang,
     sehingga kalimat bantu muncul relatif terhadap pesan ini saja.
     Saat animasi berhenti kita TIDAK memanggil setState di dalam efek
     (itu memicu render berantai); nilai lama cukup diabaikan karena
     komponen tidak dirender saat `aktif` bernilai false. */
  useEffect(() => {
    if (!aktif) return undefined
    const mulai = Date.now()
    const id = setInterval(() => {
      setDetik(Math.floor((Date.now() - mulai) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [aktif])

  if (!aktif) return null

  const t = TAHAP[fase] || TAHAP.menunggu
  // Kalimat bantu terbaru yang sudah waktunya tampil.
  const tenang = TENANG.filter((x) => detik >= x.setelah).pop()

  return (
    <div
      className={`berpikir ${ringkas ? 'berpikir--ringkas' : ''} ${fase === 'research' ? 'is-research' : ''}`}
      role="status"
      aria-live="polite"
      data-uji="berpikir"
      data-fase={fase}
    >
      <span className="berpikir__titik" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>

      {/* Bagian teks: label tahap (mengikuti gaya contoh desain) lalu
          keterangan kecil di bawahnya. */}
      <span className="berpikir__teks">
        <span className="berpikir__label">
          {t.label}
          <span className="berpikir__elipsis" aria-hidden="true">
            ...
          </span>
        </span>
        {!ringkas && (
          <span className="berpikir__ket">
            {t.ket}
            {/* Kalimat penenang menyusul di baris yang sama supaya
                pengguna punya penanda tambahan saat menunggu lama. */}
            {tenang && (
              <span className="berpikir__tenang" data-uji="berpikir-tenang">
                {' '}
                · {tenang.teks}
              </span>
            )}
          </span>
        )}
      </span>

      {/* Waktu berjalan: bukti nyata bahwa proses masih hidup. */}
      {!ringkas && detik >= 3 && (
        <span className="berpikir__detik">{detik} dtk</span>
      )}
    </div>
  )
}
