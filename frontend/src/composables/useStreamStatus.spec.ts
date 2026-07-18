import { describe, expect, it } from 'vitest'
import { phaseI18nKey } from '@/composables/chatStreamPhases'

describe('useStreamStatus phase mapping', () => {
  it('maps stream phases to i18n keys', () => {
    expect(phaseI18nKey('loading_evidence')).toBe('app.stream_loading_evidence')
    expect(phaseI18nKey('generating')).toBe('app.stream_generating')
  })
})
