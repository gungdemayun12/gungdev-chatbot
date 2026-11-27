/**
 * LoginModal.jsx — ajakan masuk dengan Google.
 *
 * Muncul dalam dua keadaan:
 *   1. `mode="batas"`  — tamu sudah memakai 3 pesan hari ini.
 *                        Ini blokir halus, bukan hukuman: pengguna
 *                        diberi tahu apa yang ia dapat setelah login.
 *   2. `mode="info"`   — dipanggil sendiri dari sidebar/tombol.
 */
import Modal from './Modal.jsx'
import GoogleMasuk from './GoogleMasuk.jsx'
import { BATAS_TAMU } from '../lib/guest.js'
import { BookOpen, Image, ShieldCheck, Sparkles, Telescope } from './icons.jsx'

const MANFAAT = [
  {
    icon: BookOpen,
    judul: 'Riwayat tersimpan',
    isi: 'Percakapan bisa dibuka lagi kapan saja — tidak hilang saat tab ditutup.',
  },
  {
    icon: Sparkles,
    judul: `Lebih dari ${BATAS_TAMU} pesan`,
    isi: 'Tanpa batas harian kecil yang berlaku untuk tamu.',
  },
  {
    icon: Image,
    judul: 'Gambar & file',
    isi: 'Baca gambar, PDF, DOCX, dan spreadsheet langsung dari kotak pesan.',
  },
  {
    icon: Telescope,
    judul: 'Riset web',
    isi: 'GungDev mencari dan membaca sumber di internet, otomatis untuk semua model.',
  },
  {
    icon: ShieldCheck,
    judul: 'Privat',
    isi: 'Riwayat hanya tersimpan di perangkat ini, tidak dikirim ke mana pun.',
  },
]

export default function LoginModal({
  open,
  mode = 'info',
  onClose,
  onAkun,
  onError,
}) {
  const batas = mode === 'batas'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={batas ? 'Batas tamu tercapai' : 'Masuk ke GungDev'}
      size="sm"
    >
      <div className="glogin-box">
        <span className={`glogin-box__badge ${batas ? 'is-warn' : ''}`} aria-hidden="true">
          <Sparkles size={18} />
        </span>

        <p className="glogin-box__lead">
          {batas ? (
            <>
              Anda sudah memakai <strong>{BATAS_TAMU} pesan gratis</strong> hari ini sebagai
              tamu. Masuk dengan Google untuk melanjutkan — gratis, tanpa kartu kredit.
            </>
          ) : (
            <>
              Masuk dengan Google agar riwayat percakapan tersimpan dan batas tamu harian
              terbuka. Gratis, tanpa kartu kredit.
            </>
          )}
        </p>

        <ul className="glogin-list">
          {MANFAAT.map((m) => {
            const Icon = m.icon
            return (
              <li key={m.judul} className="glogin-list__row">
                <span className="glogin-list__icon" aria-hidden="true">
                  <Icon size={15} />
                </span>
                <span className="glogin-list__text">
                  <span className="glogin-list__judul">{m.judul}</span>
                  <span className="glogin-list__isi">{m.isi}</span>
                </span>
              </li>
            )
          })}
        </ul>

        <GoogleMasuk
          onAkun={onAkun}
          onError={onError}
          fullWidth
          label="Masuk dengan Google"
        />

        <p className="glogin-box__note">
          Tanpa login Anda tetap bisa mencoba, tetapi riwayat percakapan tidak disimpan.
        </p>

        <button type="button" className="btn btn--ghost glogin-box__nanti" onClick={onClose}>
          {batas ? 'Nanti saja' : 'Tutup'}
        </button>
      </div>
    </Modal>
  )
}
