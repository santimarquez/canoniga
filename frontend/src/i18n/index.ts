import { createI18n, type MessageCompiler, type MessageContext } from 'vue-i18n'
import appEn from './locales/app_en.json'
import appEs from './locales/app_es.json'
import commonEn from './locales/common_en.json'
import commonEs from './locales/common_es.json'
import landingEn from './locales/landing_en.json'
import landingEs from './locales/landing_es.json'
import legalEn from './locales/legal_en.json'
import legalEs from './locales/legal_es.json'
import loginEn from './locales/login_en.json'
import loginEs from './locales/login_es.json'
import { readStoredLocale, writeLocale } from './locale'

function mergeBundles(...bundles: Record<string, string>[]) {
  return Object.assign({}, ...bundles)
}

function prefixKeys(bundle: Record<string, string>, prefix: string): Record<string, string> {
  return Object.fromEntries(Object.entries(bundle).map(([key, value]) => [`${prefix}.${key}`, value]))
}

function interpolateNamed(message: string, values: Record<string, unknown>): string {
  let text = message
  for (const [key, value] of Object.entries(values)) {
    text = text.split(`{${key}}`).join(String(value ?? ''))
  }
  return text
}

// Locale strings use Python-style `{name}` placeholders and may contain `@` or
// `{n}m ago` patterns that break vue-i18n's default ICU message compiler.
const simpleMessageCompiler: MessageCompiler = (message) => {
  const text = String(message)
  return (ctx: MessageContext) => {
    const values = ctx.values
    if (!values || typeof values !== 'object' || Array.isArray(values)) {
      return text
    }
    return interpolateNamed(text, values as Record<string, unknown>)
  }
}

export const i18n = createI18n({
  legacy: false,
  locale: readStoredLocale(),
  fallbackLocale: 'en',
  messageCompiler: simpleMessageCompiler,
  messages: {
    en: mergeBundles(commonEn, prefixKeys(appEn, 'app'), loginEn, landingEn, legalEn) as Record<string, string>,
    es: mergeBundles(commonEs, prefixKeys(appEs, 'app'), loginEs, landingEs, legalEs) as Record<string, string>,
  },
})

export function setAppLocale(locale: 'en' | 'es') {
  ;(i18n.global.locale as { value: string }).value = locale
  writeLocale(locale)
}

export function tf(key: string, vars?: Record<string, string | number>): string {
  let text = String(i18n.global.t(key))
  if (!vars) return text
  for (const [name, value] of Object.entries(vars)) {
    text = text.split(`{${name}}`).join(String(value))
  }
  return text
}
