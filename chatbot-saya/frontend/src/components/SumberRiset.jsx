/**
 * SumberRiset.jsx — kartu sumber di bawah jawaban riset web.
 *
 * Tampilannya meniru ChatGPT: satu baris ringkas "Sumber: [1] Judul situs
 * +3" yang bisa dibuka untuk melihat seluruh daftar sumber bernomor.
 *
 * Nomor di sini SAMA dengan penanda [1], [2] yang ditulis model di dalam
 * jawabannya, jadi pengguna bisa mencocokkan kalimat dengan sumbernya.
 *
 * Sumbernya datang dari server (lihat riset.daftar_sumber). Bila model
 * lupa menulis penanda, kartu tetap ditampilkan — pengguna tetap tahu
 * dari mana jawaban itu diambil.
 */
import { useState } from 'react'
import { ChevronRight, Globe } from './icons.jsx'

/** Satu kartu sumber: nomor, judul, dan alamat situs. */
function KartuSumber({ s }) {
  const judul = s.judul || s.url
  return (
    <li className="sumber__item">
      <a
        className="sumber__link"
        href={s.url}
        target="_blank"
        rel="noopener noreferrer"
        title={judul}
      >
        <span className="sumber__nomor">{s.nomor}</span>
        <span className="sumber__teks">
          <span className="sumber__judul">{judul}</span>
          {s.situs && <span className="sumber__situs">{s.situs}</span>}
        </span>
      </a>
    </li>
  )
}

function SumberRiset({ sumber }) {
  const [open, setOpen] = useState(false)

  if (!Array.isArray(sumber) || sumber.length === 0) return null

  const pertama = sumber[0]
  const sisa = sumber.length - 1

  return (
    <div className="sumber">
      <button
        type="button"
        className="sumber__ringkas"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={open ? 'Sembunyikan daftar sumber' : 'Lihat semua sumber'}
      >
        <Globe size={13} aria-hidden="true" />
        <span className="sumber__label">Sumber:</span>
        <span className="sumber__awal">{pertama.situs || pertama.judul}</span>
        {sisa > 0 && <span className="sumber__sisa">+{sisa}</span>}
        <ChevronRight
          size={13}
          className={`sumber__chevron ${open ? 'is-open' : ''}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <ol className="sumber__daftar">
          {sumber.map((s) => (
            <KartuSumber key={`${s.nomor}-${s.url}`} s={s} />
          ))}
        </ol>
      )}
    </div>
  )
}

export default SumberRiset
