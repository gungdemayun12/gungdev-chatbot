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
import { useCallback, useEffect, useState } from 'react'
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

/** Warna bar berdasarkan persen terpakai. */
function warnaBar(persen) {
  if (persen >= 90) return 'is-danger'
  if (persen >= 70) return 'is-warning'
  return ''
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

  // Bagian "pemakaian saya" hanya ada bila backend mengenali akunnya.
  const akun = data?.akun || null
  const persenAkun = akun?.requests?.persen ?? 0
  const hampirHabis = persenAkun >= 90
  const jatahPenuh = data?.jatah_penuh || akun?.requests?.jatah_penuh || 0

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
                      <>Pulih dalam <strong>{durasi(akun.reset?.detik)}</strong></>
                    ) : (
                      <>
                        Sisa <strong>{angkaRingkas(akun.requests?.sisa || 0)}</strong>{' '}
                        pesan
                        {akun.reset?.detik > 0 && (
                          <> · pulih dalam <strong>{durasi(akun.reset.detik)}</strong></>
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
                {akun.reset?.detik > 0 && (
                  <> · pulih dalam {durasi(akun.reset.detik)}</>
                )}
                {(akun.tokens?.terpakai || 0) > 0 && (
                  <>
                    <span className="usage__akun-sep">·</span>
                    {angkaRingkas(akun.tokens.terpakai)} token terpakai
                  </>
                )}
              </div>

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
                  {akun.reset?.detik > 0 && <> (dalam {durasi(akun.reset.detik)})</>} —
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
