/**
 * Logo.jsx — lambang GungDev.
 *
 * Memakai berkas aslinya langsung: public/logo.jpeg. Gambar tidak
 * diolah, tidak dipotong, dan tidak diperkecil lebih dulu — browser
 * yang menyesuaikan ukurannya. Latar gambarnya putih, jadi di tema
 * gelap pun rubahnya tetap terlihat utuh.
 *
 * Ukuran dikunci lewat CSS (`--logo-ukuran`), dan `object-fit: contain`
 * menjaga bentuk aslinya supaya tidak gepeng di layar mana pun.
 */
export function LogoGungDev({ ukuran = 28, className = '', alt = '' }) {
  return (
    <span
      className={`logo-gungdev ${className}`}
      style={{ '--logo-ukuran': `${ukuran}px` }}
    >
      <img
        src="/logo.jpeg"
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
