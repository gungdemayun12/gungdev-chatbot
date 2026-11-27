/**
 * Logo.jsx — lambang GungDev (rubah) dalam dua bentuk pakai.
 *
 * Kenapa perlu pembungkus, bukan <img> langsung di tiap tempat:
 *   1. Logo asli berwarna oranye dengan garis hampir hitam. Di tema
 *      gelap garis itu bisa menyatu dengan latar, jadi di tempat kecil
 *      logo diberi "ubin" terang (bukan latar gelap) supaya tetap jelas.
 *   2. Ukuran dikunci lewat CSS (bukan atribut width/height saja), jadi
 *      logo tidak gepeng dan tata letak tidak bergeser saat gambar
 *      selesai dimuat.
 *
 * Berkas gambar dibuat dari logo asli oleh _buat_ikon.py — bentuk
 * rubahnya tidak digambar ulang.
 */

/** Lambang rubah polos (latar transparan). */
export function LogoGungDev({ ukuran = 28, className = '', alt = '' }) {
  return (
    <span
      className={`logo-gungdev ${className}`}
      style={{ '--logo-ukuran': `${ukuran}px` }}
    >
      <img
        src="/logo-192.png"
        srcSet="/logo-192.png 1x, /logo-512.png 2x"
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
