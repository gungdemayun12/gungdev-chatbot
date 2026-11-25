/**
 * Toast.jsx — daftar notifikasi di pojok kanan bawah.
 * Type: 'success' | 'error' | 'info'
 */
import { Check, Info, TriangleAlert, X } from './icons.jsx'

const ICONS = {
  success: Check,
  error: TriangleAlert,
  info: Info,
}

export default function ToastStack({ toasts, onDismiss }) {
  if (!toasts.length) return null
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((t) => {
        const Icon = ICONS[t.type] || Info
        return (
          <div key={t.id} className={`toast toast--${t.type}`}>
            <span className="toast__icon" aria-hidden="true">
              <Icon size={16} />
            </span>
            <span className="toast__text">{t.message}</span>
            <button
              type="button"
              className="toast__close"
              onClick={() => onDismiss(t.id)}
              aria-label="Tutup notifikasi"
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
