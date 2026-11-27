/**
 * App.jsx â€” komponen utama GungDev.
 *
 * Tanggung jawab:
 *   - menyatukan state (sesi, pengaturan, tema, toast, modal)
 *   - mengirim pesan ke backend (streaming token per token)
 *   - pintasan keyboard global
 *   - dialog: ganti nama, konfirmasi hapus, pengaturan, pintasan
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

import Sidebar from './components/Sidebar.jsx'
import ChatArea from './components/ChatArea.jsx'
import Settings from './components/Settings.jsx'
import UsagePanel from './components/UsagePanel.jsx'
import Modal from './components/Modal.jsx'
import ToastStack from './components/Toast.jsx'
import LoginModal from './components/LoginModal.jsx'

import { useSettings, resolveApiUrl } from './hooks/useSettings.js'
import { useSessions } from './hooks/useSessions.js'
import { useToasts } from './hooks/useToasts.js'
import { useAuth } from './hooks/useAuth.js'
import { checkHealth, streamChat, fetchUsage, fetchCapabilities } from './lib/api.js'
import { getTokenRiwayat } from './lib/riwayat.js'
import { gabungKemampuan, modelUntukGambar, cariModel } from './lib/models.js'
import {
  catatPesanTamu,
  bacaPemakaianTamu,
  resetPemakaianTamu,
  ringkasTamu,
} from './lib/guest.js'
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

  /* ---------------- Login Google ---------------- */
  // `user` = akun Google yang sedang login di perangkat ini, atau null
  // untuk tamu. Semua data login disimpan lokal (lihat lib/auth.js).
  const { user, masuk, inisialNama, masukSebagai, keluar } = useAuth()
  const [loginOpen, setLoginOpen] = useState(false)
  const [loginMode, setLoginMode] = useState('info') // 'info' | 'batas'

  /* Pemakaian tamu: 3 pesan/hari, dihitung di perangkat ini. */
  const [tamuPemakaian, setTamuPemakaian] = useState(() => bacaPemakaianTamu())
  const tamu = useMemo(() => ringkasTamu(tamuPemakaian), [tamuPemakaian])

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
    tersimpan,
    statusSimpan,
  } = useSessions(settings, user?.sub || null, apiUrl)

  const { toasts, toast, dismiss } = useToasts()

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [streamingText, setStreamingText] = useState('')
  const [streamingId, setStreamingId] = useState(null)
  const [generationPhase, setGenerationPhase] = useState('')
  const [apiOnline, setApiOnline] = useState(false)

  /* ---------------- Kemampuan model (gambar / riset) ---------------- */
  // Diambil dari backend sekali saat muat, lalu dipakai untuk menandai
  // menu model dan memilih model otomatis. Bila backend lama belum punya
  // /capabilities, nilai cadangan di models.js yang dipakai.
  const [capabilities, setCapabilities] = useState(null)
  const [research, setResearch] = useState(false)

  const daftarModel = useMemo(() => gabungKemampuan(capabilities), [capabilities])

  useEffect(() => {
    let batal = false
    const ambil = async () => {
      const data = await fetchCapabilities(apiUrl)
      if (!batal) setCapabilities(data)
    }
    const boot = setTimeout(ambil, 400)
    return () => {
      batal = true
      clearTimeout(boot)
    }
  }, [apiUrl])

  /* Model aktif beserta kemampuannya. */
  const modelAktif = useMemo(
    () => daftarModel.find((m) => m.id === settings.model) || cariModel(settings.model),
    [daftarModel, settings.model],
  )

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
    // Token dikirim bila ada supaya backend bisa menyertakan bagian
    // "pemakaian akun saya" — tiap akun punya angkanya sendiri.
    const data = await fetchUsage(apiUrl, { token: getTokenRiwayat() })
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
    async ({ session, history, message, assistantMessageId = null, images = [], files = [], pakaiRiset = false }) => {
      setLoading(true)
      setError(null)
      setStreamingText('')
      setGenerationPhase(pakaiRiset ? 'research' : 'thinking')

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
      let catatanModel = null

      try {
        await streamChat({
          baseUrl: apiUrl,
          message,
          history,
          systemPrompt: systemPromptFinal,
          temperature: settings.temperature,
          maxTokens: settings.maxTokens,
          model: settings.model,
          images,
          files,
          research: pakaiRiset,
          // Bila pengguna login, token membuat server mencatat pemakaian
          // atas nama akunnya (usage per akun) — bukan menumpuk ke satu
          // angka global yang dipakai bersama.
          token: getTokenRiwayat(),
          signal: controller.signal,
          onMeta: (meta) => {
            /* Server memberi tahu bila model diganti otomatis
               (mis. gambar butuh model vision). Disimpan dulu, lalu
               ditampilkan bersama jawaban agar tidak mendahului teks. */
            if (meta?.penyesuaian) catatanModel = meta.penyesuaian
          },
          onDelta: (delta) => {
            setGenerationPhase('writing')
            buffer += delta
            const id = ensureAssistantSlot()
            setStreamingId(id)
            setStreamingText(buffer)
          },
          onDone: () => {
            const id = ensureAssistantSlot()
            const akhir = catatanModel ? `${buffer}\n\n> ℹ️ ${catatanModel}` : buffer
            setMessageContent(session.id, id, akhir)
            buffer = akhir
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

          // Pesan disesuaikan konteks: saat dijalankan lokal (pengembangan)
          // pesan menyebut alamat server & perintah menjalankannya; di
          // situs publik pesan dibuat umum tanpa detail infrastruktur.
          const lokal = /^(https?:\/\/)?(localhost|127\.0\.0\.1|\[::1\])/i.test(apiUrl)
          const text = isNetwork
            ? lokal
              ? `Gagal terhubung ke ${apiUrl}. Server lokal belum berjalan. Jalankan "uvicorn main:app --reload" di folder backend.`
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
        setGenerationPhase('')
        abortRef.current = null
      }
    },
    [
      apiUrl,
      settings.temperature,
      settings.maxTokens,
      settings.model,
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
    async (payload) => {
      /* Composer mengirim objek {text, images, files, research, ringkas}.
         Dukungan bentuk lama (string) dipertahankan agar tidak ada
         pemanggil lain yang rusak. */
      const data =
        typeof payload === 'string' ? { text: payload } : payload || {}
      const text = (data.text ?? input).trim()
      const images = data.images || []
      const files = data.files || []
      const pakaiRiset = Boolean(data.research)

      if ((!text && !images.length && !files.length) || loading) return

      /* ---- Batas tamu: 3 pesan per hari ----
         Diperiksa SEBELUM pesan ditambahkan, supaya tidak ada gelembung
         pesan yang tetap muncul padahal tidak boleh dikirim. */
      if (!masuk) {
        const sekarang = ringkasTamu(bacaPemakaianTamu())
        if (sekarang.habis) {
          setLoginMode('batas')
          setLoginOpen(true)
          return
        }
        const baru = catatPesanTamu()
        setTamuPemakaian(baru)
        /* Pengingat halus pada pesan terakhir: arahkan ke login,
           jangan tunggu sampai diblokir. */
        const sisaSetelah = ringkasTamu(baru).sisa
        if (sisaSetelah === 0) {
          toast('Itu pesan tamu terakhir hari ini. Masuk agar bisa lanjut.', 'info')
        }
      }

      const session = ensureSession()

      /* Simpan riwayat SEBELUM pesan baru ditambahkan. */
      const history = session.messages.map((m) => ({ role: m.role, content: m.content }))

      /* Gelembung pesan pengguna: teks + penanda lampiran, supaya
         riwayat tetap bisa dibaca setelah halaman dimuat ulang
         (isi gambar tidak disimpan, hanya namanya). */
      const penanda = []
      if (images.length) penanda.push(`🖼️ ${images.length} gambar`)
      if (files.length) penanda.push(`📎 ${files.map((f) => f.name).join(', ')}`)
      if (pakaiRiset) penanda.push('🌐 riset web')
      const teksTampil = penanda.length
        ? `${text}\n\n_${penanda.join(' · ')}_`
        : text

      addMessage(session.id, { role: 'user', content: teksTampil })
      setInput('')
      lastRequestRef.current = {
        sessionId: session.id,
        message: text,
        history,
        images,
        files,
        pakaiRiset,
      }

      await runCompletion({ session, history, message: text, images, files, pakaiRiset })
    },
    [input, loading, ensureSession, addMessage, runCompletion, masuk, toast],
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
    await runCompletion({
      session,
      history: req.history,
      message: req.message,
      images: req.images,
      files: req.files,
      pakaiRiset: req.pakaiRiset,
    })
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

  /* ---------------- Aksi login Google ---------------- */
  const openLogin = useCallback(
    (mode = 'info') => {
      setLoginMode(mode)
      setLoginOpen(true)
    },
    [],
  )

  /**
   * Setelah Google berhasil: simpan identitas, tutup dialog, dan beri
   * tahu pengguna apa yang berubah. Riwayat tamu TIDAK dimigrasikan —
   * memang tidak tersimpan, dan mencampurnya ke akun akan mengejutkan.
   */
  const handleLoginBerhasil = useCallback(
    (akun) => {
      masukSebagai(akun)
      setLoginOpen(false)
      resetPemakaianTamu()
      setTamuPemakaian(bacaPemakaianTamu())
      if (isMobile()) setSidebarOpen(false)
      toast(
        `Selamat datang, ${akun.name.split(' ')[0]}! Riwayat Anda kini tersimpan di akun dan bisa dibuka dari perangkat lain.`,
        'success',
      )
    },
    [masukSebagai, toast],
  )

  const handleLoginGagal = useCallback(
    (pesan) => toast(pesan || 'Login Google gagal. Silakan coba lagi.', 'error'),
    [toast],
  )

  /**
   * Keluar: kembali ke mode tamu.
   *
   * Riwayat akun TETAP tersimpan di server (dan salinan perangkat),
   * sehingga saat masuk lagi dengan akun yang sama — dari perangkat mana
   * pun — percakapan lama muncul kembali.
   */
  const handleLogout = useCallback(() => {
    keluar()
    setInput('')
    setError(null)
    setTamuPemakaian(bacaPemakaianTamu())
    toast('Anda sudah keluar. Riwayat tetap tersimpan di akun Anda.', 'info')
  }, [keluar, toast])

  /* Bila sesi login sudah ada saat halaman dimuat (pengguna menutup tab
     lalu kembali), hitungan tamu tidak relevan lagi: bersihkan sekali.
     Ini juga menjaga data lama agar tidak "menghantui" kuota akun. */
  useEffect(() => {
    if (!masuk) return
    resetPemakaianTamu()
  }, [masuk])

  /* Bila batas tamu habis saat halaman baru dibuka, tampilkan ajakan
     login sekali — tapi jangan memaksa; pengguna tetap bisa menutupnya. */
  useEffect(() => {
    if (masuk || !tamu.habis) return
    const t = setTimeout(() => openLogin('batas'), 900)
    return () => clearTimeout(t)
    // Hanya dievaluasi saat status login berubah / pertama dimuat.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [masuk])

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

  /* ---------------- Lampiran & riset: ganti model otomatis ------------- */
  /**
   * Dipanggil Composer setiap kali lampiran berubah.
   *
   * Bila pengguna melampirkan gambar tetapi model aktifnya bukan model
   * vision, model diganti otomatis ke model vision — sehingga gambar
   * benar-benar terbaca, bukan gagal. Pengguna diberi tahu lewat toast
   * agar tidak bingung melihat nama model berubah.
   */
  const handleLampiranBerubah = useCallback(
    (info) => {
      const adaGambar = info?.gambar?.length > 0
      if (!adaGambar) return

      const target = modelUntukGambar(capabilities)
      if (modelAktif?.vision || settings.model === target) return

      updateSettings({ model: target })
      toast(
        `Model diganti ke ${target} karena gambar hanya bisa dibaca model tersebut.`,
        'info',
      )
    },
    [capabilities, modelAktif, settings.model, updateSettings, toast],
  )

  /**
   * Mengaktifkan/mematikan riset web.
   *
   * Riset TIDAK mengganti model. Riset dikerjakan di server (lihat
   * backend/riset.py), jadi semua model bisa riset dengan kualitas yang
   * sama — pengguna tidak perlu berpindah model hanya untuk mencari
   * informasi di web.
   */
  const handleResearchChange = useCallback(
    (aktif) => {
      setResearch(aktif)
    },
    [],
  )

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
        user={user}
        inisialAkun={inisialNama}
        onOpenLogin={() => openLogin(tamu.habis ? 'batas' : 'info')}
        onLogout={handleLogout}
        guestSisa={masuk ? null : tamu.sisa}
        guestHabis={tamu.habis}
        statusSimpan={statusSimpan}
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
          model={settings.model}
          onModelChange={(id) => updateSettings({ model: id })}
          daftarModel={daftarModel}
          research={research}
           generationPhase={generationPhase}
          onResearchChange={handleResearchChange}
          onLampiranBerubah={handleLampiranBerubah}
          masuk={masuk}
          guestSisa={masuk ? null : tamu.sisa}
          onOpenLogin={() => openLogin(tamu.habis ? 'batas' : 'info')}
          onLogout={handleLogout}
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
        apiUrl={apiUrl}
        user={user}
        onOpenLogin={() => {
          setSettingsOpen(false)
          openLogin('info')
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

      {/* Masuk dengan Google */}
      <LoginModal
        open={loginOpen}
        mode={loginMode}
        onClose={() => setLoginOpen(false)}
        onAkun={handleLoginBerhasil}
        onError={handleLoginGagal}
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
          Seluruh percakapan ({sessions.length} sesi) akan dihapus dari
          {user ? ' akun Anda dan semua perangkat yang memakainya' : ' peramban ini'}. Tindakan ini
          tidak bisa dibatalkan.
        </p>
        {!tersimpan && (
          <p className="modal__text modal__text--muted">
            Anda sedang memakai mode tamu, jadi percakapan ini memang tidak tersimpan permanen.
          </p>
        )}
      </Modal>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}

