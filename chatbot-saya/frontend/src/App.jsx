/**
 * App.jsx â€” komponen utama GungDev.
 *
 * Tanggung jawab:
 *   - menyatukan state (sesi, pengaturan, tema, toast, modal)
 *   - mengirim pesan ke backend (streaming token per token)
 *   - pintasan keyboard global
 *   - dialog: ganti nama, konfirmasi hapus, pengaturan, pintasan
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

import Sidebar from './components/Sidebar.jsx'
import ChatArea from './components/ChatArea.jsx'
import Settings from './components/Settings.jsx'
import UsagePanel from './components/UsagePanel.jsx'
import Modal from './components/Modal.jsx'
import ToastStack from './components/Toast.jsx'

import { useSettings, resolveApiUrl } from './hooks/useSettings.js'
import { useSessions } from './hooks/useSessions.js'
import { useToasts } from './hooks/useToasts.js'
import { checkHealth, streamChat, fetchUsage } from './lib/api.js'
import {
  downloadFile,
  safeFilename,
  sessionToMarkdown,
  sessionToText,
} from './lib/text.js'

const MOBILE_BREAKPOINT = 1024

export default function App() {
  /* ---------------- State global ---------------- */
  const { settings, updateSettings, resetSettings, systemPromptFinal } = useSettings()

  // URL backend efektif: pakai isian pengguna bila ada, jika tidak
  // pakai bawaan build (VITE_API_URL di produksi / localhost saat dev).
  const apiUrl = resolveApiUrl(settings)
  const {
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
  } = useSessions(settings)

  const { toasts, toast, dismiss } = useToasts()

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [streamingText, setStreamingText] = useState('')
  const [streamingId, setStreamingId] = useState(null)
  const [apiOnline, setApiOnline] = useState(false)

  /* UI: sidebar & modal */
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [renameTarget, setRenameTarget] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [clearAllOpen, setClearAllOpen] = useState(false)

  const abortRef = useRef(null)
  const lastRequestRef = useRef(null) // untuk "Coba lagi" & regenerasi
  const isMobile = () => window.innerWidth < MOBILE_BREAKPOINT

  /* ---------------- Cek status backend ---------------- */
  const ping = useCallback(async () => {
    const ok = await checkHealth(apiUrl)
    setApiOnline(ok)
    return ok
  }, [apiUrl])

  useEffect(() => {
    const id = setInterval(ping, 20000)
    const boot = setTimeout(ping, 0)
    return () => {
      clearInterval(id)
      clearTimeout(boot)
    }
  }, [ping])

  /* ---------------- Pemakaian & kuota AI ---------------- */
  // Data ringkas untuk indikator di header. Panel rincian mengambil
  // datanya sendiri saat dibuka (lewat UsagePanel).
  const [usage, setUsage] = useState(null)
  const [usageOpen, setUsageOpen] = useState(false)

  const segarkanUsage = useCallback(async () => {
    const data = await fetchUsage(apiUrl)
    // Backend lama belum punya /usage -> null, panel disembunyikan.
    setUsage(data)
  }, [apiUrl])

  useEffect(() => {
    const boot = setTimeout(segarkanUsage, 600)
    // Segarkan tiap 60 detik; /usage tidak memakai kuota AI.
    const id = setInterval(segarkanUsage, 60000)
    return () => {
      clearTimeout(boot)
      clearInterval(id)
    }
  }, [segarkanUsage])

  /* Tutup sidebar mobile saat layar diperbesar. */
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= MOBILE_BREAKPOINT) setSidebarOpen(false)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  /* ---------------- Inti: mengirim pesan ---------------- */
  const runCompletion = useCallback(
    async ({ session, history, message, assistantMessageId = null }) => {
      setLoading(true)
      setError(null)
      setStreamingText('')

      const controller = new AbortController()
      abortRef.current = controller

      let messageId = assistantMessageId

      const ensureAssistantSlot = () => {
        if (messageId) return messageId
        const msg = addMessage(session.id, { role: 'assistant', content: '' })
        messageId = msg.id
        setStreamingId(msg.id)
        return msg.id
      }

      let buffer = ''

      try {
        await streamChat({
          baseUrl: apiUrl,
          message,
          history,
          systemPrompt: systemPromptFinal,
          temperature: settings.temperature,
          maxTokens: settings.maxTokens,
          signal: controller.signal,
          onDelta: (delta) => {
            buffer += delta
            const id = ensureAssistantSlot()
            setStreamingId(id)
            setStreamingText(buffer)
          },
          onDone: () => {
            const id = ensureAssistantSlot()
            setMessageContent(session.id, id, buffer)
          },
        })

        if (!buffer.trim()) {
          throw new Error('GungDev tidak mengirim jawaban. Silakan coba lagi.')
        }
        setApiOnline(true)
        // Segarkan angka kuota setelah percakapan berhasil.
        segarkanUsage()
      } catch (err) {
        const isAbort = err?.name === 'AbortError'

        if (isAbort) {
          /* Tombol Stop: simpan teks yang sudah masuk. */
          if (buffer.trim() && messageId) {
            setMessageContent(session.id, messageId, buffer + '\n\n_(dihentikan)_')
          } else if (messageId) {
            setMessageContent(session.id, messageId, '_(dihentikan sebelum jawaban selesai)_')
          }
          toast('Jawaban dihentikan.', 'info')
        } else {
          const isNetwork =
            err instanceof TypeError || /failed to fetch|network|load failed/i.test(err?.message || '')

          // Pesan disesuaikan konteks: di situs publik pengguna tidak
          // mungkin menjalankan uvicorn/Ollama di komputernya.
          const lokal = /^(https?:\/\/)?(localhost|127\.0\.0\.1|\[::1\])/i.test(apiUrl)
          const text = isNetwork
            ? lokal
              ? `Gagal terhubung ke ${apiUrl}. Backend lokal belum berjalan. Jalankan "uvicorn main:app --reload" di folder backend.`
              : 'Tidak dapat menghubungi server GungDev. Periksa koneksi internet Anda, lalu coba lagi.'
            : err?.message || 'Terjadi kesalahan tak terduga.'

          setError(text)
          setApiOnline(!isNetwork)

          /* Hapus placeholder kosong agar tidak ada gelembung hantu. */
          if (messageId && !buffer.trim()) {
            const idx = (activeSession?.messages || []).length
            truncateMessages(session.id, Math.max(0, idx))
          }
          if (isNetwork) toast('Backend tidak terhubung.', 'error')
        }
      } finally {
        setLoading(false)
        setStreamingText('')
        setStreamingId(null)
        abortRef.current = null
      }
    },
    [
      apiUrl,
      settings.temperature,
      settings.maxTokens,
      systemPromptFinal,
      addMessage,
      setMessageContent,
      truncateMessages,
      activeSession,
      segarkanUsage,
      toast,
    ],
  )

  /** Mengirim pesan dari kotak input (membuat sesi bila belum ada). */
  const handleSend = useCallback(
    async (rawText) => {
      const text = (rawText ?? input).trim()
      if (!text || loading) return

      const session = ensureSession()

      /* Simpan riwayat SEBELUM pesan baru ditambahkan. */
      const history = session.messages.map((m) => ({ role: m.role, content: m.content }))

      addMessage(session.id, { role: 'user', content: text })
      setInput('')
      lastRequestRef.current = { sessionId: session.id, message: text, history }

      await runCompletion({ session, history, message: text })
    },
    [input, loading, ensureSession, addMessage, runCompletion],
  )

  /** "Coba lagi" pada banner error. */
  const handleRetry = useCallback(async () => {
    setError(null)
    const req = lastRequestRef.current
    if (!req) {
      await ping()
      toast(apiOnline ? 'Server terhubung.' : 'Server masih belum terhubung.', apiOnline ? 'success' : 'error')
      return
    }
    const session = sessions.find((s) => s.id === req.sessionId)
    if (!session) return
    await runCompletion({ session, history: req.history, message: req.message })
  }, [sessions, runCompletion, ping, apiOnline, toast])

  /** Regenerasi jawaban pada index tertentu. */
  const handleRegenerate = useCallback(
    async (assistantIndex) => {
      if (loading || !activeSession) return

      const msgs = activeSession.messages
      /* Cari pesan user terakhir sebelum jawaban ini. */
      let userIndex = -1
      for (let i = assistantIndex - 1; i >= 0; i--) {
        if (msgs[i].role === 'user') {
          userIndex = i
          break
        }
      }
      if (userIndex === -1) return

      const history = msgs.slice(0, userIndex).map((m) => ({ role: m.role, content: m.content }))
      const message = msgs[userIndex].content

      /* Buang jawaban lama (dan apa pun sesudahnya), lalu minta ulang. */
      truncateMessages(activeSession.id, userIndex + 1)
      lastRequestRef.current = { sessionId: activeSession.id, message, history }

      await runCompletion({ session: activeSession, history, message })
    },
    [loading, activeSession, truncateMessages, runCompletion],
  )

  /** Edit pesan pengguna: isi ulang input & potong sesi dari situ. */
  const handleEditMessage = useCallback(
    (index) => {
      if (loading || !activeSession) return
      const msg = activeSession.messages[index]
      if (!msg || msg.role !== 'user') return
      setInput(msg.content)
      truncateMessages(activeSession.id, index)
      toast('Pesan dimasukkan ke kotak input. Kirim untuk mengirim ulang.', 'info')
    },
    [loading, activeSession, truncateMessages, toast],
  )

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  /* ---------------- Aksi riwayat ---------------- */
  const handleNewChat = useCallback(() => {
    newSession()
    setInput('')
    setError(null)
    if (isMobile()) setSidebarOpen(false)
  }, [newSession])

  /* ---------------- Pintasan keyboard ---------------- */
  useEffect(() => {
    const onKeyDown = (e) => {
      const mod = e.ctrlKey || e.metaKey

      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (isMobile()) setSidebarOpen(true)
        setTimeout(() => window.dispatchEvent(new Event('gungdev:focus-search')), 120)
        return
      }
      if (mod && e.shiftKey && e.key.toLowerCase() === 'o') {
        e.preventDefault()
        handleNewChat()
        return
      }
      if (mod && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        if (isMobile()) setSidebarOpen((v) => !v)
        else setSidebarCollapsed((v) => !v)
        return
      }
      if (e.key === 'Escape') {
        setSidebarOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [handleNewChat])

  /* ---------------- Ekspor ---------------- */
  const handleExportSession = useCallback(
    (session, format) => {
      const content =
        format === 'md' ? sessionToMarkdown(session) : sessionToText(session)
      const name = `${safeFilename(session.title)}.${format}`
      downloadFile(name, content)
      toast(`Percakapan diekspor ke ${name}`, 'success')
    },
    [toast],
  )

  const handleExportAll = useCallback(
    (format) => {
      if (!sessions.length) {
        toast('Belum ada percakapan untuk diekspor.', 'info')
        return
      }
      if (format === 'json') {
        downloadFile('gungdev-semua-percakapan.json', JSON.stringify(sessions, null, 2), 'application/json')
      } else {
        const md = sessions.map((s) => sessionToMarkdown(s)).join('\n\n---\n\n')
        downloadFile('gungdev-semua-percakapan.md', md, 'text/markdown;charset=utf-8')
      }
      toast('Semua percakapan diekspor.', 'success')
    },
    [sessions, toast],
  )

  const handleShare = useCallback(() => {
    if (!activeSession || !activeSession.messages.length) {
      toast('Belum ada percakapan untuk dibagikan.', 'info')
      return
    }
    handleExportSession(activeSession, 'md')
  }, [activeSession, handleExportSession, toast])

  const handleCopyNotice = useCallback(() => toast('Tersalin ke clipboard.', 'success'), [toast])

  const handleFeedback = useCallback(
    (messageId, fb) => {
      if (!activeSession) return
      setFeedback(activeSession.id, messageId, fb)
      toast(fb === 'up' ? 'Terima kasih atas masukannya!' : 'Masukan dicatat.', 'success')
    },
    [activeSession, setFeedback, toast],
  )

  /* ---------------- Konfirmasi hapus ---------------- */
  const confirmDelete = useCallback(() => {
    if (!deleteTarget) return
    deleteSession(deleteTarget.id)
    toast('Percakapan dihapus.', 'success')
    setDeleteTarget(null)
  }, [deleteTarget, deleteSession, toast])

  const confirmClearAll = useCallback(() => {
    clearAll()
    setClearAllOpen(false)
    setSettingsOpen(false)
    toast('Semua riwayat dihapus.', 'success')
  }, [clearAll, toast])

  const submitRename = useCallback(() => {
    if (!renameTarget) return
    renameSession(renameTarget.id, renameValue)
    setRenameTarget(null)
    toast('Nama percakapan diperbarui.', 'success')
  }, [renameTarget, renameValue, renameSession, toast])

  /* ---------------- Render ---------------- */
  const messages = activeSession?.messages || []

  const handlePickSuggestion = useCallback(
    (prompt) => {
      setInput(prompt)
    },
    [],
  )

  return (
    <div className={`app ${sidebarCollapsed ? 'app--collapsed' : ''}`}>
      <Sidebar
        open={sidebarOpen}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
        onClose={() => setSidebarOpen(false)}
        onCloseMobile={() => setSidebarOpen(false)}
        sessions={sessions}
        activeId={activeId}
        loaded={loaded}
        nickname={settings.nickname}
        onNewChat={handleNewChat}
        onSelect={selectSession}
        onRename={(s) => {
          setRenameTarget(s)
          setRenameValue(s.title)
        }}
        onPin={togglePin}
        onDelete={(s) => setDeleteTarget(s)}
        onExport={handleExportSession}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="app__main">
        <ChatArea
          session={activeSession}
          messages={messages}
          loading={loading}
          error={error}
          streamingText={streamingText}
          streamingId={streamingId}
          input={input}
          setInput={setInput}
          onSend={handleSend}
          onStop={handleStop}
          onRetry={handleRetry}
          onDismissError={() => setError(null)}
          onOpenSidebar={() => setSidebarOpen(true)}
          onRegenerate={handleRegenerate}
          onEditMessage={handleEditMessage}
          onFeedback={handleFeedback}
          onCopy={handleCopyNotice}
          onShare={handleShare}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenUsage={() => setUsageOpen(true)}
          usageRingkas={
            usage?.requests
              ? { persen: usage.requests.persen, sisa: usage.requests.sisa }
              : null
          }
          onPickSuggestion={handlePickSuggestion}
          nickname={settings.nickname}
          apiOnline={apiOnline}
        />
      </main>

      {/* ---------------- DIALOG ---------------- */}
      <Settings
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        updateSettings={updateSettings}
        resetSettings={resetSettings}
        onClearAll={() => setClearAllOpen(true)}
        onExportAll={handleExportAll}
        apiOnline={apiOnline}
        onOpenUsage={() => {
          setSettingsOpen(false)
          setUsageOpen(true)
        }}
      />

      {/* Panel pemakaian & kuota */}
      <UsagePanel
        open={usageOpen}
        onClose={() => {
          setUsageOpen(false)
          segarkanUsage()
        }}
        apiUrl={apiUrl}
        apiOnline={apiOnline}
      />

      {/* Ganti nama */}
      <Modal
        open={Boolean(renameTarget)}
        onClose={() => setRenameTarget(null)}
        title="Ganti nama percakapan"
        size="sm"
        footer={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => setRenameTarget(null)}>
              Batal
            </button>
            <button type="button" className="btn btn--primary" onClick={submitRename}>
              Simpan
            </button>
          </>
        }
      >
        <label className="sr-only" htmlFor="rename-input">
          Nama percakapan
        </label>
        <input
          id="rename-input"
          className="input"
          value={renameValue}
          maxLength={120}
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submitRename()
          }}
        />
      </Modal>

      {/* Konfirmasi hapus satu sesi */}
      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Hapus percakapan?"
        size="sm"
        footer={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => setDeleteTarget(null)}>
              Batal
            </button>
            <button type="button" className="btn btn--danger" onClick={confirmDelete}>
              Hapus
            </button>
          </>
        }
      >
        <p className="modal__text">
          Percakapan <strong>â€œ{deleteTarget?.title}â€</strong> akan dihapus permanen. Tindakan ini
          tidak dapat dibatalkan.
        </p>
      </Modal>

      {/* Konfirmasi hapus semua */}
      <Modal
        open={clearAllOpen}
        onClose={() => setClearAllOpen(false)}
        title="Hapus semua riwayat?"
        size="sm"
        footer={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => setClearAllOpen(false)}>
              Batal
            </button>
            <button type="button" className="btn btn--danger" onClick={confirmClearAll}>
              Hapus semua
            </button>
          </>
        }
      >
        <p className="modal__text">
          Seluruh percakapan ({sessions.length} sesi) akan dihapus dari peramban ini. Pastikan Anda
          sudah mengekspornya bila masih diperlukan.
        </p>
      </Modal>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}

