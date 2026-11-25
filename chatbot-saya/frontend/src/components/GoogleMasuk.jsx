/**
 * GoogleMasuk.jsx — tombol "Masuk dengan Google".
 *
 * Memakai Google Identity Services langsung dari browser (tanpa backend,
 * tanpa menyimpan apa pun di server). Bila Client ID belum diisi di
 * environment, tombol tetap tampil tapi memberi penjelasan — supaya
 * situs tidak terlihat rusak saat pemilik belum memasang konfigurasi.
 */
import { useRef, useState } from 'react'
import { LogIn } from './icons.jsx'
import { LOGIN_TERSEDIA, mulaiLoginGoogle } from '../lib/auth.js'

/** Logo "G" resmi Google (4 warna) — bentuk sederhana, bukan emoji. */
function LogoGoogle({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  )
}

export default function GoogleMasuk({
  onAkun,
  onError,
  label = 'Masuk dengan Google',
  variant = 'primary', // 'primary' | 'ghost' | 'sidebar'
  fullWidth = false,
  disabled = false,
}) {
  const wadahRef = useRef(null)
  const [sibuk, setSibuk] = useState(false)

  const mulai = async () => {
    if (sibuk || disabled) return
    setSibuk(true)

    const batal = await mulaiLoginGoogle({
      wadah: wadahRef.current,
      onAkun: (akun) => {
        setSibuk(false)
        onAkun?.(akun)
      },
      onError: (pesan) => {
        setSibuk(false)
        onError?.(pesan)
      },
    })

    /* GIS merender tombol ke wadah, lalu kita klik. Delay kecil
       memberi waktu render selesai sebelum diklik. */
    const klik = () => {
      const tombol = wadahRef.current?.querySelector('div[role="button"], button')
      if (tombol) tombol.click()
      else {
        setSibuk(false)
        onError?.('Jendela login Google tidak bisa dibuka. Coba lagi.')
      }
      if (typeof batal === 'function') batal()
    }
    setTimeout(klik, 60)
  }

  if (!LOGIN_TERSEDIA) {
    return (
      <div className={`glogin glogin--${variant} ${fullWidth ? 'is-full' : ''}`}>
        <button
          type="button"
          className="glogin__btn is-off"
          onClick={() =>
            onError?.(
              'Login Google belum diaktifkan di situs ini. Pemilik situs perlu mengisi Client ID Google di pengaturan deploy.',
            )
          }
          title="Login Google belum dikonfigurasi"
        >
          <LogoGoogle />
          <span>{label}</span>
        </button>
      </div>
    )
  }

  return (
    <div className={`glogin glogin--${variant} ${fullWidth ? 'is-full' : ''}`}>
      <button
        type="button"
        className="glogin__btn"
        onClick={mulai}
        disabled={sibuk || disabled}
        aria-busy={sibuk}
      >
        {sibuk ? (
          <>
            <span className="glogin__spin" aria-hidden="true" />
            <span>Membuka Google…</span>
          </>
        ) : (
          <>
            <LogoGoogle />
            <span>{label}</span>
            <LogIn size={14} className="glogin__tail" aria-hidden="true" />
          </>
        )}
      </button>

      {/* Wadah tombol resmi Google: tidak terlihat mata & tidak bisa
          difokus keyboard, hanya dipakai untuk membuka jendela login. */}
      <div
        ref={wadahRef}
        className="glogin__gis"
        aria-hidden="true"
        tabIndex={-1}
      />
    </div>
  )
}
