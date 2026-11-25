/**
 * Modal.jsx — dialog dasar dengan overlay, fokus terkunci, dan Esc untuk tutup.
 * Dipakai untuk Pengaturan, ganti nama, konfirmasi hapus, dan daftar pintasan.
 */
import { useCallback, useEffect, useRef } from 'react'
import { X } from './icons.jsx'

export default function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  labelledBy = 'modal-title',
}) {
  const dialogRef = useRef(null)
  const lastFocused = useRef(null)

  /* Simpan elemen fokus terakhir, kembalikan saat modal ditutup. */
  useEffect(() => {
    if (!open) return
    lastFocused.current = document.activeElement
    const t = setTimeout(() => {
      const first = dialogRef.current?.querySelector(
        'input, select, textarea, button:not([data-close])',
      )
      ;(first || dialogRef.current)?.focus()
    }, 40)
    return () => {
      clearTimeout(t)
      if (lastFocused.current instanceof HTMLElement) lastFocused.current.focus()
    }
  }, [open])

  /* Esc untuk menutup + kunci scroll body + jebakan Tab. */
  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      const focusables = dialogRef.current?.querySelectorAll(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (!focusables || focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    },
    [onClose],
  )

  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  if (!open) return null

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        className={`modal modal--${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? labelledBy : undefined}
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {title && (
          <header className="modal__header">
            <h2 className="modal__title" id={labelledBy}>
              {title}
            </h2>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              aria-label="Tutup dialog"
              data-close
            >
              <X size={18} />
            </button>
          </header>
        )}
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__footer">{footer}</footer>}
      </div>
    </div>
  )
}
