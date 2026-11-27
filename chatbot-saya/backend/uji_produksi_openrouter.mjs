/**
 * uji_produksi_openrouter.mjs — memverifikasi bahwa OpenRouter BENAR-BENAR
 * tersambung di produksi setelah Anda memasang OPENROUTER_API_KEY.
 *
 * Jalankan setelah redeploy:
 *
 *     node uji_produksi_openrouter.mjs
 *
 * Yang diperiksa:
 *   1. /diagnostik   -> penyedia aktif & apakah kunci terbaca
 *   2. /capabilities -> semua model bisa riset
 *   3. Chat per model -> benar-benar menjawab (bukan "Halo!")
 *   4. Riset web      -> menyisipkan sumber nyata
 *
 * Skrip ini TIDAK memakai API key apa pun: semua lewat backend Anda.
 */
const base = 'https://gungdev-chatbot-rq5l.vercel.app'

const KIRIM = async (body, path = '/chat', ms = 180000) => {
  const t0 = Date.now()
  const r = await fetch(base + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(ms),
  })
  const teks = await r.text()
  let isi = teks.slice(0, 220)
  try {
    const j = JSON.parse(teks)
    isi = j.reply ? String(j.reply).replace(/\s+/g, ' ') : JSON.stringify(j).slice(0, 220)
  } catch {
    /* bukan JSON */
  }
  return { status: r.status, ms: Date.now() - t0, isi, mentah: teks }
}

const MODEL = [
  'openai/gpt-oss-120b',
  'deepseek/deepseek-v4.1-flash',
  'google/gemini-3.1-flash-lite',
  'google/gemma-4-31b-it:free',
  'nvidia/nemotron-3.5-super-vl:free',
  'inclusionai/ling-3.2-flash:free',
]

let gagal = 0
const cek = (nama, ok, info = '') => {
  console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ` — ${info}` : ''}`)
  if (!ok) gagal += 1
}

console.log('=== 1. STATUS PENYEDIA ===')
const diag = await (await fetch(`${base}/diagnostik`)).json()
console.log(JSON.stringify(diag))
cek('Penyedia aktif = openrouter', diag.provider_aktif === 'openrouter', diag.provider_aktif)
cek('Kunci OpenRouter terbaca', diag.panjang_key_openrouter > 0, `panjang ${diag.panjang_key_openrouter}`)
cek('Bentuk kunci wajar', diag.format_key_openrouter === 'ok', diag.format_key_openrouter)
cek('Riwayat tersimpan di server', diag.penyimpanan_riwayat === true)
cek('Login terverifikasi', diag.verifikasi_login === true)

console.log('\n=== 2. SEMUA MODEL BISA RISET ===')
const caps = await (await fetch(`${base}/capabilities`)).json()
const tanpaRiset = caps.models.filter((m) => !m.browser)
cek('Tidak ada model tanpa riset', tanpaRiset.length === 0, `${caps.models.length} model`)

console.log('\n=== 3. CHAT PER MODEL (uji penalaran, bukan sapaan) ===')
for (const m of MODEL) {
  const h = await KIRIM({ message: 'Berapa hasil 17 x 23? Jawab angkanya saja.', model: m })
  const benar = /\b391\b/.test(h.isi)
  const generik = /halo|ada yang bisa saya bantu/i.test(h.isi)
  cek(`${m} menjawab benar`, h.status === 200 && benar && !generik, `${h.status} ${h.ms}ms ${h.isi.slice(0, 90)}`)
  await new Promise((r) => setTimeout(r, 1500))
}

console.log('\n=== 4. RISET WEB NYATA (model non-GPT-OSS) ===')
const riset = await KIRIM({
  message: 'Siapa presiden Indonesia saat ini? Sebutkan sumbernya.',
  model: 'deepseek/deepseek-v4.1-flash',
  research: true,
})
cek('Riset menjawab', riset.status === 200, `${riset.status} ${riset.ms}ms`)
cek('Menyebut sumber', /(wikipedia|http|\[\d\])/i.test(riset.isi), riset.isi.slice(0, 150))

console.log('\n=== 5. USAGE ===')
const usage = await (await fetch(`${base}/usage`)).json()
console.log(JSON.stringify({ requests: usage.requests, sumber: usage.sumber, provider: usage.provider }))

console.log(`\n${'='.repeat(60)}`)
console.log(gagal === 0 ? 'SEMUA LULUS — OpenRouter tersambung & semua model berfungsi.' : `ADA ${gagal} KEGAGALAN — lihat baris GAGAL di atas.`)
console.log('='.repeat(60))
process.exit(gagal === 0 ? 0 : 1)
