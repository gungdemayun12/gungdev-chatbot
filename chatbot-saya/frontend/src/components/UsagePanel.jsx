/**
 * UsagePanel.jsx — panel pemakaian & jatah harian milik akun sendiri.
 *
 * Prinsip desain:
 *   1. HANYA JATAH AKUN — pengguna melihat bagiannya sendiri (berapa
 *      pesan terpakai, sisa, kapan pulih). Kapasitas layanan secara
 *      keseluruhan adalah urusan pemilik situs dan tidak ditampilkan.
 *   2. TENANG SEPERTI UANG BEKAL — jatah bukan hal yang perlu
 *      dicemaskan. Bahasanya sederhana, tidak menakut-nakuti, tidak
 *      berlebihan ("alay"), dan tidak menampilkan peringatan merah
 *      kecuali benar-benar habis.
 *   3. TIDAK MENGHABISKAN KUOTA — panel ini hanya membaca /usage,
 *      tidak memanggil model AI sama sekali.
 *
 * Tampilan mengikuti gaya yang sudah ada (token warna, radius, font)
 * agar tidak terasa seperti komponen tempelan.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Modal from './Modal.jsx'
import JatahBar from './JatahBar.jsx'
import { Activity, RefreshCw } from './icons.jsx'
import { getTokenRiwayat } from '../lib/riwayat.js'

/* ---------------- Bantuan format ---------------- */

/** 17500 -> "17.5 rb", 200000 -> "200 rb", 1000 -> "1.000" */
function angkaRingkas(n) {
  const v = Number(n) || 0
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1).replace('.0', '') + ' jt'
  if (v >= 10_000) return (v / 1000).toFixed(1).replace('.0', '') + ' rb'
  return v.toLocaleString('id-ID')
}

/** 25200 -> "7 jam", 900 -> "15 menit", 45 -> "45 detik" */
function durasi(detik) {
  const d = Math.max(0, Math.round(Number(detik) || 0))
  if (d >= 86400) {
    const hari = Math.floor(d / 86400)
    const sisaJam = Math.floor((d % 86400) / 3600)
    return sisaJam ? `${hari} hari ${sisaJam} jam` : `${hari} hari`
  }
  if (d >= 3600) {
    const jam = Math.floor(d / 3600)
    const menit = Math.floor((d % 3600) / 60)
    return menit ? `${jam} jam ${menit} menit` : `${jam} jam`
  }
  if (d >= 60) return `${Math.floor(d / 60)} menit`
  return `${d} detik`
}

/**
 * Menghitung mundur sampai jatah pulih, BERDETAK SETIAP DETIK.
 *
 * Kenapa perlu: server hanya dikirimi angka "sisa_detik" saat panel
 * mengambil data. Tanpa penghitung lokal, tulisan "pulih dalam 23 jam 59
 * menit" akan diam sampai data diambil ulang (30 detik kemudian) — terasa
 * tidak hidup dan tidak real time.
 *
 * Cara: simpan WAKTU BERAKHIR absolut (dari `reset.pada` bila ada, atau
 * `reset.detik` dihitung dari saat data diterima), lalu hitung selisihnya
 * sendiri tiap detik. Tidak ada permintaan tambahan ke server.
 *
 * Bila waktu berakhir habis, panggil `onHabis` SEKALI agar data diambil
 * ulang — jatah yang pulih langsung terlihat tanpa menunggu 30 detik.
 */
function useHitungMundur(reset, onHabis) {
  const [sisa, setSisa] = useState(() => Math.max(0, Number(reset?.detik) || 0))

  // Waktu berakhir absolut; dihitung ulang hanya bila data server berubah.
  const akhirRef = useRef(0)

  useEffect(() => {
    if (!reset) {
      akhirRef.current = 0
      return undefined
    }
    const sekarang = Date.now()
    // `pada` (detik epoch) paling akurat; `detik` jadi cadangan.
    const akhir = Number(reset.pada)
      ? Number(reset.pada) * 1000
      : sekarang + Math.max(0, Number(reset.detik) || 0)
    akhirRef.current = akhir

    const hitung = () => {
      const s = Math.max(0, Math.round((akhirRef.current - Date.now()) / 1000))
      setSisa((lama) => (lama === s ? lama : s))
      return s
    }

    hitung()
    const id = setInterval(() => {
      if (hitung() <= 0) {
        clearInterval(id)
        // Jatah sudah pulih: minta angka terbaru sekali.
        if (typeof onHabis === 'function') onHabis()
      }
    }, 1000)

    return () => clearInterval(id)
    // Sengaja bergantung pada NILAI waktu berakhirnya saja (bukan objek
    // `reset` yang selalu baru setiap pengambilan data). Dengan begitu
    // penghitung TIDAK diulang saat data disegarkan, sehingga angka detik
    // berdetak mulus tiap detik dan tidak "melompat" tiap 30 detik.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reset?.pada, reset?.detik, onHabis])

  return sisa
}

/* ---------------- Isi panel (dipakai modal & Pengaturan) ---------------- */
export function UsageContent({ apiUrl, apiOnline, aktif = true }) {
  const [data, setData] = useState(null)
  const [memuat, setMemuat] = useState(false)
  const [galat, setGalat] = useState(false)

  const ambil = useCallback(async () => {
    if (!apiUrl) return
    setMemuat(true)
    setGalat(false)
    try {
      // Token dikirim agar backend menyertakan pemakaian akun ini.
      const token = getTokenRiwayat()
      const res = await fetch(`${apiUrl.replace(/\/+$/, '')}/usage`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (!res.ok) throw new Error('HTTP ' + res.status)
      setData(await res.json())
    } catch {
      setGalat(true)
      setData(null)
    } finally {
      setMemuat(false)
    }
  }, [apiUrl])

  /* Muat saat aktif + segarkan tiap 30 detik.
     setState dipanggil di dalam promise (bukan langsung di body
     effect) agar tidak memicu render berantai. */
  useEffect(() => {
    if (!aktif) return undefined
    let batal = false
    const jalan = () => {
      if (batal) return
      ambil()
    }
    Promise.resolve().then(jalan)
    const id = setInterval(jalan, 30000)
    return () => {
      batal = true
      clearInterval(id)
    }
  }, [aktif, ambil])

  /* REAL TIME saat tab kembali aktif.
     Bila pengguna berpindah tab (atau meminimalkan browser) lalu kembali,
     angka jatah langsung disegarkan — tidak menunggu putaran 30 detik.
     Ini penting karena jatah bisa berubah dari perangkat lain. */
  useEffect(() => {
    if (!aktif) return undefined
    const saatTerlihat = () => {
      if (document.visibilityState === 'visible') ambil()
    }
    document.addEventListener('visibilitychange', saatTerlihat)
    window.addEventListener('focus', saatTerlihat)
    return () => {
      document.removeEventListener('visibilitychange', saatTerlihat)
      window.removeEventListener('focus', saatTerlihat)
    }
  }, [aktif, ambil])

  // Bagian "pemakaian saya" hanya ada bila backend mengenali akunnya.
  const akun = data?.akun || null
  const persenAkun = akun?.requests?.persen ?? 0
  const hampirHabis = persenAkun >= 90
  const jatahPenuh = data?.jatah_penuh || akun?.requests?.jatah_penuh || 0

  /* Judul ringkasan mengikuti jatah yang paling menipis.
     Dengan dua bilah (obrolan & gambar), kalimatnya tidak lagi cukup
     menyebut "jatah" saja — pengguna perlu tahu jatah mana yang hampir
     habis. Bila keduanya masih lega, kalimat tetap netral. */
  const persenGambar =
    akun?.gambar && akun.gambar.batas > 0
      ? Math.round(((akun.gambar.batas - akun.gambar.terpakai) / akun.gambar.batas) * 100)
      : 100
  const sisaPersenChat = Math.max(0, 100 - persenAkun)
  const menipisChat = sisaPersenChat <= 10
  const menipisGambar = persenGambar <= 10

  /* Hitung mundur BERDETAK PER DETIK. Saat habis, data diambil ulang
     supaya jatah yang baru pulih langsung tampil. */
  const sisaDetik = useHitungMundur(akun?.reset, ambil)

  /* Jatah gambar punya jendela waktunya SENDIRI (dihitung sejak gambar
     pertama, bukan sejak pesan pertama). Karena itu hitung mundurnya
     dipisah — memakai satu nilai untuk keduanya akan menampilkan waktu
     yang salah pada salah satunya. */
  const detikGambar = useHitungMundur(akun?.gambar?.reset, ambil)

  return (
    <div className="usage">
      {!apiOnline && (
        <div className="usage__notice is-danger">
          Server belum terhubung. Angka di bawah mungkin sudah tidak terbaru.
        </div>
      )}

      {memuat && !data && (
        <div className="usage__loading">
          <RefreshCw size={16} className="spin" />
          <span>Memuat jatah Anda…</span>
        </div>
      )}

      {galat && !memuat && (
        <div className="usage__notice is-danger">
          Jatah belum bisa dimuat saat ini. Coba lagi sebentar lagi, ya.
        </div>
      )}

      {data && (
        <>
          {/* --- Ringkasan jatah akun ---
               Diganti dari angka menjadi BILAH PERSEN, mengikuti contoh
               yang diminta: judul, "N% sisa", keterangan waktu reset, dan
               bilah. Angka pastinya tetap ada di baris keterangan kecil,
               jadi pengguna yang ingin hitungan tepat tidak kehilangan
               informasi. */}
          <div className="usage__hero">
            <div className="usage__hero-icon">
              <Activity size={18} />
            </div>
            <div className="usage__hero-text">
              <div className="usage__hero-title">Jatah saya</div>
              <div className="usage__hero-sub">
                {akun ? (
                  <>
                    {akun.requests?.sisa > 0 && !menipisChat ? (
                      <>Jatah Anda masih lega. Jatah kembali penuh otomatis dalam{' '}</>
                    ) : menipisChat ? (
                      <>Jatah obrolan tinggal sedikit · kembali penuh dalam{' '}</>
                    ) : (
                      <>Jatah obrolan sudah terpakai semua · kembali dalam{' '}</>
                    )}
                    <strong>{durasi(sisaDetik)}</strong>.
                  </>
                ) : (
                  <>Anda sedang memakai mode tamu</>
                )}
              </div>
            </div>
          </div>

          {/* --- Bilah jatah ---
               SATU bilah per jenis jatah. Chat dan gambar dipisah karena
               memang tidak saling mengurangi: membuat gambar tidak
               memotong jatah chat. Menggabungkannya akan menyesatkan. */}
          {akun && (
            <div className="usage__bars">
              <JatahBar
                judul="Batas obrolan"
                terpakai={akun.requests?.terpakai || 0}
                batas={akun.requests?.batas || 0}
                sisaDetik={sisaDetik}
                keterangan
                uji="jatah-chat"
              />

              {akun.gambar && (
                <JatahBar
                  judul="Batas gambar"
                  terpakai={akun.gambar.terpakai || 0}
                  batas={akun.gambar.batas || 0}
                  sisaDetik={detikGambar}
                  keterangan
                  uji="jatah-gambar"
                />
              )}
            </div>
          )}

          {/* --- Penjelasan tambahan ---
               Hanya muncul bila memang ada yang perlu dijelaskan. */}
          {akun && (
            <div className="usage__akun">
              {akun.reset?.bergulir && (
                <div className="usage__akun-note">
                  Jatah obrolan dan jatah gambar dihitung terpisah: membuat
                  gambar tidak mengurangi jatah obrolan Anda. Keduanya
                  berjalan sebagai bekal{' '}
                  {Math.round(akun.reset.jendela_jam || 24)} jam sejak pesan
                  pertama.
                  {akun.requests?.terpakai === 0 && (
                    <> Hitungannya baru mulai saat Anda mengirim pesan.</>
                  )}
                </div>
              )}

              {akun.gambar && akun.gambar.batas === 0 && (
                <div className="usage__akun-note">
                  Akun Anda belum mendapat jatah gambar. Masuk dengan Google
                  agar bisa membuat gambar.
                </div>
              )}

              {akun.gambar && akun.gambar.habis && (
                <div className="usage__akun-note">
                  Jatah gambar Anda sudah terpakai semua · kembali dalam{' '}
                  {durasi(detikGambar)}
                  {detikGambar <= 0 && 'sebentar lagi'}. Mengobrol tetap bisa
                  seperti biasa.
                </div>
              )}

              {akun.requests?.dikurangi && (
                <div className="usage__akun-note">
                  Hari ini jatah obrolannya sedikit lebih kecil karena sedang
                  banyak yang memakai —{' '}
                  {angkaRingkas(akun.requests?.batas || 0)} pesan (biasanya{' '}
                  {angkaRingkas(jatahPenuh)}). Kembali normal sendiri, tidak
                  perlu melakukan apa pun.
                </div>
              )}

              {akun.habis && (
                <div className="usage__akun-habis">
                  Jatah obrolan Anda sudah terpakai semua. Bisa chat lagi dalam{' '}
                  {durasi(sisaDetik)}
                  {sisaDetik <= 0 && 'sebentar lagi'} — sementara itu, percakapan
                  lama tetap bisa dibaca.
                </div>
              )}
            </div>
          )}

          {!akun && data.tamu && (
            <div className="usage__akun">
              <div className="usage__akun-head">
                <span className="usage__akun-label">Mode tamu</span>
                <span className="usage__akun-total">
                  {angkaRingkas(data.tamu.batas_pesan || 0)} pesan/hari
                </span>
              </div>
              <div className="usage__akun-note">
                Masuk dengan Google untuk mendapat{' '}
                <strong>
                  {angkaRingkas(data.tamu.jatah_akun || jatahPenuh)} pesan
                </strong>{' '}
                untuk akun Anda sendiri, dan riwayat tersimpan.
              </div>
            </div>
          )}

          {hampirHabis && !akun?.habis && (
            <div className="usage__notice is-warning">
              Jatah obrolan Anda tinggal sedikit. Tidak masalah — akan kembali
              sendiri dalam {durasi(sisaDetik)}.
            </div>
          )}

          {menipisGambar && !menipisChat && akun?.gambar && !akun.gambar.habis && (
            <div className="usage__notice is-warning">
              Jatah gambar Anda tinggal sedikit. Akan kembali sendiri dalam{' '}
              {durasi(detikGambar)}.
            </div>
          )}

          {/* --- Penjelasan jujur, tanpa membuka kapasitas layanan --- */}
          <p className="usage__fineprint">
            Angka ini hanya milik akun Anda (
            {angkaRingkas(akun?.requests?.batas || jatahPenuh)} pesan per{' '}
            {Math.round(akun?.reset?.jendela_jam || 24)} jam) dan tidak memengaruhi akun
            lain. Hitungannya mulai dari pesan pertama Anda, jadi waktu perbarui tiap
            akun berbeda. Setiap pesan dihitung sama, baik jawabannya panjang maupun
            pendek. Membuka panel ini tidak memakai jatah.
          </p>

          <button
            type="button"
            className="btn btn--ghost btn--sm usage__refresh"
            onClick={ambil}
            disabled={memuat}
          >
            <RefreshCw size={14} className={memuat ? 'spin' : ''} />
            {memuat ? 'Menyegarkan…' : 'Segarkan'}
          </button>
        </>
      )}
    </div>
  )
}

/* ---------------- Panel modal ---------------- */
export default function UsagePanel({ open, onClose, apiUrl, apiOnline }) {
  return (
    <Modal open={open} onClose={onClose} title="Jatah Saya" size="md">
      <UsageContent apiUrl={apiUrl} apiOnline={apiOnline} aktif={open} />
    </Modal>
  )
}
