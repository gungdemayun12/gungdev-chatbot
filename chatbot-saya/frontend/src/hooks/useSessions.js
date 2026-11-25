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
import {
  KEYS,
  keyActiveSession,
  keySessions,
  readJSON,
  removeKey,
  writeJSON,
  writeString,
} from '../lib/storage.js'
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

export function useSessions(settings, akunSub = null) {
  /* ---------------------------------------------------------------
     Riwayat dipisah per akun Google.

     `akunSub` = ID unik akun yang sedang login (null untuk tamu).

       tamu   -> tidak ada riwayat tersimpan (selalu mulai kosong)
       login  -> gungdev:sessions:<sub>  &  gungdev:active-session:<sub>
     --------------------------------------------------------------- */

  /** Muat riwayat milik akun (atau kosong untuk tamu). */
  function muatUntuk(sub) {
    if (!sub) return { sessions: [], activeId: null }
    const sessions = sanitizeSessions(readJSON(keySessions(sub), []))
    let activeId = null
    try {
      activeId = localStorage.getItem(keyActiveSession(sub))
    } catch {
      activeId = null
    }
    if (!activeId || !sessions.some((s) => s.id === activeId)) activeId = null
    return { sessions, activeId }
  }

  const awal = useMemo(() => muatUntuk(akunSub), [akunSub])

  const [sessions, setSessions] = useState(awal.sessions)
  const [activeId, setActiveId] = useState(awal.activeId)
  const [loaded, setLoaded] = useState(false)

  /* Berganti akun (login / keluar): ganti isi riwayat seketika.
     Ini juga yang membuat riwayat tamu tidak "terbawa" ke akun dan
     riwayat akun tidak tertinggal untuk tamu berikutnya. */
  const [subTerpasang, setSubTerpasang] = useState(akunSub)
  if (subTerpasang !== akunSub) {
    setSubTerpasang(akunSub)
    const baru = muatUntuk(akunSub)
    setSessions(baru.sessions)
    setActiveId(baru.activeId)
  }

  /* Simulasikan pembacaan riwayat (untuk skeleton di sidebar).
     Data sebenarnya sudah tersedia sinkron; delay kecil ini membuat
     transisi terasa halus, bukan berkedip. */
  useEffect(() => {
    const t = setTimeout(() => setLoaded(true), 220)
    return () => clearTimeout(t)
  }, [])

  /* Bersihkan sisa riwayat versi lama (sebelum ada login).

     Versi sebelumnya menyimpan riwayat tamu di gungdev:sessions tanpa
     nama akun. Sekarang riwayat tamu TIDAK boleh tersimpan, jadi kunci
     lama itu dibuang sekali saat aplikasi dimuat. */
  useEffect(() => {
    removeKey(KEYS.SESSIONS)
    removeKey(KEYS.ACTIVE_SESSION)
  }, [])

  /* Persistensi: HANYA untuk pengguna yang login DAN mengizinkan
     riwayat disimpan. Tamu tidak pernah menulis apa pun. */
  const bolehSimpan = Boolean(akunSub) && Boolean(settings.saveHistory)
  useEffect(() => {
    if (!bolehSimpan) return
    writeJSON(keySessions(akunSub), sessions)
  }, [sessions, bolehSimpan, akunSub])

  /* Simpan sesi aktif agar refresh mengembalikan posisi terakhir. */
  useEffect(() => {
    if (!bolehSimpan) return
    if (activeId) writeString(keyActiveSession(akunSub), activeId)
  }, [activeId, bolehSimpan, akunSub])

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
    if (akunSub) {
      writeJSON(keySessions(akunSub), [])
      removeKey(keyActiveSession(akunSub))
    }
  }, [akunSub])

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
    // False = riwayat tidak disimpan (tamu). Dipakai UI untuk jujur
    // memberi tahu pengguna bahwa percakapannya akan hilang.
    tersimpan: bolehSimpan,
  }
}
