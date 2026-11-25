/**
 * ModelPicker.jsx — pemilih model di dalam kotak pesan (composer).
 *
 * Bentuknya tombol pil kecil berisi nama PENDEK model aktif (mis.
 * "GPT-OSS 120B ▾") karena ruang di kotak ketik terbatas. Saat diklik
 * muncul daftar berisi NAMA ASLI model (mis. "openai/gpt-oss-120b")
 * beserta keterangan singkat dan penanda kemampuan:
 *
 *   Gambar  -> model bisa membaca gambar
 *   Web     -> model bisa riset di web
 *
 * Menu terbuka KE ATAS agar tidak menutupi kotak ketik. Ditempatkan
 * tepat di sebelah kiri tombol kirim.
 */
import { useEffect, useRef, useState } from 'react'
import { Brain, Check, ChevronDown, Globe, Image, Sparkles, Zap } from './icons.jsx'
import { cariModel } from '../lib/models.js'

const IKON = { Sparkles, Zap, Brain }

export default function ModelPicker({ value, onChange, disabled, daftarModel }) {
  const [buka, setBuka] = useState(false)
  const wrapRef = useRef(null)
  const model = daftarModel?.length ? daftarModel : null

  /* Model aktif: cari di daftar (yang kemampuannya sudah digabung
     dengan data server). Bila tidak ada, pakai definisi bawaan. */
  const aktif = (model || []).find((m) => m.id === value) || cariModel(value)

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
  const daftar = model || [aktif]

  /* Ringkasan kemampuan untuk atribut aksesibilitas. */
  const kemampuanAktif = [
    aktif.vision ? 'bisa membaca gambar' : null,
    aktif.browser ? 'bisa riset web' : null,
  ].filter(Boolean)

  return (
    <div className="mpicker" ref={wrapRef}>
      <button
        type="button"
        className={`mpicker__btn ${buka ? 'is-open' : ''}`}
        onClick={() => setBuka((v) => !v)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={buka}
        aria-label={`Model AI: ${aktif.id}${
          kemampuanAktif.length ? `, ${kemampuanAktif.join(', ')}` : ''
        }. Klik untuk mengganti`}
        title={`Model: ${aktif.id}${
          kemampuanAktif.length ? ` (${kemampuanAktif.join(', ')})` : ''
        }`}
      >
        <IkonAktif size={14} aria-hidden="true" />
        <span className="mpicker__label">{aktif.singkat}</span>
        <ChevronDown size={13} className="mpicker__caret" aria-hidden="true" />
      </button>

      {buka && (
        <div className="mpicker__menu" role="listbox" aria-label="Pilih model AI">
          <p className="mpicker__heading">Pilih model</p>
          {daftar.map((m) => {
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
                  {(m.vision || m.browser) && (
                    <span className="mpicker__tags">
                      {m.vision && (
                        <span className="mpicker__tag mpicker__tag--vision">
                          <Image size={10} aria-hidden="true" />
                          Gambar
                        </span>
                      )}
                      {m.browser && (
                        <span className="mpicker__tag mpicker__tag--web">
                          <Globe size={10} aria-hidden="true" />
                          Web
                        </span>
                      )}
                    </span>
                  )}
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
