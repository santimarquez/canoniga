import { describe, expect, it } from 'vitest'
import { computeTutorialCardPosition } from '@/composables/tutorialCardPosition'

describe('computeTutorialCardPosition', () => {
  it('places the card above a wide bottom prompt without overlapping it', () => {
    const target = {
      left: 200,
      top: 640,
      right: 900,
      bottom: 760,
      width: 700,
      height: 120,
    }
    const card = { width: 420, height: 200 }
    const viewport = { width: 1200, height: 800 }

    const pos = computeTutorialCardPosition(target, card, viewport)
    expect(pos.top + card.height).toBeLessThanOrEqual(target.top - 8)
    expect(pos.left).toBeGreaterThanOrEqual(8)
    expect(pos.left + card.width).toBeLessThanOrEqual(viewport.width - 8)
  })

  it('places the card to the side when there is room beside a narrow target', () => {
    const target = {
      left: 40,
      top: 120,
      right: 200,
      bottom: 180,
      width: 160,
      height: 60,
    }
    const card = { width: 360, height: 180 }
    const viewport = { width: 1200, height: 800 }

    const pos = computeTutorialCardPosition(target, card, viewport)
    const overlapsHorizontally = !(pos.left + card.width <= target.left - 8 || pos.left >= target.right + 8)
    const overlapsVertically = !(pos.top + card.height <= target.top - 8 || pos.top >= target.bottom + 8)
    expect(overlapsHorizontally && overlapsVertically).toBe(false)
  })
})
