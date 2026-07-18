export interface RectLike {
  left: number
  top: number
  right: number
  bottom: number
  width: number
  height: number
}

export interface CardSize {
  width: number
  height: number
}

export interface ViewportSize {
  width: number
  height: number
}

export interface CardPosition {
  left: number
  top: number
}

function overlaps(a: RectLike, b: RectLike, gap = 0): boolean {
  return !(
    a.right + gap <= b.left ||
    a.left - gap >= b.right ||
    a.bottom + gap <= b.top ||
    a.top - gap >= b.bottom
  )
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/**
 * Place the tutorial helper card so it does not cover the highlighted target.
 * Prefers above / below for wide targets (e.g. the prompt), else left / right.
 */
export function computeTutorialCardPosition(
  target: RectLike,
  card: CardSize,
  viewport: ViewportSize,
  margin = 16,
  edge = 8,
): CardPosition {
  const maxLeft = Math.max(edge, viewport.width - card.width - edge)
  const maxTop = Math.max(edge, viewport.height - card.height - edge)

  const candidates: CardPosition[] = [
    // Above target (centered on target when possible)
    {
      left: clamp(target.left + target.width / 2 - card.width / 2, edge, maxLeft),
      top: clamp(target.top - card.height - margin, edge, maxTop),
    },
    // Below target
    {
      left: clamp(target.left + target.width / 2 - card.width / 2, edge, maxLeft),
      top: clamp(target.bottom + margin, edge, maxTop),
    },
    // Right of target
    {
      left: clamp(target.right + margin, edge, maxLeft),
      top: clamp(target.top, edge, maxTop),
    },
    // Left of target
    {
      left: clamp(target.left - card.width - margin, edge, maxLeft),
      top: clamp(target.top, edge, maxTop),
    },
    // Top of viewport, centered (fallback away from bottom composers)
    {
      left: clamp(viewport.width / 2 - card.width / 2, edge, maxLeft),
      top: edge,
    },
    // Bottom of viewport, centered
    {
      left: clamp(viewport.width / 2 - card.width / 2, edge, maxLeft),
      top: maxTop,
    },
  ]

  // Prefer stacking above/below for wide targets (prompt, report).
  const preferVertical = target.width > viewport.width * 0.45 || target.width > card.width
  const order = preferVertical ? [0, 1, 2, 3, 4, 5] : [2, 3, 0, 1, 4, 5]

  for (const index of order) {
    const pos = candidates[index]
    const cardRect: RectLike = {
      left: pos.left,
      top: pos.top,
      right: pos.left + card.width,
      bottom: pos.top + card.height,
      width: card.width,
      height: card.height,
    }
    if (!overlaps(cardRect, target, margin / 2)) {
      return { left: Math.round(pos.left), top: Math.round(pos.top) }
    }
  }

  // Last resort: top-center of viewport (still better than overlapping the prompt).
  return {
    left: Math.round(clamp(viewport.width / 2 - card.width / 2, edge, maxLeft)),
    top: edge,
  }
}
