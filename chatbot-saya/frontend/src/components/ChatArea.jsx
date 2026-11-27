/**
 * ChatArea.jsx — header tipis + daftar pesan + tombol scroll ke bawah.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Message from './Message.jsx'
import EmptyState from './EmptyState.jsx'
import Composer from './Composer.jsx'
import Berpikir from './Berpikir.jsx'
import {
  ArrowDown,
  Lock,
  Menu,
  MoreHorizontal,
  RefreshCw,
  Sparkles,
  Square,
  Share2,
  TriangleAlert,
  X,
} from './icons.jsx'
import LogoGungDev from './Logo.jsx'

/**
 * Banner kecil di atas kotak pesan.
 *
 * Dua keadaan:
 *   - tamu, masih ada sisa  -> pengingat lembut "riwayat tidak disimpan"
 *   - tamu, batas habis     -> ajakan masuk (tombol Google)
 * Pengguna yang sudah login tidak melihat banner ini sama sekali.
 */
function GuestBanner({ sisa, onOpenLogin }) {
  const habis = sisa <= 0
  return (
    <div className={`guest-note ${habis ? 'is-limit' : ''}`} role="status">
      <span className="guest-note__icon" aria-hidden="true">
        {habis ? <Lock size={14} /> : <Sparkles size={14} />}
      </span>
      <p className="guest-note__text">
        {habis ? (
          <>
            Batas tamu hari ini tercapai. <strong>Masuk dengan Google</strong> untuk
            melanjutkan — riwayat Anda juga akan tersimpan.
          </>
        ) : (
          <>
            Anda memakai mode tamu — <strong>riwayat tidak disimpan</strong>. Sisa{' '}
            {sisa} pesan hari ini.
          </>
        )}
      </p>
      <button type="button" className="guest-note__btn" onClick={onOpenLogin}>
        Masuk
      </button>
    </div>
  )
}

export default function ChatArea({
  session,
  messages,
  loading,
  error,
  streamingText, // teks yang sedang ditampilkan (streaming) untuk pesan terakhir
  streamingId,
  input,
  setInput,
  onSend,
  onStop,
  onRetry,
  onDismissError,
  onOpenSidebar,
  onRegenerate,
  onEditMessage,
  onFeedback,
  onCopy,
  onShare,
  onOpenSettings,
  onOpenUsage,
  usageRingkas,
  onPickSuggestion,
  nickname,
  apiOnline,
  model,
  onModelChange,
  daftarModel,
  research,
  generationPhase = '',
  onResearchChange,
  onLampiranBerubah,
  /* --- Preferensi (dari Pengaturan) --- */
  sendWithEnter = true,
  autoScrollAktif = true,
  /* --- Status login --- */
  masuk = false,
  guestSisa = null,
  onOpenLogin,
  onLogout,
}) {
  const scrollRef = useRef(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  // Gulir otomatis hanya berjalan bila (a) preferensi pengguna aktif dan
  // (b) pengguna sedang berada di dasar percakapan. Digabung dalam satu
  // state agar tidak perlu efek tambahan.
  const [autoScroll, setAutoScroll] = useState(true)
  const bolehGulir = autoScrollAktif && autoScroll

  const title = session?.title || 'Percakapan baru'
  const isEmpty = messages.length === 0

  /* Apakah animasi "berpikir" perlu tampil di area chat?

     Patokannya: balon asisten TERAKHIR belum berisi teks untuk permintaan
     yang sedang berjalan. Dua hal penting:

     1. `streamingId` bisa masih menyimpan ID jawaban sebelumnya, jadi
        tidak bisa dipakai sebagai penanda "ini jawaban yang sekarang".
        Yang dipakai: apakah balon asisten terakhir berada SETELAH pesan
        pengguna terakhir. Urutan itulah yang menentukan.
     2. Saat riset web, server bisa lama tanpa mengirim satu karakter pun.
        Selama balon terakhir kosong, animasi harus tetap tampil — kalau
        tidak, layar terlihat diam seperti aplikasi mati. */
  const indeksUserTerakhir = messages.map((m) => m.role).lastIndexOf('user')
  const balonTerakhir = [...messages].reverse().find((m) => m.role === 'assistant')
  const indeksBalonTerakhir = balonTerakhir ? messages.indexOf(balonTerakhir) : -1
  const balonMilikPermintaanIni = indeksBalonTerakhir > indeksUserTerakhir
  const isiBalonTerakhir = balonMilikPermintaanIni
    ? balonTerakhir.id === streamingId && streamingText
      ? streamingText
      : balonTerakhir.content || ''
    : ''
  const perluIndikatorMenunggu = !isiBalonTerakhir.trim()

  /* Deteksi posisi scroll: tampilkan tombol "ke bawah" jika pengguna
     menggulir jauh dari dasar, dan matikan auto-scroll saat itu. */
  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    const nearBottom = distance < 120
    setShowScrollBtn(!nearBottom)
    setAutoScroll(nearBottom)
  }, [])

  /* Auto-scroll ke pesan terbaru (hanya jika pengguna sedang di dasar). */
  useEffect(() => {
    if (!bolehGulir) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, streamingText, loading, bolehGulir])

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    setAutoScroll(true)
  }

  const lastAssistantIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return i
    }
    return -1
  })()

  return (
    <div className="chat">
      {/* ---------------- HEADER ---------------- */}
      <header className="chat__header">
        <button
          type="button"
          className="icon-btn chat__menu"
          onClick={onOpenSidebar}
          aria-label="Buka sidebar"
        >
          <Menu size={19} />
        </button>

        <div className="chat__title-wrap">
          <h1 className="chat__title" title={title}>
            {title}
          </h1>
          <span
            className={`chat__status ${apiOnline ? 'is-online' : 'is-offline'}`}
            title={apiOnline ? 'Terhubung ke server' : 'Server tidak terhubung'}
          >
            <span className="chat__status-dot" aria-hidden="true" />
            {apiOnline ? 'Online' : 'Offline'}
          </span>
        </div>

        <div className="chat__header-actions">
          {/* Indikator jatah akun / pintu masuk panel "Jatah Saya".
              SELALU tampil — termasuk untuk tamu dan saat data belum
              termuat — supaya panel tidak pernah "hilang" bagi pengguna.
              Bila angka belum tersedia, tampil sebagai "Jatah" saja. */}
          <button
            type="button"
            className={`chat__quota ${
              usageRingkas
                ? usageRingkas.persen >= 90
                  ? 'is-danger'
                  : usageRingkas.persen >= 70
                    ? 'is-warning'
                    : ''
                : ''
            }`}
            onClick={onOpenUsage}
            title={
              usageRingkas
                ? `Jatah Anda: ${usageRingkas.persen}% terpakai. Klik untuk rincian.`
                : 'Lihat jatah dan pemakaian saya'
            }
            aria-label="Lihat jatah dan pemakaian saya"
          >
            <span className="chat__quota-dot" aria-hidden="true" />
            <span>
              {usageRingkas ? `${usageRingkas.persen}% jatah` : 'Jatah'}
            </span>
          </button>

          <button
            type="button"
            className="icon-btn"
            onClick={onShare}
            aria-label="Bagikan percakapan"
            title="Ekspor / bagikan"
          >
            <Share2 size={17} />
          </button>

          {/* Login / nama akun. Tamu melihat tombol "Masuk" yang jelas;
              pengguna login melihat namanya dan bisa keluar dari menu. */}
          {!masuk ? (
            <button
              type="button"
              className="chat__login"
              onClick={onOpenLogin}
              title="Masuk dengan Google agar riwayat tersimpan"
            >
              Masuk
            </button>
          ) : (
            <button
              type="button"
              className="chat__account"
              onClick={onLogout}
              title={`Keluar dari ${nickname || 'akun Google'}`}
            >
              Keluar
            </button>
          )}

          <button
            type="button"
            className="icon-btn"
            onClick={onOpenSettings}
            aria-label="Menu pengaturan"
            title="Pengaturan"
          >
            <MoreHorizontal size={18} />
          </button>
        </div>
      </header>

      {/* ---------------- PESAN ---------------- */}
      <div
        className="chat__scroll"
        ref={scrollRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Percakapan dengan GungDev"
      >
        <div className={`chat__inner ${isEmpty ? 'chat__inner--empty' : ''}`}>
          {isEmpty ? (
            <>
              <EmptyState nickname={nickname} onPick={onPickSuggestion} />
              {/* Kasus pertama kali memakai aplikasi: pesan pengguna belum
                  ikut tampil di daftar, jadi tanpa ini layar terlihat
                  kosong total selama AI bekerja. */}
              {loading && (
                <div className="chat__menunggu chat__menunggu--tengah" data-uji="berpikir-wrapper">
                  <div className="msg__avatar" aria-hidden="true">
                    <LogoGungDev ukuran={26} />
                  </div>
                  <div className="msg__body">
                    <Berpikir
                      aktif={loading}
                      fase={
                        generationPhase === 'research'
                          ? 'research'
                          : generationPhase === 'writing'
                            ? 'menulis'
                            : 'berpikir'
                      }
                    />
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="chat__messages">
              {messages.map((m, index) => {
                const isStreamingMsg = loading && m.id === streamingId
                /* Saat streaming, tampilkan teks yang sedang bertambah. */
                const content = isStreamingMsg && streamingText ? streamingText : m.content
                return (
                  <Message
                    key={m.id}
                    message={{ ...m, content }}
                    isStreaming={isStreamingMsg}
                    fase={
                      generationPhase === 'research'
                        ? 'research'
                        : generationPhase === 'writing'
                          ? 'menulis'
                          : 'berpikir'
                    }
                    canRegenerate={
                      m.role === 'assistant' && index === lastAssistantIndex && !loading
                    }
                    onCopy={onCopy}
                    onRegenerate={() => onRegenerate(index)}
                    onFeedback={(fb) => onFeedback(m.id, fb)}
                    onEdit={() => onEditMessage(index)}
                  />
                )
              })}

              {/* Animasi berpikir di AREA CHAT selama balon jawaban belum
                  berisi teks apa pun. Tanpa ini, pengguna hanya melihat
                  layar diam dan tidak tahu apakah aplikasi masih bekerja —
                  terutama saat riset web.

                  CATATAN: pengecekannya TIDAK boleh memakai
                  `m.id === streamingId`, karena `streamingId` bisa masih
                  menyimpan ID jawaban lama sehingga kondisinya salah dan
                  animasi hilang sama sekali. Yang benar: cari tahu apakah
                  ada balon asisten terakhir yang masih kosong. Bila tidak
                  ada (server belum mengirim apa pun), tampilkan animasi. */}
              {loading && perluIndikatorMenunggu && (
                <div className="chat__menunggu" data-uji="berpikir-wrapper">
                  <div className="msg__avatar" aria-hidden="true">
                    <LogoGungDev ukuran={26} />
                  </div>
                  <div className="msg__body">
                    <Berpikir
                      aktif={loading}
                      fase={
                        generationPhase === 'research'
                          ? 'research'
                          : generationPhase === 'writing'
                            ? 'menulis'
                            : 'berpikir'
                      }
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Tombol scroll ke bawah (mengambang) */}
      {showScrollBtn && !isEmpty && (
        <button
          type="button"
          className="scroll-bottom"
          onClick={scrollToBottom}
          aria-label="Gulir ke pesan terbaru"
          title="Ke bawah"
        >
          <ArrowDown size={18} />
        </button>
      )}

      {/* ---------------- ERROR BANNER ---------------- */}
      {error && (
        <div className="chat__error" role="alert">
          <span className="chat__error-icon" aria-hidden="true">
            <TriangleAlert size={16} />
          </span>
          <p className="chat__error-text">{error}</p>
          <button type="button" className="btn btn--sm btn--ghost" onClick={onRetry}>
            <RefreshCw size={13} /> Coba lagi
          </button>
          <button
            type="button"
            className="icon-btn icon-btn--sm"
            onClick={onDismissError}
            aria-label="Tutup pesan error"
          >
            <X size={15} />
          </button>
        </div>
      )}

      {/* ---------------- INPUT ---------------- */}
      <div className="chat__composer">
        {/* Pengingat mode tamu / ajakan masuk */}
        {!masuk && guestSisa !== null && (
          <GuestBanner sisa={guestSisa} onOpenLogin={onOpenLogin} />
        )}

        <Composer
          value={input}
          onChange={setInput}
          onSend={onSend}
          onStop={onStop}
          loading={loading}
          autoFocus={!isEmpty}
          large={isEmpty}
          placeholder={isEmpty ? 'Tanya apa saja ke GungDev…' : 'Balas GungDev…'}
          model={model}
          onModelChange={onModelChange}
          daftarModel={daftarModel}
          research={research}
           generationPhase={generationPhase}
          onResearchChange={onResearchChange}
          onLampiranBerubah={onLampiranBerubah}
          sendWithEnter={sendWithEnter}
        />
      </div>

      {/* Indikator tahap berjalan: selalu terlihat selama AI bekerja,
          termasuk di mobile, sehingga pengguna tahu aplikasi masih hidup. */}
      {loading && (
        <div className="chat__streaming-hint">
          <Berpikir
            ringkas
            aktif={loading}
            fase={
              generationPhase === 'research'
                ? 'research'
                : generationPhase === 'writing'
                  ? 'menulis'
                  : 'berpikir'
            }
          />
          <button type="button" className="link-btn" onClick={onStop}>
            <Square size={11} fill="currentColor" /> Hentikan
          </button>
        </div>
      )}
    </div>
  )
}
