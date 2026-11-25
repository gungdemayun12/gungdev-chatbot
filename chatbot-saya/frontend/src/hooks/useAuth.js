/**
 * useAuth.js — status login Google untuk seluruh aplikasi.
 *
 * Menyimpan satu sumber kebenaran: siapa yang sedang login di
 * perangkat ini. Komponen lain hanya membaca `user` / `masuk`.
 */
import { useCallback, useMemo, useState } from 'react'
import {
  LOGIN_TERSEDIA,
  bacaSesiTersimpan,
  hapusSesi,
  inisial,
  simpanSesi,
} from '../lib/auth.js'

export function useAuth() {
  const [user, setUser] = useState(() => bacaSesiTersimpan())

  /** Dipanggil setelah Google berhasil memberikan identitas. */
  const masukSebagai = useCallback((akun) => {
    simpanSesi(akun)
    setUser(akun)
  }, [])

  const keluar = useCallback(() => {
    hapusSesi()
    setUser(null)
  }, [])

  const nilai = useMemo(
    () => ({
      user,
      masuk: Boolean(user),
      tersedia: LOGIN_TERSEDIA,
      inisialNama: user ? inisial(user.name) : 'G',
    }),
    [user],
  )

  return { ...nilai, masukSebagai, keluar }
}
