/**
 * ModelPicker.jsx — pemilih model di dalam kotak pesan (composer).
 *
 * Bentuknya tombol pil kecil bertuliskan model aktif (mis. "Pintar ▾").
 * Saat diklik muncul daftar pilihan ke ATAS agar tidak menutupi kotak
 * ketik. Ditempatkan tepat di sebelah kiri tombol kirim, mengikuti
 * kebiasaan aplikasi chat modern.
 *
 * Semua yang tampil hanya label publik — tidak ada nama model teknis.
 */
import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Sparkles, Zap } from './icons.jsx'
import { MODEL_PILIHAN, cariModel } from '../lib/models.js'

const IKON = { Sparkles, Zap }

export default function ModelPicker({ value, onChange, disabled }) {
  const [buka, setBuka] = useState(false)
  const wrapRef = useRef(null)
  const aktif = cariModel(value)

  /* Tutup bila klik di luar atau tekan Escape. */
  useEffect(() => {
    if (!buka) return undefined

    const onDocClick = (e) => {
      if (!wrapRef.current?.contains(e.target)) setBuka(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setBuka(false)
      }
    }

    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [buka])

  const pilih = (id) => {
    onChange(id)
    setBuka(false)
  }

  const IkonAktif = IKON[aktif.Icon] || Sparkles

  return (
    <div className="mpicker" ref={wrapRef}>
      <button
        type="button"
        className={`mpicker__btn ${buka ? 'is-open' : ''}`}
        onClick={() => setBuka((v) => !v)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={buka}
        aria-label={`Model AI: ${aktif.label}. Klik untuk mengganti`}
        title={`Model: ${aktif.label}`}
      >
        <IkonAktif size={14} aria-hidden="true" />
        <span className="mpicker__label">{aktif.label}</span>
        <ChevronDown size={13} className="mpicker__caret" aria-hidden="true" />
      </button>

      {buka && (
        <div className="mpicker__menu" role="listbox" aria-label="Pilih model AI">
          <p className="mpicker__heading">Pilih model</p>
          {MODEL_PILIHAN.map((m) => {
            const Ikon = IKON[m.Icon] || Sparkles
            const dipilih = m.id === aktif.id
            return (
              <button
                key={m.id}
                type="button"
                role="option"
                aria-selected={dipilih}
                className={`mpicker__item ${dipilih ? 'is-active' : ''}`}
                onClick={() => pilih(m.id)}
              >
                <span className="mpicker__item-icon">
                  <Ikon size={15} aria-hidden="true" />
                </span>
                <span className="mpicker__item-text">
                  <span className="mpicker__item-label">{m.label}</span>
                  <span className="mpicker__item-hint">{m.hint}</span>
                </span>
                {dipilih && <Check size={15} className="mpicker__item-check" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
