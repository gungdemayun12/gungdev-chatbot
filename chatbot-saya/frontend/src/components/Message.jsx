/**
 * Message.jsx — satu pesan dalam percakapan.
 *
 * - Pesan pengguna: bubble membulat rata kanan + menu Edit / Salin.
 * - Pesan GungDev: teks langsung di kanvas (tanpa bubble berat), avatar "G",
 *   blok <think> disembunyikan dalam panel lipat "Proses berpikir",
 *   dan aksi Salin / Regenerasi / Suka / Tidak suka.
 */
import { memo, useState } from 'react'
import Markdown from './Markdown.jsx'
import {
  Brain,
  Check,
  ChevronRight,
  Copy,
  Pencil,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
} from './icons.jsx'
import { copyToClipboard, formatTime, splitThinking } from '../lib/text.js'

/** Panel lipat untuk proses berpikir model (default tertutup). */
function ThinkingPanel({ text, streaming }) {
  const [open, setOpen] = useState(false)
  if (!text) return null

  return (
    <div className={`thinking ${open ? 'thinking--open' : ''}`}>
      <button
        type="button"
        className="thinking__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <ChevronRight size={14} className="thinking__chevron" aria-hidden="true" />
        <Brain size={14} aria-hidden="true" />
        <span>Proses berpikir</span>
        {streaming && <span className="thinking__live">sedang berpikir…</span>}
      </button>
      {open && <div className="thinking__body">{text}</div>}
    </div>
  )
}

function Message({
  message,
  isStreaming,
  onCopy,
  onRegenerate,
  onFeedback,
  onEdit,
  canRegenerate,
}) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'

  const handleCopy = async () => {
    const ok = await copyToClipboard(message.content || '')
    if (ok) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
      onCopy?.()
    }
  }

  /* --- Pesan pengguna --- */
  if (isUser) {
    return (
      <article className="msg msg--user" aria-label="Pesan Anda">
        <div className="msg__user-bubble">
          <p className="msg__user-text">{message.content}</p>
        </div>
        <div className="msg__user-actions">
          <span className="msg__time">{formatTime(message.createdAt)}</span>
          <button
            type="button"
            className="msg-action"
            onClick={onEdit}
            aria-label="Edit pesan"
            title="Edit"
          >
            <Pencil size={14} />
          </button>
          <button
            type="button"
            className="msg-action"
            onClick={handleCopy}
            aria-label={copied ? 'Tersalin' : 'Salin pesan'}
            title={copied ? 'Tersalin' : 'Salin'}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
        </div>
      </article>
    )
  }

  /* --- Pesan asisten --- */
  const { thinking, answer } = splitThinking(message.content || '')
  const showTyping = isStreaming && !answer && !thinking

  return (
    <article className="msg msg--assistant" aria-label="Jawaban GungDev">
      <div className="msg__avatar" aria-hidden="true">
        G
      </div>
      <div className="msg__body">
        <ThinkingPanel text={thinking} streaming={isStreaming} />

        {showTyping && (
          <div className="typing" aria-label="GungDev sedang menulis">
            <span />
            <span />
            <span />
          </div>
        )}

        {answer && (
          <div className="msg__content">
            <Markdown content={answer} />
            {isStreaming && <span className="caret" aria-hidden="true" />}
          </div>
        )}

        {!isStreaming && message.content && (
          <div className="msg__actions">
            <span className="msg__time">{formatTime(message.createdAt)}</span>
            <button
              type="button"
              className="msg-action"
              onClick={handleCopy}
              aria-label={copied ? 'Tersalin' : 'Salin jawaban'}
              title={copied ? 'Tersalin ✓' : 'Salin'}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
            {canRegenerate && (
              <button
                type="button"
                className="msg-action"
                onClick={onRegenerate}
                aria-label="Regenerasi jawaban"
                title="Regenerasi"
              >
                <RefreshCw size={14} />
              </button>
            )}
            <button
              type="button"
              className={`msg-action ${message.feedback === 'up' ? 'is-active' : ''}`}
              onClick={() => onFeedback?.('up')}
              aria-label="Suka jawaban ini"
              aria-pressed={message.feedback === 'up'}
              title="Suka"
            >
              <ThumbsUp size={14} />
            </button>
            <button
              type="button"
              className={`msg-action ${message.feedback === 'down' ? 'is-active' : ''}`}
              onClick={() => onFeedback?.('down')}
              aria-label="Tidak suka jawaban ini"
              aria-pressed={message.feedback === 'down'}
              title="Tidak suka"
            >
              <ThumbsDown size={14} />
            </button>
          </div>
        )}
      </div>
    </article>
  )
}

export default memo(Message)
