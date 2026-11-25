/**
 * useToasts.js — notifikasi ringan (berhasil salin, terhapus, error).
 */
import { useCallback, useRef, useState } from 'react'

let counter = 0

export function useToasts() {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const toast = useCallback(
    (message, type = 'success', duration = 2600) => {
      const id = ++counter
      setToasts((prev) => [...prev.slice(-3), { id, message, type }])
      const timer = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
        timers.current.delete(id)
      }, duration)
      timers.current.set(id, timer)
      return id
    },
    [],
  )

  return { toasts, toast, dismiss }
}
