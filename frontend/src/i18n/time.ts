import { i18n } from './index'

export function formatRelativeTime(isoText: string | null | undefined): string {
  const t = i18n.global.t
  if (!isoText) return t('common.time_na')
  const parsed = new Date(String(isoText))
  if (Number.isNaN(parsed.getTime())) return String(isoText)
  const minutes = Math.round((Date.now() - parsed.getTime()) / 60000)
  if (minutes < 1) return t('common.time_just_now')
  if (minutes < 60) return t('common.time_minutes_ago', { n: minutes })
  const hours = Math.round(minutes / 60)
  if (hours < 48) return t('common.time_hours_ago', { n: hours })
  return t('common.time_days_ago', { n: Math.round(hours / 24) })
}
