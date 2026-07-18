export type TutorialMode = 'short' | 'full'

export type TutorialAction =
  | 'question_typed'
  | 'report_ready'
  | 'db_explorer_opened'
  | 'sessions_view_opened'
  | 'hypothesis_queue_opened'
  | 'review_queue_opened'
  | 'evidence_clicked'
  | 'filters_applied'

export type TutorialEnsure =
  | 'assistant'
  | 'filter_modal'
  | 'diagnostics'
  | 'evidence_sidebar'
  | 'db_explorer'
  | 'sessions'
  | 'hypothesis'
  | 'review'
  | 'report_actions'

export interface TutorialStepDef {
  id: string
  target: string
  titleKey: string
  bodyKey: string
  requiredAction?: TutorialAction
  readyWhen?: 'last_report' | 'evidence_rows' | 'db_explorer_open' | 'view_sessions' | 'view_hypothesis' | 'view_review'
  ensureVisible?: TutorialEnsure[]
}

export const TUTORIAL_VERSION = '2026-07-05-v1'
export const TUTORIAL_STORAGE_KEY = 'als_tool_tutorial'

export const SHORT_STEP_IDS = new Set(['query', 'send', 'validation', 'evidence', 'filters'])

export const FULL_TUTORIAL_STEPS: TutorialStepDef[] = [
  {
    id: 'query',
    target: 'query',
    titleKey: 'tutorial_step_query_title',
    bodyKey: 'tutorial_step_query_body',
    requiredAction: 'question_typed',
    ensureVisible: ['assistant'],
  },
  {
    id: 'send',
    target: 'send',
    titleKey: 'tutorial_step_send_title',
    bodyKey: 'tutorial_step_send_body',
    requiredAction: 'report_ready',
    ensureVisible: ['assistant'],
  },
  {
    id: 'report',
    target: 'report',
    titleKey: 'tutorial_step_report_title',
    bodyKey: 'tutorial_step_report_body',
    readyWhen: 'last_report',
    ensureVisible: ['assistant'],
  },
  {
    id: 'validation',
    target: 'validation',
    titleKey: 'tutorial_step_validation_title',
    bodyKey: 'tutorial_step_validation_body',
    readyWhen: 'last_report',
    ensureVisible: ['assistant'],
  },
  {
    id: 'diagnostics',
    target: 'diagnostics',
    titleKey: 'tutorial_step_diagnostics_title',
    bodyKey: 'tutorial_step_diagnostics_body',
    ensureVisible: ['assistant', 'evidence_sidebar', 'diagnostics'],
  },
  {
    id: 'save_session',
    target: 'save_session',
    titleKey: 'tutorial_step_save_title',
    bodyKey: 'tutorial_step_save_body',
    readyWhen: 'last_report',
    ensureVisible: ['assistant', 'report_actions'],
  },
  {
    id: 'export_summary',
    target: 'export_summary',
    titleKey: 'tutorial_step_export_title',
    bodyKey: 'tutorial_step_export_body',
    readyWhen: 'last_report',
    ensureVisible: ['assistant', 'report_actions'],
  },
  {
    id: 'copy_citations',
    target: 'copy_citations',
    titleKey: 'tutorial_step_copy_title',
    bodyKey: 'tutorial_step_copy_body',
    readyWhen: 'last_report',
    ensureVisible: ['assistant', 'report_actions'],
  },
  {
    id: 'open_db_explorer',
    target: 'open_db_explorer',
    titleKey: 'tutorial_step_db_open_title',
    bodyKey: 'tutorial_step_db_open_body',
    requiredAction: 'db_explorer_opened',
  },
  {
    id: 'db_explorer',
    target: 'db_explorer',
    titleKey: 'tutorial_step_db_explorer_title',
    bodyKey: 'tutorial_step_db_explorer_body',
    readyWhen: 'db_explorer_open',
    ensureVisible: ['db_explorer'],
  },
  {
    id: 'sessions_nav',
    target: 'sessions_nav',
    titleKey: 'tutorial_step_sessions_nav_title',
    bodyKey: 'tutorial_step_sessions_nav_body',
    requiredAction: 'sessions_view_opened',
  },
  {
    id: 'sessions_list',
    target: 'sessions_list',
    titleKey: 'tutorial_step_sessions_list_title',
    bodyKey: 'tutorial_step_sessions_list_body',
    readyWhen: 'view_sessions',
    ensureVisible: ['sessions'],
  },
  {
    id: 'open_hypothesis_queue',
    target: 'hypothesis_nav',
    titleKey: 'tutorial_step_hypothesis_open_title',
    bodyKey: 'tutorial_step_hypothesis_open_body',
    requiredAction: 'hypothesis_queue_opened',
  },
  {
    id: 'hypothesis_queue',
    target: 'hypothesis_queue',
    titleKey: 'tutorial_step_hypothesis_queue_title',
    bodyKey: 'tutorial_step_hypothesis_queue_body',
    readyWhen: 'view_hypothesis',
    ensureVisible: ['hypothesis'],
  },
  {
    id: 'open_review_queue',
    target: 'review_nav',
    titleKey: 'tutorial_step_review_open_title',
    bodyKey: 'tutorial_step_review_open_body',
    requiredAction: 'review_queue_opened',
  },
  {
    id: 'review_queue',
    target: 'review_queue',
    titleKey: 'tutorial_step_review_queue_title',
    bodyKey: 'tutorial_step_review_queue_body',
    readyWhen: 'view_review',
    ensureVisible: ['review'],
  },
  {
    id: 'evidence',
    target: 'evidence',
    titleKey: 'tutorial_step_evidence_title',
    bodyKey: 'tutorial_step_evidence_body',
    readyWhen: 'evidence_rows',
    ensureVisible: ['assistant', 'evidence_sidebar'],
  },
  {
    id: 'lineage',
    target: 'lineage',
    titleKey: 'tutorial_step_lineage_title',
    bodyKey: 'tutorial_step_lineage_body',
    requiredAction: 'evidence_clicked',
    readyWhen: 'evidence_rows',
    ensureVisible: ['assistant', 'evidence_sidebar'],
  },
  {
    id: 'filters',
    target: 'filters',
    titleKey: 'tutorial_step_filters_title',
    bodyKey: 'tutorial_step_filters_body',
    requiredAction: 'filters_applied',
    ensureVisible: ['assistant', 'filter_modal'],
  },
  {
    id: 'compare',
    target: 'compare',
    titleKey: 'tutorial_step_compare_title',
    bodyKey: 'tutorial_step_compare_body',
    ensureVisible: ['assistant', 'evidence_sidebar'],
  },
]

export function getTutorialSteps(mode: TutorialMode): TutorialStepDef[] {
  if (mode === 'short') {
    return FULL_TUTORIAL_STEPS.filter((step) => SHORT_STEP_IDS.has(step.id))
  }
  return FULL_TUTORIAL_STEPS
}

export function tutorialTargetSelector(target: string): string {
  return `[data-tutorial="${target}"]`
}

function isVisibleTutorialTarget(el: HTMLElement): boolean {
  const rect = el.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0
}

/**
 * Resolve a tutorial target in the DOM. Prefer a painted in-flow host when
 * duplicates exist (desktop column + mobile drawer both mounted).
 */
export function findTutorialTarget(target: string): HTMLElement | null {
  const nodes = Array.from(document.querySelectorAll(tutorialTargetSelector(target))) as HTMLElement[]
  if (!nodes.length) return null
  const visible = nodes.filter(isVisibleTutorialTarget)
  if (!visible.length) return nodes[0] ?? null
  const inFlow = visible.find((el) => !el.closest('.fixed'))
  return inFlow ?? visible[0] ?? null
}

export interface SpotlightRect {
  left: number
  top: number
  width: number
  height: number
}

/** Build a padded spotlight rect for a tutorial target element. */
export function measureTutorialSpotlight(target: HTMLElement, pad = 6): SpotlightRect {
  const raw = target.getBoundingClientRect()
  return {
    left: Math.round(raw.left - pad),
    top: Math.round(raw.top - pad),
    width: Math.max(0, Math.round(raw.width + pad * 2)),
    height: Math.max(0, Math.round(raw.height + pad * 2)),
  }
}
