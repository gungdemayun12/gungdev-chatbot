/**
 * useSessions.js — state SEMUA percakapan + persistensi localStorage.
 *
 * Model data:
 *   session = {
 *     id, title, messages: [{id, role, content, createdAt}],
 *     createdAt, updatedAt, pinned
 *   }
 *
 * "Satu sesi = satu item riwayat": seluruh bolak-balik pesan disimpan di
 * dalam satu objek session, jadi sidebar menampilkan satu baris per sesi.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { KEYS, readJSON, writeJSON, readString, writeString } from '../lib/storage.js'
import { makeTitle } from '../lib/text.js'

/** ID unik sederhana (aman untuk localStorage). */
function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

/** Membuat sesi baru yang kosong. */
export function createSession() {
  const now = Date.now()
  return {
    id: uid('s'),
    title: 'Percakapan baru',
    titleLocked: false, // true jika user sudah mengganti nama manual
    messages: [],
    createdAt: now,
    updatedAt: now,
    pinned: false,
  }
}

/** Validasi bentuk data dari localStorage. */
function sanitizeSessions(value) {
  if (!Array.isArray(value)) return []
  return value
    .filter((s) => s && typeof s.id === 'string' && Array.isArray(s.messages))
    .map((s) => ({
      id: s.id,
      title: typeof s.title === 'string' && s.title ? s.title : 'Percakapan baru',
      titleLocked: Boolean(s.titleLocked),
      messages: s.messages
        .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
        .map((m) => ({
          id: m.id || uid('m'),
          role: m.role,
          content: typeof m.content === 'string' ? m.content : '',
          createdAt: m.createdAt || Date.now(),
          feedback: m.feedback || null,
        })),
      createdAt: s.createdAt || Date.now(),
      updatedAt: s.updatedAt || s.createdAt || Date.now(),
      pinned: Boolean(s.pinned),
    }))
}

export function useSessions(settings) {
  const [sessions, setSessions] = useState(() =>
    sanitizeSessions(readJSON(KEYS.SESSIONS, [])),
  )
  const [activeId, setActiveId] = useState(() => readString(KEYS.ACTIVE_SESSION, null))
  const [loaded, setLoaded] = useState(false)

  /* Simulasikan pembacaan riwayat (untuk skeleton di sidebar).
     Data sebenarnya sudah tersedia sinkron; delay kecil ini membuat
     transisi terasa halus, bukan berkedip. */
  useEffect(() => {
    const t = setTimeout(() => setLoaded(true), 220)
    return () => clearTimeout(t)
  }, [])

  /* Persistensi: simpan sesi setiap kali berubah (bila diizinkan). */
  useEffect(() => {
    if (!settings.saveHistory) return
    writeJSON(KEYS.SESSIONS, sessions)
  }, [sessions, settings.saveHistory])

  /* Simpan sesi aktif agar refresh mengembalikan posisi terakhir. */
  useEffect(() => {
    if (activeId) writeString(KEYS.ACTIVE_SESSION, activeId)
  }, [activeId])

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) || null,
    [sessions, activeId],
  )

  /** Memperbarui satu sesi lewat fungsi updater. */
  const updateSession = useCallback((id, updater) => {
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== id) return s
        const next = typeof updater === 'function' ? updater(s) : { ...s, ...updater }
        return { ...next, updatedAt: Date.now() }
      }),
    )
  }, [])

  /** Memastikan ada sesi aktif; membuat baru bila belum ada. */
  const ensureSession = useCallback(() => {
    if (activeSession) return activeSession
    const s = createSession()
    setSessions((prev) => [s, ...prev])
    setActiveId(s.id)
    return s
  }, [activeSession])

  /** Menambah pesan ke sesi (judul otomatis dari pesan pertama). */
  const addMessage = useCallback(
    (sessionId, message) => {
      const msg = {
        id: uid('m'),
        createdAt: Date.now(),
        feedback: null,
        ...message,
      }
      updateSession(sessionId, (s) => {
        const messages = [...s.messages, msg]
        const firstUser = messages.find((m) => m.role === 'user')
        const title =
          s.titleLocked || !firstUser ? s.title : makeTitle(firstUser.content)
        return { ...s, messages, title }
      })
      return msg
    },
    [updateSession],
  )

  /** Menimpa isi satu pesan (dipakai streaming & edit). */
  const setMessageContent = useCallback(
    (sessionId, messageId, content) => {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) => (m.id === messageId ? { ...m, content } : m)),
      }))
    },
    [updateSession],
  )

  /** Memberi tanda suka / tidak suka pada pesan asisten. */
  const setFeedback = useCallback(
    (sessionId, messageId, feedback) => {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.id === messageId
            ? { ...m, feedback: m.feedback === feedback ? null : feedback }
            : m,
        ),
      }))
    },
    [updateSession],
  )

  /** Menghapus pesan mulai dari index tertentu (untuk Edit & Regenerasi). */
  const truncateMessages = useCallback(
    (sessionId, keepCount) => {
      updateSession(sessionId, (s) => ({ ...s, messages: s.messages.slice(0, keepCount) }))
    },
    [updateSession],
  )

  const newSession = useCallback(() => {
    // Pakai sesi kosong yang sudah ada bila aktif pun sudah kosong.
    if (activeSession && activeSession.messages.length === 0) return activeSession
    const s = createSession()
    setSessions((prev) => [s, ...prev])
    setActiveId(s.id)
    return s
  }, [activeSession])

  const selectSession = useCallback((id) => setActiveId(id), [])

  const renameSession = useCallback(
    (id, title) => {
      const clean = title.trim()
      if (!clean) return
      updateSession(id, (s) => ({ ...s, title: clean.slice(0, 120), titleLocked: true }))
    },
    [updateSession],
  )

  const togglePin = useCallback(
    (id) => {
      updateSession(id, (s) => ({ ...s, pinned: !s.pinned }))
    },
    [updateSession],
  )

  const deleteSession = useCallback(
    (id) => {
      setSessions((prev) => prev.filter((s) => s.id !== id))
      setActiveId((cur) => (cur === id ? null : cur))
    },
    [],
  )

  const clearAll = useCallback(() => {
    setSessions([])
    setActiveId(null)
    if (settings.saveHistory) writeJSON(KEYS.SESSIONS, [])
  }, [settings.saveHistory])

  return {
    sessions,
    activeSession,
    activeId,
    loaded,
    ensureSession,
    addMessage,
    setMessageContent,
    setFeedback,
    truncateMessages,
    newSession,
    selectSession,
    renameSession,
    togglePin,
    deleteSession,
    clearAll,
    setActiveId,
  }
}
