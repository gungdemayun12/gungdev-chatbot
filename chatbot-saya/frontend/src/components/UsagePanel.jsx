/**
 * UsagePanel.jsx — panel pemakaian & jatah harian milik akun sendiri.
 *
 * Prinsip desain:
 *   1. HANYA JATAH AKUN — pengguna melihat bagiannya sendiri (berapa
 *      pesan terpakai, sisa, kapan pulih). Kapasitas layanan secara
 *      keseluruhan adalah urusan pemilik situs dan tidak ditampilkan.
 *   2. TENANG — jatah bukan hal yang perlu dicemaskan pengguna biasa.
 *      Warna hanya berubah saat benar-benar mendekati batas.
 *   3. TIDAK MENGHABISKAN KUOTA — panel ini hanya membaca /usage,
 *      tidak memanggil model AI sama sekali.
 *
 * Tampilan mengikuti gaya yang sudah ada (token warna, radius, font)
 * agar tidak terasa seperti komponen tempelan.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Modal from './Modal.jsx'
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
 * Format KHUSUS hitung mundur: selalu menampilkan DETIK sehingga angka
 * benar-benar berdetak setiap detik (jam:menit:detik).
 *
 * Contoh: 86399 -> "23:59:59", 900 -> "15:00", 45 -> "0:45".
 * Dipakai di blok hitung mundur, bukan di teks biasa — di teks biasa
 * "23 jam 59 menit" lebih enak dibaca.
 */
function durasiDetik(detik) {
  const d = Math.max(0, Math.round(Number(detik) || 0))
  const jam = Math.floor(d / 3600)
  const menit = Math.floor((d % 3600) / 60)
  const sisa = d % 60
  const duaAngka = (n) => String(n).padStart(2, '0')
  if (jam > 0) return `${jam}:${duaAngka(menit)}:${duaAngka(sisa)}`
  return `${menit}:${duaAngka(sisa)}`
}

/** Warna bar berdasarkan persen terpakai. */
function warnaBar(persen) {
  if (persen >= 90) return 'is-danger'
  if (persen >= 70) return 'is-warning'
  return ''
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

  /* Hitung mundur BERDETAK PER DETIK. Saat habis, data diambil ulang
     supaya jatah yang baru pulih langsung tampil. */
  const sisaDetik = useHitungMundur(akun?.reset, ambil)

  return (
    <div className="usage">
      {!apiOnline && (
        <div className="usage__notice is-danger">
          Server tidak terhubung. Angka di bawah mungkin sudah usang.
        </div>
      )}

      {memuat && !data && (
        <div className="usage__loading">
          <RefreshCw size={16} className="spin" />
          <span>Memuat data pemakaian…</span>
        </div>
      )}

      {galat && !memuat && (
        <div className="usage__notice is-danger">
          Data pemakaian belum bisa diambil. Coba lagi sebentar lagi.
        </div>
      )}

      {data && (
        <>
          {/* --- Ringkasan jatah akun --- */}
          <div className="usage__hero">
            <div className="usage__hero-icon">
              <Activity size={18} />
            </div>
            <div className="usage__hero-text">
              <div className="usage__hero-title">Jatah saya</div>
              <div className="usage__hero-sub">
                {akun ? (
                  <>
                    {akun.habis ? (
                      <>Pulih dalam <strong>{durasi(sisaDetik)}</strong></>
                    ) : (
                      <>
                        Sisa <strong>{angkaRingkas(akun.requests?.sisa || 0)}</strong>{' '}
                        pesan
                        {sisaDetik > 0 && (
                          <> · pulih dalam <strong>{durasi(sisaDetik)}</strong></>
                        )}
                      </>
                    )}
                  </>
                ) : (
                  <>Mode tamu</>
                )}
              </div>
            </div>
          </div>

          {/* --- Pemakaian akun ini sendiri ---
               Satu-satunya angka jatah yang perlu diketahui pengguna.
               Bila habis, chat ditolak sampai jendelanya berakhir, jadi
               angkanya harus terlihat jelas — bukan tersembunyi. */}
          {akun && (
            <div className="usage__akun">
              <div className="usage__akun-head">
                <span className="usage__akun-label">Pemakaian saya</span>
                <span className="usage__akun-total">
                  {angkaRingkas(akun.requests?.terpakai || 0)}
                  <span className="usage__akun-sep"> / </span>
                  {angkaRingkas(akun.requests?.batas || 0)} pesan
                </span>
              </div>

              <div
                className={`usage-bar__track usage__akun-track ${warnaBar(
                  akun.requests?.persen ?? 0,
                )}`}
                role="progressbar"
                aria-valuenow={Math.round(akun.requests?.persen ?? 0)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Jatah pesan akun ini: ${akun.requests?.persen ?? 0}% terpakai`}
              >
                <div
                  className="usage-bar__fill"
                  style={{
                    width: `${Math.max(
                      akun.requests?.persen ?? 0,
                      (akun.requests?.terpakai || 0) > 0 ? 1.5 : 0,
                    )}%`,
                  }}
                />
              </div>

              <div className="usage__akun-note">
                Sisa <strong>{angkaRingkas(akun.requests?.sisa || 0)}</strong> pesan
                pada jendela ini
                {sisaDetik > 0 && (
                  <> · pulih dalam {durasi(sisaDetik)}</>
                )}
                {(akun.tokens?.terpakai || 0) > 0 && (
                  <>
                    <span className="usage__akun-sep">·</span>
                    {angkaRingkas(akun.tokens.terpakai)} token terpakai
                  </>
                )}
              </div>

              {/* Hitung mundur RESET — berdetak tiap detik (real time),
                  dihitung di browser sehingga tidak memakai kuota. */}
              {akun.reset?.bergulir && sisaDetik > 0 && (
                <div className="usage__hitung" aria-live="polite">
                  <span className="usage__hitung-label">Jatah pulih dalam</span>
                  <span className="usage__hitung-nilai" data-uji="hitung">
                    {durasiDetik(sisaDetik)}
                  </span>
                  {akun.reset?.waktu_utc && (
                    <span className="usage__hitung-jam">
                      ({new Date(akun.reset.waktu_utc).toLocaleString('id-ID', {
                        hour: '2-digit',
                        minute: '2-digit',
                        day: 'numeric',
                        month: 'short',
                      })})
                    </span>
                  )}
                </div>
              )}

              {akun.reset?.bergulir && (
                <div className="usage__akun-jendela">
                  Jendela {Math.round(akun.reset.jendela_jam || 24)} jam milik akun
                  Anda dimulai saat pesan pertama, lalu jatah kembali penuh.
                  {akun.requests?.terpakai === 0 && (
                    <> Jendela baru dimulai saat Anda mengirim pesan.</>
                  )}
                </div>
              )}

              {akun.requests?.dikurangi && (
                <div className="usage__akun-jendela">
                  Layanan sedang ramai, jadi jatah hari ini sementara lebih
                  kecil ({angkaRingkas(akun.requests?.batas || 0)} dari biasanya{' '}
                  {angkaRingkas(jatahPenuh)} pesan). Jatah kembali normal otomatis.
                </div>
              )}

              {akun.habis && (
                <div className="usage__akun-habis">
                  Jatah Anda habis. Chat bisa dipakai lagi saat jendela ini
                  berakhir
                  {sisaDetik > 0 && <> (dalam {durasi(sisaDetik)})</>} —
                  riwayat lama tetap bisa dibaca.
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
                Masuk dengan Google untuk mendapat jatah{' '}
                <strong>
                  {angkaRingkas(data.tamu.jatah_akun || jatahPenuh)} pesan per
                  jendela 24 jam
                </strong>{' '}
                milik akun Anda sendiri.
              </div>
            </div>
          )}

          {hampirHabis && !akun?.habis && (
            <div className="usage__notice is-warning">
              Jatah Anda hampir habis. Jatah pulih otomatis saat jendela
              24 jam Anda berakhir.
            </div>
          )}

          {/* --- Penjelasan jujur, tanpa membuka kapasitas layanan --- */}
          <p className="usage__fineprint">
            Jatah <strong>Pemakaian saya</strong> adalah milik akun Anda sendiri
            ({angkaRingkas(akun?.requests?.batas || jatahPenuh)} pesan per jendela{' '}
            {Math.round(akun?.reset?.jendela_jam || 24)} jam) dan terpisah dari akun
            lain. Jendelanya dimulai saat pesan pertama Anda, dan jatah kembali
            penuh saat jendela itu berakhir — jadi waktu pulih tiap akun berbeda.
            Bila jatah tidak habis, Anda tidak pernah dibatasi. Setiap pesan
            dihitung sama, baik jawabannya pendek maupun panjang. Panel ini tidak
            memakai jatah saat dibuka.
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
