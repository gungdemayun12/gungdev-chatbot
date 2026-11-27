/**
 * EmptyState.jsx â€” tampilan saat percakapan masih kosong.
 * Sapaan besar bergaya serif sesuai waktu + kartu saran prompt.
 */
import { Bug, Lightbulb, AlignLeft, BookOpen } from './icons.jsx'
import LogoGungDev from './Logo.jsx'

/** Sapaan sesuai jam lokal. */
function greeting(date = new Date()) {
  const h = date.getHours()
  if (h >= 4 && h < 11) return 'Selamat pagi'
  if (h >= 11 && h < 15) return 'Selamat siang'
  if (h >= 15 && h < 19) return 'Selamat sore'
  return 'Selamat malam'
}

const SUGGESTIONS = [
  {
    icon: Bug,
    title: 'Bantu saya debug kode',
    prompt:
      'Bantu saya debug kode berikut. Jelaskan penyebabnya dan berikan perbaikannya:\n\n```js\n// tempel kode kamu di sini\n```',
  },
  {
    icon: Lightbulb,
    title: 'Buatkan ide tulisan',
    prompt:
      'Buatkan 5 ide tulisan (artikel/blog) yang menarik tentang produktivitas untuk developer, lengkap dengan sudut pandang uniknya.',
  },
  {
    icon: BookOpen,
    title: 'Jelaskan konsep sulit',
    prompt:
      'Jelaskan konsep "event loop" di JavaScript dengan bahasa sederhana, analogi yang mudah dipahami, dan contoh singkat.',
  },
  {
    icon: AlignLeft,
    title: 'Ringkas teks ini',
    prompt:
      'Ringkas teks berikut menjadi 3 poin utama. Pertahankan angka dan nama penting:\n\nTempel teks kamu di siniâ€¦',
  },
]

export default function EmptyState({ nickname, onPick }) {
  const name = (nickname || '').trim()

  return (
    <div className="empty">
      <div className="empty__hero">
        <span className="empty__spark" aria-hidden="true">
          <LogoGungDev ukuran={54} />
        </span>
        <h1 className="empty__greeting">
          {greeting()}
          {name && name !== 'Kamu' ? `, ${name}` : ''}
        </h1>
        <p className="empty__sub">Ada yang bisa saya bantu hari ini?</p>
      </div>

      <div className="empty__grid" role="list">
        {SUGGESTIONS.map((s) => {
          const Icon = s.icon
          return (
            <button
              key={s.title}
              type="button"
              className="suggestion"
              role="listitem"
              onClick={() => onPick(s.prompt)}
            >
              <span className="suggestion__icon" aria-hidden="true">
                <Icon size={17} />
              </span>
              <span className="suggestion__title">{s.title}</span>
              <span className="suggestion__desc">{s.prompt.split('\n')[0]}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
