/**
 * Logo.jsx — lambang GungDev (rubah).
 *
 * Kenapa memakai berkas 64px, bukan berkas besar:
 *   Rubah pada logo ini tinggi dan sempit, sehingga di kotak kecil garis
 *   tepinya hanya selebar 2-3 piksel. Bila gambar 512px diperkecil
 *   langsung ke 26px oleh browser, garis lurus di sisi kiri berubah
 *   menjadi kabur dan terlihat seperti bekas potongan. Berkas 64px sudah
 *   disusutkan bertahap oleh _buat_ikon.py, jadi tepinya tetap lurus.
 *   Berkas 512px hanya dipakai untuk layar beresolusi tinggi (2x).
 */
export function LogoGungDev({ ukuran = 28, className = '', alt = '' }) {
  return (
    <span
      className={`logo-gungdev ${className}`}
      style={{ '--logo-ukuran': `${ukuran}px` }}
    >
      <img
        src="/logo-64.png"
        srcSet="/logo-64.png 1x, /logo-512.png 2x"
        width={ukuran}
        height={ukuran}
        alt={alt}
        aria-hidden={alt ? undefined : 'true'}
        draggable="false"
        decoding="async"
        className="logo-gungdev__img"
      />
    </span>
  )
}

export default LogoGungDev
