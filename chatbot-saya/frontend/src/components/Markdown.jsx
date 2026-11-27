/**
 * Markdown.jsx — render Markdown penuh untuk jawaban GungDev.
 *
 * Kenapa perlu library? Sebelumnya tanda ** tampil mentah karena teks
 * dirender apa adanya. Sekarang:
 *   - react-markdown + remark-gfm  => **bold**, list, tabel, link, dll.
 *   - rehype-highlight             => syntax highlighting code block
 *   - DOMPurify                    => sanitasi HTML (anti-XSS)
 *
 * Catatan keamanan: react-markdown tidak mengeksekusi HTML mentah secara
 * default, dan kita menambahkan DOMPurify pada hasil akhir sebagai lapisan
 * kedua sebelum disisipkan ke DOM.
 */
import { memo, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import DOMPurify from 'dompurify'
import { Check, Copy } from './icons.jsx'
import { copyToClipboard } from '../lib/text.js'
import { pecahSitasi } from '../lib/text.js'
import ChipSitasi from './Sitasi.jsx'

/** Tombol "Salin" untuk satu blok kode. */
function CopyCodeButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    const ok = await copyToClipboard(text)
    if (!ok) return
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <button
      type="button"
      className="code-copy"
      onClick={handleCopy}
      aria-label={copied ? 'Tersalin' : 'Salin kode'}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      <span>{copied ? 'Tersalin ✓' : 'Salin'}</span>
    </button>
  )
}

/** Mengambil teks polos dari pohon React (untuk tombol salin). */
function nodeToText(node) {
  if (node === null || node === undefined) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(nodeToText).join('')
  if (node.props && node.props.children) return nodeToText(node.props.children)
  return ''
}

/** Blok kode dengan header (nama bahasa + tombol salin). */
function CodeBlock({ children, className }) {
  const language = useMemo(() => {
    const match = /language-([\w+-]+)/.exec(className || '')
    return match ? match[1] : 'teks'
  }, [className])

  const rawText = useMemo(() => nodeToText(children).replace(/\n$/, ''), [children])

  return (
    <div className="code-block">
      <div className="code-block__header">
        <span className="code-block__lang">{language}</span>
        <CopyCodeButton text={rawText} />
      </div>
      <pre className="code-block__pre">
        <code className={className}>{children}</code>
      </pre>
    </div>
  )
}

/** Komponen utama. `content` adalah teks Markdown. */
function Markdown({ content, sumber }) {
  /* Lapisan keamanan tambahan: buang skrip/atribut berbahaya dari string. */
  const safeContent = useMemo(() => {
    // DOMPurify pada string Markdown akan menghapus tag HTML berbahaya,
    // sementara sintaks Markdown (**, #, -, dll.) tidak tersentuh.
    return DOMPurify.sanitize(content || '', {
      USE_PROFILES: { html: true },
      ADD_ATTR: ['target', 'rel'],
      FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form'],
      FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
    })
  }, [content])

  /* Sitasi sebaris: penanda [1] diubah menjadi chip nama situs yang bisa
     diklik, persis setelah kalimat yang memakainya. Bila tidak ada daftar
     sumber, teks dirender apa adanya (satu segmen utuh). */
  const segmen = useMemo(() => pecahSitasi(safeContent, sumber), [safeContent, sumber])
  const adaSitasi = segmen.some((s) => s.jenis === 'sitasi')

  const renderer = (teks, kunci) => (
    <ReactMarkdown
      key={kunci}
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
      components={{
        /* Blok kode: bungkus dengan header bahasa + tombol Salin. */
        pre({ children }) {
          const child = Array.isArray(children) ? children[0] : children
          const className = child?.props?.className || ''
          return <CodeBlock className={className}>{child?.props?.children}</CodeBlock>
        },
        /* Link eksternal: aman + buka tab baru. */
        a({ href, children, ...props }) {
          const isExternal = /^https?:\/\//i.test(href || '')
          return (
            <a
              href={href}
              {...props}
              {...(isExternal ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            >
              {children}
            </a>
          )
        },
        /* Tabel dibungkus agar bisa di-scroll horizontal di mobile. */
        table({ children }) {
          return (
            <div className="md-table-wrap">
              <table>{children}</table>
            </div>
          )
        },
      }}
    >
      {teks}
    </ReactMarkdown>
  )

  if (!adaSitasi) {
    return <div className="markdown">{renderer(safeContent, 'utuh')}</div>
  }

  return (
    <div className="markdown">
      {segmen.map((s, i) =>
        s.jenis === 'sitasi' ? (
          <ChipSitasi key={`s${i}`} nomor={s.nomor} daftar={sumber} />
        ) : (
          renderer(s.isi, `t${i}`)
        ),
      )}
    </div>
  )
}

export default memo(Markdown)
