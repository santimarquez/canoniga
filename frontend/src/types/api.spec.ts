import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS } from '@/types/api'

describe('DEFAULT_FILTERS', () => {
  it('matches legacy investigator defaults', () => {
    expect(DEFAULT_FILTERS.evidence_types).toEqual(['observational', 'interventional'])
    expect(DEFAULT_FILTERS.min_reliability).toBe(0.6)
    expect(DEFAULT_FILTERS.highlight_contradictions).toBe(true)
    expect(DEFAULT_FILTERS.date_window).toBe('all')
  })
})
