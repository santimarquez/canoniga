import { i18n } from './index'

const formatters = new Map<string, Intl.NumberFormat>()

function getCompactFormatter(locale: string): Intl.NumberFormat {
  let formatter = formatters.get(locale)
  if (!formatter) {
    formatter = new Intl.NumberFormat(locale, {
      notation: 'compact',
      maximumFractionDigits: 1,
    })
    formatters.set(locale, formatter)
  }
  return formatter
}

export function formatCompactCount(value: number | null | undefined, locale?: string): string {
  const count = Number(value ?? 0)
  if (!Number.isFinite(count) || count < 0) return '0'
  const resolvedLocale = locale ?? String((i18n.global.locale as { value: string }).value || 'en')
  if (count < 1000) return String(Math.round(count))
  return getCompactFormatter(resolvedLocale).format(count)
}
