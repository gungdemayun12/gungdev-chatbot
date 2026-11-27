/**
 * ModelPicker.jsx — pemilih model di dalam kotak pesan (composer).
 *
 * Bentuknya tombol pil kecil berisi nama PENDEK model aktif (mis.
 * "GPT-OSS 120B ▾") karena ruang di kotak ketik terbatas. Saat diklik
 * muncul daftar berisi NAMA ASLI model beserta keterangan singkat.
 *
 * =====================================================================
 *  MENGAPA DAFTARNYA DIPENDEKKAN
 * =====================================================================
 * Semua model (±12) dulu ditampilkan sekaligus. Di ponsel itu membuat
 * menu sangat panjang hingga mendorong kotak ketik keluar layar.
 *
 * Sekarang:
 *   - Model UTAMA (lihat MODEL_UTAMA di lib/models.js) tampil lebih
 *     dulu: GPT, Qwen, DeepSeek, Gemini 4 Argon, Gemini 3.5.
 *   - Sisanya masuk ke bagian "Model lainnya" yang bisa dibuka.
 *   - Bila model yang SEDANG AKTIF ada di bagian "lainnya", model itu
 *     tetap ditampilkan di atas (sebagai baris aktif) agar pengguna
 *     selalu melihat apa yang sedang dipakai. Tanpa ini, pengguna bisa
 *     bingung karena pilihannya "hilang" dari daftar.
 *
 * PENTING: tidak ada model yang dihapus. Semua tetap bisa dipilih —
 * yang berubah hanya urutan/tata letaknya.
 *
 * Menu terbuka KE ATAS agar tidak menutupi kotak ketik. Ditempatkan
 * tepat di sebelah kiri tombol kirim.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Brain, Check, ChevronDown, ChevronRight, Sparkles, Zap } from './icons.jsx'
import { apakahModelUtama, cariModel } from '../lib/models.js'

const IKON = { Sparkles, Zap, Brain }

/**
 * Satu baris model.
 *
 * `ringkas` dipakai di bagian "Model lainnya": keterangan disembunyikan
 * agar daftar panjang tetap mudah dipindai mata.
 */
function BarisModel({ m, aktif, ringkas = false, onPilih }) {
  const Ikon = IKON[m.Icon] || Sparkles
  const dipilih = m.id === aktif

  return (
    <button
      type="button"
      role="option"
      aria-selected={dipilih}
      className={`mpicker__item ${dipilih ? 'is-active' : ''} ${
        ringkas ? 'is-ringkas' : ''
      }`}
      onClick={() => onPilih(m.id)}
      title={m.id}
    >
      <span className="mpicker__item-icon">
        <Ikon size={15} aria-hidden="true" />
      </span>
      <span className="mpicker__item-text">
        <span className="mpicker__item-label">{m.singkat}</span>
        {!ringkas && <span className="mpicker__item-hint">{m.ket}</span>}
      </span>
      {dipilih && <Check size={15} className="mpicker__item-check" />}
    </button>
  )
}

export default function ModelPicker({ value, onChange, disabled, daftarModel }) {
  const [buka, setBuka] = useState(false)
  const [bukaLainnya, setBukaLainnya] = useState(false)
  const wrapRef = useRef(null)
  const model = daftarModel?.length ? daftarModel : null

  /* Model aktif: cari di daftar (yang kemampuannya sudah digabung
     dengan data server). Bila tidak ada, pakai definisi bawaan. */
  const aktif = (model || []).find((m) => m.id === value) || cariModel(value)

  /* Bagi daftar menjadi bagian utama dan bagian "lainnya".
     Dihitung ulang hanya bila daftar berubah. */
  const { utama, lainnya } = useMemo(() => {
    const semua = model || [aktif]
    return {
      utama: semua.filter((m) => apakahModelUtama(m.id)),
      lainnya: semua.filter((m) => !apakahModelUtama(m.id)),
    }
  }, [model, aktif])

  /* Bila model aktif tidak ada di bagian utama (mis. pengguna memilih
     model lama), tampilkan di atas agar pilihannya tetap terlihat.
     Tanpa ini, menu bisa terbuka tanpa satu pun tanda centang. */
  const aktifDiLuar = !utama.some((m) => m.id === aktif.id)

  /* Tutup menu. Bagian "Model lainnya" ikut ditutup agar menu selalu
     terbuka dalam keadaan ringkas. */
  const tutup = () => {
    setBuka(false)
    setBukaLainnya(false)
  }

  /* Tutup bila klik di luar atau tekan Escape. */
  useEffect(() => {
    if (!buka) return undefined

    const onDocClick = (e) => {
      if (!wrapRef.current?.contains(e.target)) {
        setBuka(false)
        setBukaLainnya(false)
      }
    }
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setBuka(false)
        setBukaLainnya(false)
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
    tutup()
  }

  const IkonAktif = IKON[aktif.Icon] || Sparkles

  /* Ringkasan kemampuan untuk atribut aksesibilitas. */
  const kemampuanAktif = ['bisa membaca gambar dan riset web, serta membaca file']

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

          {/* Bila model aktif termasuk "lainnya", tetap tampilkan lebih
              dulu supaya pengguna tahu model apa yang sedang dipakai. */}
          {aktifDiLuar && (
            <BarisModel m={aktif} aktif={aktif.id} onPilih={pilih} />
          )}

          {utama.map((m) => (
            <BarisModel key={m.id} m={m} aktif={aktif.id} onPilih={pilih} />
          ))}

          {lainnya.length > 0 && (
            <>
              <button
                type="button"
                className={`mpicker__more ${bukaLainnya ? 'is-open' : ''}`}
                onClick={() => setBukaLainnya((v) => !v)}
                aria-expanded={bukaLainnya}
                aria-controls="mpicker-lainnya"
              >
                <span>Model lainnya</span>
                <span className="mpicker__more-kanan">
                  <span className="mpicker__more-jumlah">{lainnya.length}</span>
                  <ChevronRight size={14} aria-hidden="true" />
                </span>
              </button>

              {bukaLainnya && (
                <div
                  id="mpicker-lainnya"
                  className="mpicker__lainnya"
                  role="group"
                  aria-label="Model lainnya"
                >
                  {lainnya.map((m) => (
                    <BarisModel
                      key={m.id}
                      m={m}
                      aktif={aktif.id}
                      ringkas
                      onPilih={pilih}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          <p className="mpicker__catatan">
            Semua model bisa riset web, membaca gambar, dan membaca file.
          </p>
        </div>
      )}
    </div>
  )
}
