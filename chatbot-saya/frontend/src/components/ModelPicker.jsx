/**
 * ModelPicker.jsx — pemilih model di dalam kotak pesan (composer).
 *
 * Bentuknya tombol pil kecil berisi nama PENDEK model aktif (mis.
 * "GPT-OSS 120B ▾") karena ruang di kotak ketik terbatas. Saat diklik
 * muncul daftar berisi NAMA ASLI model (mis. "openai/gpt-oss-120b")
 * beserta keterangan singkat.
 *
 * Menu terbuka KE ATAS agar tidak menutupi kotak ketik. Ditempatkan
 * tepat di sebelah kiri tombol kirim.
 */
import { useEffect, useRef, useState } from 'react'
import { Brain, Check, ChevronDown, Sparkles, Zap } from './icons.jsx'
import { MODEL_PILIHAN, cariModel } from '../lib/models.js'

const IKON = { Sparkles, Zap, Brain }

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
        aria-label={`Model AI: ${aktif.id}. Klik untuk mengganti`}
        title={`Model: ${aktif.id}`}
      >
        <IkonAktif size={14} aria-hidden="true" />
        <span className="mpicker__label">{aktif.singkat}</span>
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
                  <span className="mpicker__item-label">{m.id}</span>
                  <span className="mpicker__item-hint">{m.ket}</span>
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
