/**
 * Sidebar.jsx — panel kiri: logo, tombol percakapan baru, pencarian,
 * riwayat terkelompok, dan footer pengguna.
 *
 * Satu sesi = satu item riwayat. Item aktif diberi highlight lembut.
 * Menu "..." pada tiap item: Ganti nama, Sematkan, Ekspor, Hapus.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronRight,
  Download,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Settings,
  Sparkles,
  Trash2,
} from './icons.jsx'
import { groupSessions } from '../lib/text.js'

/** Skeleton saat riwayat sedang "dimuat". */
function HistorySkeleton() {
  return (
    <div className="sb-skeleton" aria-hidden="true">
      {[68, 82, 56, 74, 62].map((w, i) => (
        <div key={i} className="sb-skeleton__row">
          <span className="sb-skeleton__dot" />
          <span className="sb-skeleton__bar" style={{ width: `${w}%` }} />
        </div>
      ))}
    </div>
  )
}

/** Satu item riwayat + menu kontekstual. */
function HistoryItem({ session, active, onSelect, onRename, onPin, onDelete, onExport }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const wrapRef = useRef(null)

  /* Tutup menu saat klik di luar. */
  useEffect(() => {
    if (!menuOpen) return
    const handler = (e) => {
      if (!wrapRef.current?.contains(e.target)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  return (
    <li className={`sb-item ${active ? 'is-active' : ''}`} ref={wrapRef}>
      <button
        type="button"
        className="sb-item__main"
        onClick={() => onSelect(session.id)}
        aria-current={active ? 'true' : undefined}
        title={session.title}
      >
        {session.pinned && (
          <Pin size={12} className="sb-item__pin" aria-label="Disematkan" />
        )}
        <span className="sb-item__title">{session.title}</span>
      </button>

      <button
        type="button"
        className="sb-item__more"
        onClick={() => setMenuOpen((v) => !v)}
        aria-label={`Menu untuk ${session.title}`}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
      >
        <MoreHorizontal size={16} />
      </button>

      {menuOpen && (
        <div className="sb-menu" role="menu">
          <button
            type="button"
            role="menuitem"
            className="sb-menu__item"
            onClick={() => {
              setMenuOpen(false)
              onRename(session)
            }}
          >
            <Pencil size={14} /> Ganti nama
          </button>
          <button
            type="button"
            role="menuitem"
            className="sb-menu__item"
            onClick={() => {
              setMenuOpen(false)
              onPin(session.id)
            }}
          >
            {session.pinned ? <PinOff size={14} /> : <Pin size={14} />}
            {session.pinned ? 'Lepas sematan' : 'Sematkan'}
          </button>
          <button
            type="button"
            role="menuitem"
            className="sb-menu__item"
            onClick={() => {
              setMenuOpen(false)
              onExport(session, 'md')
            }}
          >
            <Download size={14} /> Ekspor (.md)
          </button>
          <button
            type="button"
            role="menuitem"
            className="sb-menu__item"
            onClick={() => {
              setMenuOpen(false)
              onExport(session, 'txt')
            }}
          >
            <Download size={14} /> Ekspor (.txt)
          </button>
          <div className="sb-menu__sep" />
          <button
            type="button"
            role="menuitem"
            className="sb-menu__item sb-menu__item--danger"
            onClick={() => {
              setMenuOpen(false)
              onDelete(session)
            }}
          >
            <Trash2 size={14} /> Hapus
          </button>
        </div>
      )}
    </li>
  )
}

export default function Sidebar({
  open,
  collapsed,
  onToggleCollapse,
  onClose,
  onCloseMobile,
  sessions,
  activeId,
  loaded,
  nickname,
  onNewChat,
  onSelect,
  onRename,
  onPin,
  onDelete,
  onExport,
  onOpenSettings,
}) {
  const [query, setQuery] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState({})
  const searchRef = useRef(null)

  /* Swipe ke kiri untuk menutup drawer di mobile. */
  const touchRef = useRef({ x: 0, y: 0, active: false })

  const onTouchStart = (e) => {
    const t = e.touches[0]
    touchRef.current = { x: t.clientX, y: t.clientY, active: true }
  }

  const onTouchEnd = (e) => {
    const st = touchRef.current
    if (!st.active) return
    st.active = false
    const t = e.changedTouches[0]
    const dx = t.clientX - st.x
    const dy = Math.abs(t.clientY - st.y)
    /* Geser kiri > 60px dan horizontal (bukan scroll vertikal) => tutup. */
    if (dx < -60 && dy < 70) onClose()
  }

  /* Filter sederhana berdasarkan judul + isi pesan pertama. */
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return sessions
    return sessions.filter((s) => {
      if (s.title.toLowerCase().includes(q)) return true
      return s.messages.some((m) => (m.content || '').toLowerCase().includes(q))
    })
  }, [sessions, query])

  const groups = useMemo(() => groupSessions(filtered), [filtered])

  /* Fokus ke pencarian saat Ctrl+K ditekan (ditangani di App). */
  useEffect(() => {
    if (!open) return
    const handler = () => searchRef.current?.focus()
    window.addEventListener('gungdev:focus-search', handler)
    return () => window.removeEventListener('gungdev:focus-search', handler)
  }, [open])

  const toggleGroup = (key) =>
    setCollapsedGroups((prev) => ({ ...prev, [key]: !prev[key] }))

  return (
    <>
      {/* Overlay gelap di mobile */}
      <div
        className={`sb-overlay ${open ? 'is-visible' : ''}`}
        onClick={onCloseMobile}
        aria-hidden="true"
      />

      <aside
        className={`sidebar ${open ? 'is-open' : ''} ${collapsed ? 'is-collapsed' : ''}`}
        aria-label="Panel navigasi"
        data-collapsed={collapsed ? 'true' : 'false'}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        {/* Header: logo + nama + tombol collapse */}
        <div className="sb-header">
          <button
            type="button"
            className="sb-brand"
            onClick={onNewChat}
            aria-label="GungDev — mulai percakapan baru"
            title="GungDev"
          >
            <span className="sb-brand__mark" aria-hidden="true">
              <Sparkles size={15} />
            </span>
            <span className="sb-brand__name">GungDev</span>
          </button>

          <button
            type="button"
            className="icon-btn sb-collapse"
            onClick={onToggleCollapse}
            aria-label={collapsed ? 'Perluas sidebar' : 'Ciutkan sidebar'}
            title={collapsed ? 'Perluas (Ctrl+B)' : 'Ciutkan (Ctrl+B)'}
          >
            <PanelLeftClose size={17} />
          </button>

          <button
            type="button"
            className="icon-btn sb-mobile-close"
            onClick={onClose}
            aria-label="Tutup sidebar"
          >
            <ChevronRight size={18} className="sb-mobile-close__icon" />
          </button>        </div>

        {/* Tombol percakapan baru (gaya subtle) */}
        <div className="sb-new-wrap">
          <button type="button" className="sb-new" onClick={onNewChat} title="Percakapan baru (Ctrl+Shift+O)">
            <Plus size={16} aria-hidden="true" />
            <span className="sb-new__label">Percakapan Baru</span>
          </button>
        </div>

        {/* Pencarian */}
        <div className="sb-search">
          <Search size={15} className="sb-search__icon" aria-hidden="true" />
          <label htmlFor="sb-search-input" className="sr-only">
            Cari percakapan
          </label>
          <input
            id="sb-search-input"
            ref={searchRef}
            type="search"
            className="sb-search__input"
            placeholder="Cari percakapan…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className="sb-search__kbd" aria-hidden="true">
            Ctrl K
          </kbd>
        </div>

        {/* Daftar riwayat */}
        <nav className="sb-history" aria-label="Riwayat percakapan">
          {!loaded ? (
            <HistorySkeleton />
          ) : groups.length === 0 ? (
            <p className="sb-empty">
              {query ? 'Tidak ada percakapan yang cocok.' : 'Belum ada percakapan.'}
            </p>
          ) : (
            groups.map((group) => (
              <section key={group.key} className="sb-group">
                <button
                  type="button"
                  className="sb-group__head"
                  onClick={() => toggleGroup(group.key)}
                  aria-expanded={!collapsedGroups[group.key]}
                >
                  <ChevronRight
                    size={12}
                    className={`sb-group__chev ${collapsedGroups[group.key] ? '' : 'is-open'}`}
                    aria-hidden="true"
                  />
                  <span>{group.label}</span>
                </button>
                {!collapsedGroups[group.key] && (
                  <ul className="sb-list">
                    {group.items.map((s) => (
                      <HistoryItem
                        key={s.id}
                        session={s}
                        active={s.id === activeId}
                        onSelect={(id) => {
                          onSelect(id)
                          onCloseMobile?.()
                        }}
                        onRename={onRename}
                        onPin={onPin}
                        onDelete={onDelete}
                        onExport={onExport}
                      />
                    ))}
                  </ul>
                )}
              </section>
            ))
          )}
        </nav>

        {/* Footer: profil + pengaturan */}
        <div className="sb-footer">
          <div className="sb-profile">
            <span className="sb-avatar" aria-hidden="true">
              {(nickname || 'K').charAt(0).toUpperCase()}
            </span>
            <span className="sb-profile__name">{nickname || 'Kamu'}</span>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onOpenSettings}
            aria-label="Buka pengaturan"
            title="Pengaturan"
          >
            <Settings size={17} />
          </button>
        </div>
      </aside>
    </>
  )
}
