/**
 * Sitasi.jsx — chip sumber kecil yang menempel di ujung kalimat.
 *
 * Tampilannya meniru ChatGPT: setelah kalimat yang memakai sumber,
 * muncul chip kecil berisi NAMA SITUS yang bisa diklik, misalnya
 *
 *     Harga awal: Rp200.000–Rp250.000/orang. [Batur Tours +1]
 *
 * Chip dibangun dari penanda [1], [2] yang ditulis model (lihat
 * pecahSitasi di lib/text.js), jadi model tidak perlu menghafal format
 * khusus — cukup menulis nomor sumber seperti biasa.
 *
 * Bila satu kalimat memakai beberapa sumber, nomor pertama menjadi nama
 * chip dan sisanya diringkas menjadi "+N" dengan daftar kecil saat
 * kursor diarahkan (title), agar jawaban tidak penuh chip.
 */
import { ringkasSitasi } from '../lib/text.js'

export function ChipSitasi({ nomor, daftar }) {
  const info = ringkasSitasi(nomor, daftar)
  if (!info) return null

  const sisa = info.lainnya
  const judulLengkap = [info.judul, ...sisa.map((s) => s.judul || s.url)].join('\n')

  return (
    <a
      className="sitasi"
      href={info.url}
      target="_blank"
      rel="noopener noreferrer"
      title={judulLengkap}
      aria-label={`Sumber: ${judulLengkap.replace(/\n/g, ', ')}`}
    >
      <span className="sitasi__label">{info.label}</span>
      {sisa.length > 0 && <span className="sitasi__sisa">+{sisa.length}</span>}
    </a>
  )
}

export default ChipSitasi
