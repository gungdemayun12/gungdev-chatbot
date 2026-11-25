/**
 * ChatArea.jsx — header tipis + daftar pesan + tombol scroll ke bawah.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Message from './Message.jsx'
import EmptyState from './EmptyState.jsx'
import Composer from './Composer.jsx'
import { ArrowDown, Menu, MoreHorizontal, RefreshCw, Square, Share2, TriangleAlert, X } from './icons.jsx'

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
  onResearchChange,
  onLampiranBerubah,
}) {
  const scrollRef = useRef(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)

  const title = session?.title || 'Percakapan baru'
  const isEmpty = messages.length === 0

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
    if (!autoScroll) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, streamingText, loading, autoScroll])

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
          {/* Indikator sisa kuota — hanya muncul bila data tersedia,
              sehingga tidak mengganggu tampilan lama saat backend lama. */}
          {usageRingkas && (
            <button
              type="button"
              className={`chat__quota ${
                usageRingkas.persen >= 90
                  ? 'is-danger'
                  : usageRingkas.persen >= 70
                    ? 'is-warning'
                    : ''
              }`}
              onClick={onOpenUsage}
              title={`Kuota AI: ${usageRingkas.persen}% terpakai hari ini. Klik untuk rincian.`}
              aria-label="Lihat pemakaian dan kuota AI"
            >
              <span className="chat__quota-dot" aria-hidden="true" />
              <span>{usageRingkas.persen}% kuota</span>
            </button>
          )}

          <button
            type="button"
            className="icon-btn"
            onClick={onShare}
            aria-label="Bagikan percakapan"
            title="Ekspor / bagikan"
          >
            <Share2 size={17} />
          </button>
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
            <EmptyState nickname={nickname} onPick={onPickSuggestion} />
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
          onResearchChange={onResearchChange}
          onLampiranBerubah={onLampiranBerubah}
        />
      </div>

      {/* Indikator stop saat streaming (muncul juga di atas input di mobile) */}
      {loading && (
        <div className="chat__streaming-hint" aria-live="polite">
          <span className="pulse-dot" aria-hidden="true" />
          GungDev sedang menjawab…
          <button type="button" className="link-btn" onClick={onStop}>
            <Square size={11} fill="currentColor" /> Hentikan
          </button>
        </div>
      )}
    </div>
  )
}
