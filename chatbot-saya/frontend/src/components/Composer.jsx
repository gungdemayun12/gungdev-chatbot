/**
 * Composer.jsx — kotak input pesan.
 *
 * Fitur:
 *   - textarea auto-grow (maks 8 baris)
 *   - Enter = kirim, Shift+Enter = baris baru
 *   - tombol kirim bulat; berubah jadi tombol Stop saat AI menjawab
 *   - lampirkan GAMBAR (dibaca model vision) dan FILE (PDF/DOCX/XLSX/
 *     PPTX/TXT/CSV/kode) yang isinya diekstrak jadi teks di browser
 *   - tombol globe "riset lebih dalam": riset web sudah OTOMATIS untuk
 *     semua model, tombol ini hanya memaksa penggalian lebih dalam
 *   - pratinjau lampiran (thumbnail gambar, nama & ukuran file)
 *   - hint keyboard hanya tampil di desktop
 *   - disclaimer kecil di bawah
 */
import { useEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  FileText,
  Globe,
  Image as ImageIcon,
  Loader2,
  Paperclip,
  Square,
  X,
} from './icons.jsx'
import ModelPicker from './ModelPicker.jsx'
import {
  MAKS_FILE,
  MAKS_GAMBAR,
  bacaLampiran,
  formatUkuran,
} from '../lib/lampiran.js'

const MAX_ROWS = 8
const LINE_HEIGHT = 24 // px, harus sama dengan CSS
const PADDING = 24 // px vertikal textarea

export default function Composer({
  value,
  onChange,
  onSend,
  onStop,
  loading,
  disabled,
  autoFocus,
  placeholder = 'Tanya apa saja ke GungDev…',
  large = false,
  model,
  onModelChange,
  daftarModel,
  research,
  onResearchChange,
  buatGambar = false,
  onBuatGambarChange,
  onLampiranBerubah,
  sendWithEnter = true,
}) {
  const textareaRef = useRef(null)
  const fileRef = useRef(null)
  const [lampiran, setLampiran] = useState([])
  const [membaca, setMembaca] = useState(false)
  const [galat, setGalat] = useState(null)

  /* Auto-grow: sesuaikan tinggi dengan isi, maksimal 8 baris. */
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const maxHeight = MAX_ROWS * LINE_HEIGHT + PADDING
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [value])

  /* Fokus otomatis saat kotak kosong & siap. */
  useEffect(() => {
    if (autoFocus && !loading) textareaRef.current?.focus()
  }, [autoFocus, loading])

  /* Beri tahu induk setiap kali lampiran berubah, supaya model bisa
     dialihkan otomatis ke model vision saat ada gambar. */
  const jumlahGambar = lampiran.filter((l) => l.jenis === 'gambar').length
  useEffect(() => {
    onLampiranBerubah?.({
      gambar: lampiran.filter((l) => l.jenis === 'gambar'),
      file: lampiran.filter((l) => l.jenis === 'teks'),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lampiran])

  const handleKeyDown = (e) => {
    // Pengguna boleh memilih: Enter mengirim, atau Enter hanya baris baru.
    // Shift+Enter selalu baris baru (tidak pernah mengirim).
    if (e.nativeEvent.isComposing) return
    if (e.key !== 'Enter') return

    if (sendWithEnter) {
      if (e.shiftKey) return
    } else if (!(e.ctrlKey || e.metaKey)) {
      // Mode "Enter = baris baru": hanya Ctrl/Cmd+Enter yang mengirim.
      return
    }
    e.preventDefault()
    submit()
  }

  const submit = () => {
    const text = value.trim()
    const adaGambar = jumlahGambar > 0
    const adaFile = lampiran.some((l) => l.jenis === 'teks')

    // Boleh kirim tanpa teks bila ada lampiran (mis. "apa isi gambar ini?").
    if ((!text && !adaGambar && !adaFile) || loading || disabled || membaca) return

    const pesanDefault = adaGambar
      ? 'Tolong jelaskan isi gambar ini.'
      : adaFile
        ? 'Tolong rangkum dan jelaskan isi file ini.'
        : ''

    onSend({
      text: text || pesanDefault,
      images: lampiran.filter((l) => l.jenis === 'gambar').map((l) => l.dataUrl),
      files: lampiran
        .filter((l) => l.jenis === 'teks')
        .map((l) => ({ name: l.nama, text: l.teks, type: l.tipe })),
      research: Boolean(research),
      buatGambar: Boolean(buatGambar),
      // Label yang tampil di gelembung pesan pengguna.
      ringkas: lampiran.map((l) => l.nama),
    })
    setLampiran([])
    setGalat(null)
    if (buatGambar && onBuatGambarChange) {
      onBuatGambarChange(false)
    }
  }

  const handleFiles = async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (!files.length) return

    setGalat(null)
    setMembaca(true)

    const baru = []
    const masalah = []

    for (const file of files) {
      /* Batas jumlah: gambar & file dihitung terpisah. */
      const gambarSekarang = lampiran.filter((l) => l.jenis === 'gambar').length + baru.filter((l) => l.jenis === 'gambar').length
      const fileSekarang = lampiran.filter((l) => l.jenis === 'teks').length + baru.filter((l) => l.jenis === 'teks').length

      try {
        const hasil = await bacaLampiran(file)
        if (hasil.jenis === 'gambar' && gambarSekarang >= MAKS_GAMBAR) {
          masalah.push(`Maksimal ${MAKS_GAMBAR} gambar per pesan.`)
          continue
        }
        if (hasil.jenis === 'teks' && fileSekarang >= MAKS_FILE) {
          masalah.push(`Maksimal ${MAKS_FILE} file per pesan.`)
          continue
        }
        baru.push({ ...hasil, id: `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}` })
      } catch (err) {
        masalah.push(err?.message || `Gagal membaca "${file.name}".`)
      }
    }

    if (baru.length) setLampiran((prev) => [...prev, ...baru])
    if (masalah.length) setGalat(masalah.join(' '))
    setMembaca(false)
    textareaRef.current?.focus()
  }

  const lepas = (id) => {
    setLampiran((prev) => prev.filter((l) => l.id !== id))
    setGalat(null)
  }

  const canSend =
    (value.trim().length > 0 || lampiran.length > 0) && !loading && !disabled && !membaca

  return (
    <div className={`composer ${large ? 'composer--large' : ''}`}>
      {/* ---------------- PRATINJAU LAMPIRAN ---------------- */}
      {lampiran.length > 0 && (
        <ul className="composer__attachments">
          {lampiran.map((l) => (
            <li
              key={l.id}
              className={`composer__attachment composer__attachment--${l.jenis}`}
              title={l.nama}
            >
              {l.jenis === 'gambar' ? (
                <img
                  src={l.pratinjau}
                  alt={`Pratinjau ${l.nama}`}
                  className="composer__thumb"
                />
              ) : (
                <FileText size={13} aria-hidden="true" className="composer__file-icon" />
              )}
              <span className="composer__attachment-text">
                <span className="composer__attachment-name">{l.nama}</span>
                <span className="composer__attachment-meta">
                  {l.jenis === 'gambar' ? 'Gambar' : l.tipe || 'Teks'}
                  {l.ukuran ? ` · ${formatUkuran(l.ukuran)}` : ''}
                  {l.terpotong ? ' · dipotong' : ''}
                </span>
              </span>
              <button
                type="button"
                onClick={() => lepas(l.id)}
                aria-label={`Lepas lampiran ${l.nama}`}
                title="Lepas"
                className="composer__attachment-x"
              >
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {galat && (
        <p className="composer__attach-error" role="alert">
          {galat}
        </p>
      )}

      <div className="composer__box">
        <button
          type="button"
          className="composer__tool"
          onClick={() => fileRef.current?.click()}
          disabled={membaca || disabled}
          aria-label="Lampirkan file atau gambar"
          title="Lampirkan file atau gambar (PDF, DOCX, XLSX, TXT, JPG, PNG)"
        >
          {membaca ? (
            <Loader2 size={18} className="composer__spin" aria-hidden="true" />
          ) : (
            <Paperclip size={18} />
          )}
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          className="sr-only"
          onChange={handleFiles}
          accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.markdown,.csv,.tsv,.json,.yaml,.yml,.xml,.html,.htm,.css,.js,.jsx,.ts,.tsx,.py,.java,.c,.h,.cpp,.cs,.go,.rs,.rb,.php,.sql,.sh,.bash,.ini,.toml,.conf,.log,.srt,.tex,image/png,image/jpeg,image/webp"
          tabIndex={-1}
        />

        <label htmlFor="composer-input" className="sr-only">
          Tulis pesan untuk GungDev
        </label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          className="composer__input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            lampiran.length
              ? 'Tanya tentang lampiran ini…'
              : buatGambar
                ? 'Deskripsikan gambar yang ingin dibuat…'
                : placeholder
          }
          rows={1}
          disabled={disabled}
          aria-label={buatGambar ? 'Deskripsikan gambar yang ingin dibuat' : 'Tulis pesan untuk GungDev'}
        />

        {/* Tombol mode gambar: aktifkan untuk mengubah teks menjadi gambar */}
        {!loading && onBuatGambarChange && (
          <button
            type="button"
            className={`composer__tool composer__tool--image ${buatGambar ? 'is-active' : ''}`}
            onClick={() => onBuatGambarChange(!buatGambar)}
            disabled={disabled}
            aria-pressed={Boolean(buatGambar)}
            aria-label={
              buatGambar
                ? 'Mode gambar aktif. Klik untuk kembali ke mode chat'
                : 'Mode buat gambar'
            }
            title={
              buatGambar
                ? 'Mode gambar AKTIF — teks yang dikirim akan digambar oleh model'
                : 'Buat gambar (teks akan diubah menjadi gambar)'
            }
          >
            <ImageIcon size={18} />
          </button>
        )}

        {/* Tombol riset web: hanya di luar mode streaming. */}
        {!loading && onResearchChange && (
          <button
            type="button"
            className={`composer__tool composer__tool--research ${research ? 'is-active' : ''}`}
            onClick={() => onResearchChange(!research)}
            disabled={disabled}
            aria-pressed={Boolean(research)}
            aria-label={
              research
                ? 'Riset lebih dalam aktif. Klik untuk mematikan'
                : 'Paksa riset lebih dalam'
            }
            title={
              research
                ? 'Riset lebih dalam AKTIF — AI menggali lebih banyak sumber'
                : 'Paksa riset lebih dalam (riset web sudah otomatis)'
            }
          >
            <Globe size={18} />
          </button>
        )}

        {loading ? (
          <button
            type="button"
            className="composer__send composer__send--stop"
            onClick={onStop}
            aria-label="Hentikan jawaban"
            title="Hentikan"
          >
            <Square size={16} fill="currentColor" />
          </button>
        ) : (
          <>
            {onModelChange && (
              <ModelPicker
                value={model}
                onChange={onModelChange}
                disabled={disabled}
                daftarModel={daftarModel}
              />
            )}
            <button
              type="button"
              className="composer__send"
              onClick={submit}
              disabled={!canSend}
              aria-label="Kirim pesan"
              title="Kirim (Enter)"
            >
              <ArrowUp size={18} />
            </button>
          </>
        )}
      </div>

      <div className="composer__footer">
        <p className="composer__disclaimer">
          GungDev bisa membuat kesalahan. Periksa kembali informasi penting.
        </p>
        <p className="composer__hint" aria-hidden="true">
          {sendWithEnter ? (
            <>
              <kbd>Enter</kbd> kirim · <kbd>Shift</kbd>+<kbd>Enter</kbd> baris baru
            </>
          ) : (
            <>
              <kbd>Ctrl</kbd>+<kbd>Enter</kbd> kirim · <kbd>Enter</kbd> baris baru
            </>
          )}
        </p>
      </div>
    </div>
  )
}
