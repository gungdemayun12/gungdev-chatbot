"""
lampiran.py — ekstraksi teks dari file & validasi gambar.

Dipakai backend untuk dua hal:

1. FILE (PDF, DOCX, XLSX, TXT, CSV, MD, JSON, kode, dsb.)
   Isinya diekstrak jadi TEKS di server, lalu disisipkan ke pesan.
   Karena hasilnya teks biasa, SEMUA model bisa "membaca" file —
   tidak perlu model khusus.

2. GAMBAR (JPG, PNG, WEBP)
   Tidak mungkin diubah jadi teks tanpa model vision. Karena itu
   gambar diteruskan apa adanya (base64) ke model yang memang
   multimodal. Fungsi di sini hanya memvalidasi format & ukuran.

Semua batas di bawah sengaja konservatif agar:
  - tidak melewati batas kuota token gratis (8.000 TPM),
  - tidak membuat respons Vercel kehabisan waktu,
  - tidak membebani memori fungsi serverless.
"""
from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------
# BATAS UKURAN
# ---------------------------------------------------------------------
# Ukuran file mentah maksimum yang diterima dari klien.
MAKS_FILE_BYTES = 4 * 1024 * 1024        # 4 MB per file
MAKS_TOTAL_BYTES = 8 * 1024 * 1024       # 8 MB total semua lampiran
MAKS_JUMLAH_FILE = 5                     # jumlah file per pesan

# Panjang teks hasil ekstraksi yang disisipkan ke percakapan.
MAKS_KARAKTER_PER_FILE = 24_000
MAKS_KARAKTER_TOTAL = 48_000

# Gambar: batas per gambar dan jumlahnya (batas Groq: 3 gambar, 20 MB).
MAKS_GAMBAR_BYTES = 4 * 1024 * 1024      # 4 MB setelah base64-decode
MAKS_JUMLAH_GAMBAR = 3
TIPE_GAMBAR = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


class LampiranError(ValueError):
    """Kesalahan yang pesannya aman ditampilkan ke pengguna."""


# ---------------------------------------------------------------------
# DETEKSI JENIS FILE
# ---------------------------------------------------------------------
# Ekstensi teks polos: langsung dibaca sebagai UTF-8.
EKSTENSI_TEKS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".xml", ".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx", ".py",
    ".java", ".c", ".h", ".cpp", ".cs", ".go", ".rs", ".rb", ".php", ".sql",
    ".sh", ".bash", ".env", ".ini", ".toml", ".conf", ".log", ".srt", ".tex",
}

NAMA_RAMAH = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".xlsx": "Excel",
    ".pptx": "PowerPoint",
}


def ekstensi(nama: str) -> str:
    """Mengambil ekstensi (huruf kecil, termasuk titik)."""
    nama = (nama or "").strip().lower()
    titik = nama.rfind(".")
    return nama[titik:] if titik != -1 else ""


def _bersihkan(teks: str) -> str:
    """Merapikan teks hasil ekstraksi: buang baris kosong berlebih."""
    teks = teks.replace("\r\n", "\n").replace("\r", "\n")
    teks = re.sub(r"[ \t]+\n", "\n", teks)
    teks = re.sub(r"\n{3,}", "\n\n", teks)
    return teks.strip()


def _potong(teks: str, batas: int) -> Tuple[str, bool]:
    """Memotong teks ke batas karakter. True bila terpotong."""
    if len(teks) <= batas:
        return teks, False
    return teks[:batas], True


# ---------------------------------------------------------------------
# EKSTRAKTOR PER JENIS FILE
# ---------------------------------------------------------------------
def _dari_pdf(data: bytes) -> str:
    """Mengekstrak teks dari PDF memakai pypdf."""
    try:
        from pypdf import PdfReader  # impor lokal: hemat memori saat tidak dipakai
    except ImportError as exc:  # pragma: no cover
        raise LampiranError(
            "Pembaca PDF belum tersedia di server. Simpan lampiran sebagai "
            "teks lalu kirim ulang, atau hubungi pemilik situs."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise LampiranError(
            "File PDF tidak dapat dibuka. Pastikan file tidak rusak atau "
            "terkunci kata sandi."
        ) from exc

    bagian: List[str] = []
    total = 0
    # Batasi jumlah halaman: PDF tebal menghasilkan teks sangat panjang
    # dan menghabiskan kuota token.
    for halaman in reader.pages[:60]:
        try:
            isi = halaman.extract_text() or ""
        except Exception:  # noqa: BLE001
            continue
        if isi.strip():
            bagian.append(isi)
            total += len(isi)
        if total >= MAKS_KARAKTER_PER_FILE:
            break

    teks = _bersihkan("\n\n".join(bagian))
    if not teks:
        raise LampiranError(
            "PDF ini tidak berisi teks yang bisa dibaca (kemungkinan hasil "
            "pindai/gambar). Coba lampirkan foto halamannya sebagai gambar."
        )
    return teks


def _teks_dari_zip_xml(data: bytes, pola: str) -> str:
    """
    Mengambil teks dari file Office (docx/xlsx/pptx) yang sebenarnya
    adalah arsip ZIP berisi XML.

    `pola` adalah regex untuk mencari isi tag <w:t> (Word) atau
    <t> (Excel/PowerPoint).
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise LampiranError(
            "File tidak dapat dibuka. Pastikan formatnya benar (bukan file "
            "lama .doc/.xls, yang harus disimpan ulang sebagai .docx/.xlsx)."
        ) from exc

    with zf:
        nama_nama = sorted(
            n for n in zf.namelist() if n.endswith(".xml") and n.startswith("word/")
        ) or sorted(
            n for n in zf.namelist()
            if n.endswith(".xml") and n.startswith(("xl/", "ppt/"))
        )
        if not nama_nama:
            raise LampiranError("File tidak berisi teks yang bisa dibaca.")

        kumpulan: List[str] = []
        for nama in nama_nama[:40]:
            try:
                isi = zf.read(nama).decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            # <w:p> = paragraf; ganti jadi baris baru agar rapi.
            isi = isi.replace("</w:p>", "\n")
            potongan = re.findall(pola, isi)
            if potongan:
                kumpulan.append(" ".join(potongan))
            if sum(len(x) for x in kumpulan) >= MAKS_KARAKTER_PER_FILE:
                break

    return _bersihkan("\n".join(kumpulan))


def _dari_docx(data: bytes) -> str:
    return _teks_dari_zip_xml(data, r"<w:t[^>]*>(.*?)</w:t>")


def _dari_xlsx(data: bytes) -> str:
    teks = _teks_dari_zip_xml(data, r"<t[^>]*>(.*?)</t>")
    if not teks:
        raise LampiranError("Spreadsheet ini tidak berisi teks yang bisa dibaca.")
    return teks


def _dari_pptx(data: bytes) -> str:
    return _teks_dari_zip_xml(data, r"<a:t[^>]*>(.*?)</a:t>")


def _dari_teks(data: bytes) -> str:
    # Coba UTF-8 dulu (paling umum), lalu cp1252 (Windows Indonesia).
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return _bersihkan(data.decode(enc))
        except UnicodeDecodeError:
            continue
    return _bersihkan(data.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------
# API PUBLIK
# ---------------------------------------------------------------------
def ekstrak_file(nama: str, data: bytes) -> Dict[str, object]:
    """
    Mengubah isi file menjadi teks.

    Mengembalikan:
        {"nama": str, "teks": str, "terpotong": bool, "jenis": str}

    Melempar LampiranError bila file tidak didukung / rusak.
    """
    if not data:
        raise LampiranError(f"File '{nama}' kosong.")

    if len(data) > MAKS_FILE_BYTES:
        batas_mb = MAKS_FILE_BYTES // (1024 * 1024)
        raise LampiranError(
            f"File '{nama}' terlalu besar (maksimal {batas_mb} MB)."
        )

    ext = ekstensi(nama)

    if ext == ".pdf":
        teks, jenis = _dari_pdf(data), "PDF"
    elif ext == ".docx":
        teks, jenis = _dari_docx(data), "Word"
    elif ext == ".xlsx":
        teks, jenis = _dari_xlsx(data), "Excel"
    elif ext == ".pptx":
        teks, jenis = _dari_pptx(data), "PowerPoint"
    elif ext in EKSTENSI_TEKS:
        teks, jenis = _dari_teks(data), "teks"
    else:
        # Format biner lain (zip, gambar, audio, dsb.) tidak bisa
        # diekstrak di server tanpa pustaka tambahan.
        raise LampiranError(
            f"Jenis file '{nama}' belum bisa dibaca. Yang didukung: "
            "PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, JSON, dan file kode teks. "
            "Untuk gambar, lampirkan langsung sebagai gambar (JPG/PNG)."
        )

    teks, terpotong = _potong(teks, MAKS_KARAKTER_PER_FILE)
    if not teks:
        raise LampiranError(f"Tidak ada teks yang bisa dibaca di '{nama}'.")

    return {"nama": nama, "teks": teks, "terpotong": terpotong, "jenis": jenis}


def validasi_gambar(daftar: Optional[List[str]]) -> List[str]:
    """
    Memeriksa daftar gambar (data URL base64) sebelum dikirim ke model.

    Menerima format:
        "data:image/png;base64,iVBORw0..."

    Mengembalikan daftar data URL yang sudah divalidasi (bentuk asli,
    siap dipakai sebagai `image_url` pada API OpenAI-compatible).

    Melempar LampiranError dengan pesan Bahasa Indonesia bila ada
    masalah, supaya pengguna tahu persis apa yang salah.
    """
    if not daftar:
        return []

    if len(daftar) > MAKS_JUMLAH_GAMBAR:
        raise LampiranError(
            f"Maksimal {MAKS_JUMLAH_GAMBAR} gambar per pesan. "
            f"Anda mengirim {len(daftar)}."
        )

    bersih: List[str] = []
    for i, item in enumerate(daftar, start=1):
        if not isinstance(item, str) or not item.strip():
            raise LampiranError(f"Gambar ke-{i} tidak valid.")
        item = item.strip()

        if not item.startswith("data:"):
            raise LampiranError(
                f"Gambar ke-{i} harus dikirim dalam format data URL base64."
            )

        try:
            header, b64 = item.split(",", 1)
        except ValueError as exc:
            raise LampiranError(f"Format gambar ke-{i} rusak.") from exc

        mime = header[5:].split(";")[0].lower().strip()
        if mime not in TIPE_GAMBAR:
            raise LampiranError(
                f"Format gambar ke-{i} tidak didukung ({mime or 'tidak dikenal'}). "
                "Gunakan JPG, PNG, atau WEBP."
            )
        if "base64" not in header.lower():
            raise LampiranError(f"Gambar ke-{i} harus di-encode base64.")

        try:
            mentah = base64.b64decode(b64, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise LampiranError(f"Gambar ke-{i} tidak dapat dibaca.") from exc

        if len(mentah) > MAKS_GAMBAR_BYTES:
            batas_mb = MAKS_GAMBAR_BYTES // (1024 * 1024)
            raise LampiranError(
                f"Gambar ke-{i} terlalu besar (maksimal {batas_mb} MB)."
            )

        bersih.append(item)

    return bersih


def susun_blok_lampiran(hasil: List[Dict[str, object]]) -> str:
    """
    Menyusun teks lampiran menjadi satu blok konteks untuk model.

    Bentuknya sengaja jelas dan berlabel agar model tahu ini isi file
    kiriman pengguna, bukan bagian dari pertanyaan.
    """
    if not hasil:
        return ""

    bagian: List[str] = []
    total = 0
    for item in hasil:
        teks = str(item["teks"])
        sisa = MAKS_KARAKTER_TOTAL - total
        if sisa <= 0:
            break
        teks, terpotong_total = _potong(teks, sisa)
        total += len(teks)

        catatan = []
        if item.get("terpotong") or terpotong_total:
            catatan.append("dipotong otomatis karena terlalu panjang")

        kepala = f'=== ISI FILE: "{item["nama"]}"'
        if item.get("jenis"):
            kepala += f' ({item["jenis"]})'
        kepala += " ==="
        if catatan:
            kepala += f" [{', '.join(catatan)}]"

        bagian.append(f"{kepala}\n{teks}\n=== AKHIR FILE ===")

    if not bagian:
        return ""

    return (
        "\n\n---\n"
        "Pengguna melampirkan file berikut. Baca dan gunakan isinya untuk "
        "menjawab pertanyaan berikutnya. Jangan mengarang bagian yang tidak "
        "ada di dalamnya; bila informasi tidak ditemukan, katakan demikian.\n\n"
        + "\n\n".join(bagian)
        + "\n---\n"
    )


def ringkas_untuk_log(hasil: List[Dict[str, object]]) -> str:
    """Ringkasan aman untuk log (tanpa isi file, hanya ukuran)."""
    if not hasil:
        return "-"
    return json.dumps(
        [{"nama": h["nama"], "jenis": h.get("jenis"), "panjang": len(str(h["teks"]))} for h in hasil],
        ensure_ascii=False,
    )
