import { describe, expect, it } from 'vitest'
import {
  isStreamPhase,
  isTimeoutError,
  phaseI18nKey,
  phaseIndex,
  STREAM_PHASES,
} from '@/composables/chatStreamPhases'

describe('chatStreamPhases', () => {
  it('lists phases in pipeline order', () => {
    expect(STREAM_PHASES).toEqual([
      'loading_evidence',
      'building_prompt',
      'generating',
      'post_processing',
    ])
  })

  it('maps phases to i18n keys', () => {
    expect(phaseI18nKey('loading_evidence')).toBe('app.stream_loading_evidence')
    expect(phaseI18nKey('generating')).toBe('app.stream_generating')
    expect(phaseI18nKey('unknown')).toBe('app.in_progress')
  })

  it('validates stream phases', () => {
    expect(isStreamPhase('building_prompt')).toBe(true)
    expect(isStreamPhase('done')).toBe(false)
  })

  it('returns phase index', () => {
    expect(phaseIndex('generating')).toBe(2)
    expect(phaseIndex(null)).toBe(-1)
  })

  it('detects timeout errors', () => {
    expect(isTimeoutError('request timed out')).toBe(true)
    expect(isTimeoutError('network error')).toBe(false)
  })
})
