/**
 * Composer.jsx — kotak input pesan.
 *
 * Fitur:
 *   - textarea auto-grow (maks 8 baris)
 *   - Enter = kirim, Shift+Enter = baris baru
 *   - tombol kirim bulat; berubah jadi tombol Stop saat AI menjawab
 *   - tombol lampirkan file (menyisipkan nama file ke pesan)
 *   - hint keyboard hanya tampil di desktop
 *   - disclaimer kecil di bawah
 */
import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Paperclip, Square } from './icons.jsx'

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
}) {
  const textareaRef = useRef(null)
  const fileRef = useRef(null)
  const [attachments, setAttachments] = useState([])

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

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const submit = () => {
    const text = value.trim()
    if (!text || loading || disabled) return

    // Sertakan daftar lampiran sebagai konteks teks.
    const attachmentNote = attachments.length
      ? `\n\n(Lampiran: ${attachments.map((a) => a.name).join(', ')})`
      : ''

    onSend(text + attachmentNote)
    setAttachments([])
  }

  const handleFiles = (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setAttachments((prev) => [
      ...prev,
      ...files.map((f) => ({ name: f.name, size: f.size })),
    ])
    e.target.value = ''
    textareaRef.current?.focus()
  }

  const canSend = value.trim().length > 0 && !loading && !disabled

  return (
    <div className={`composer ${large ? 'composer--large' : ''}`}>
      {attachments.length > 0 && (
        <ul className="composer__attachments">
          {attachments.map((a, i) => (
            <li key={`${a.name}-${i}`} className="composer__attachment">
              <Paperclip size={12} aria-hidden="true" />
              <span>{a.name}</span>
              <button
                type="button"
                onClick={() => setAttachments((prev) => prev.filter((_, idx) => idx !== i))}
                aria-label={`Lepas lampiran ${a.name}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="composer__box">
        <button
          type="button"
          className="composer__tool"
          onClick={() => fileRef.current?.click()}
          aria-label="Lampirkan file"
          title="Lampirkan file"
        >
          <Paperclip size={18} />
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          className="sr-only"
          onChange={handleFiles}
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
          placeholder={placeholder}
          rows={1}
          disabled={disabled}
          aria-label="Tulis pesan untuk GungDev"
        />

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
        )}
      </div>

      <div className="composer__footer">
        <p className="composer__disclaimer">
          GungDev bisa membuat kesalahan. Periksa kembali informasi penting.
        </p>
        <p className="composer__hint" aria-hidden="true">
          <kbd>Enter</kbd> kirim · <kbd>Shift</kbd>+<kbd>Enter</kbd> baris baru
        </p>
      </div>
    </div>
  )
}
