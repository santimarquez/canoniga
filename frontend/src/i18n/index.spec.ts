import { describe, expect, it } from 'vitest'
import { i18n } from '@/i18n'
import { formatCooldownRemaining, formatRelativeTime } from '@/i18n/time'

describe('i18n message compiler', () => {
  it('renders email placeholders containing @ without syntax errors', () => {
    const text = i18n.global.t('login.email_placeholder')
    expect(text).toBe('name@university.edu')
  })

  it('interpolates named placeholders', () => {
    const text = i18n.global.t('login.sent_smtp', { email: 'user@example.com' })
    expect(text).toBe('We sent a secure sign-in link to user@example.com.')
  })

  it('renders time strings with braces adjacent to letters', () => {
    const text = i18n.global.t('common.time_minutes_ago', { n: 5 })
    expect(text).toBe('5m ago')
  })

  it('interpolates login last-updated label with relative time', () => {
    const text = i18n.global.t('login.db_last_updated', { time: '5m ago' })
    expect(text).toBe('Last Updated: 5m ago')
  })

  it('resolves app-prefixed investigator labels', () => {
    expect(i18n.global.t('app.nav_assistant')).toBe('Assistant')
    expect(i18n.global.t('app.filter_title')).toBe('Evidence Filters')
  })

  it('resolves session action labels', () => {
    expect(i18n.global.t('app.save_session')).toBe('Save session')
    expect(i18n.global.t('app.export_summary')).toBe('Export summary')
    expect(i18n.global.t('app.copy_citations')).toBe('Copy citations')
    expect(i18n.global.t('app.citations_copied')).toBe('Citations copied to clipboard.')
    expect(i18n.global.t('app.session_saved')).toBe('Session saved to database.')
  })
})

describe('formatCooldownRemaining', () => {
  it('rounds up to minutes without seconds', () => {
    expect(formatCooldownRemaining(45)).toBe('1m')
    expect(formatCooldownRemaining(3600)).toBe('1h')
  })
})

describe('formatRelativeTime', () => {
  it('returns just now for recent timestamps', () => {
    const stamp = new Date(Date.now() - 30_000).toISOString()
    expect(formatRelativeTime(stamp)).toBe('just now')
  })
})
