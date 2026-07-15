const LOCALE_KEY = 'als_lang'
const LOCALE_COOKIE = 'als_lang'

export function normalizeLocale(value: string | null | undefined): 'en' | 'es' | null {
  if (!value) return null
  const token = value.trim().toLowerCase()
  if (token.startsWith('es')) return 'es'
  if (token.startsWith('en')) return 'en'
  return null
}

export function readStoredLocale(): 'en' | 'es' {
  if (typeof window === 'undefined') return 'en'
  const fromStorage = normalizeLocale(localStorage.getItem(LOCALE_KEY))
  if (fromStorage) return fromStorage
  const match = document.cookie.match(new RegExp(`(?:^|; )${LOCALE_COOKIE}=([^;]*)`))
  const fromCookie = normalizeLocale(match ? decodeURIComponent(match[1]) : null)
  if (fromCookie) return fromCookie
  const browser = normalizeLocale(navigator.language)
  return browser ?? 'en'
}

export function writeLocale(locale: 'en' | 'es') {
  if (typeof window === 'undefined') return
  localStorage.setItem(LOCALE_KEY, locale)
  document.cookie = `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`
}
