import { computed, reactive } from 'vue'
import {
  getTutorialSteps,
  TUTORIAL_STORAGE_KEY,
  TUTORIAL_VERSION,
  type TutorialAction,
  type TutorialEnsure,
  type TutorialMode,
  type TutorialStepDef,
} from '@/composables/tutorialSteps'
import { useAppStore } from '@/stores/app'

export type TutorialStopStatus = 'completed' | 'dismissed' | ''

interface TutorialProgress {
  version: string
  status: string
}

interface TutorialState {
  running: boolean
  mode: TutorialMode
  stepIndex: number
  actions: Record<TutorialAction, boolean>
  notice: string
}

const emptyActions = (): Record<TutorialAction, boolean> => ({
  question_typed: false,
  report_ready: false,
  db_explorer_opened: false,
  sessions_view_opened: false,
  hypothesis_queue_opened: false,
  review_queue_opened: false,
  evidence_clicked: false,
  filters_applied: false,
})

const tutorialState = reactive<TutorialState>({
  running: false,
  mode: 'short',
  stepIndex: 0,
  actions: emptyActions(),
  notice: '',
})

let navigateHandler: ((name: string) => void) | null = null

export function setTutorialNavigateHandler(handler: ((name: string) => void) | null) {
  navigateHandler = handler
}

export function loadTutorialProgress(): TutorialProgress {
  try {
    const storage = globalThis.localStorage
    const raw = storage?.getItem(TUTORIAL_STORAGE_KEY)
    if (!raw) return { version: '', status: '' }
    const parsed = JSON.parse(raw) as { version?: string; status?: string }
    return {
      version: String(parsed.version || ''),
      status: String(parsed.status || ''),
    }
  } catch {
    return { version: '', status: '' }
  }
}

export function saveTutorialProgress(status: TutorialStopStatus) {
  try {
    globalThis.localStorage?.setItem(
      TUTORIAL_STORAGE_KEY,
      JSON.stringify({
        version: TUTORIAL_VERSION,
        status: String(status || ''),
        updated_at: new Date().toISOString(),
      }),
    )
  } catch {
    // ignore quota / private mode
  }
}

export function shouldAutoStartTutorial(): boolean {
  const progress = loadTutorialProgress()
  if (progress.version !== TUTORIAL_VERSION) return true
  return progress.status !== 'completed' && progress.status !== 'dismissed'
}

function isReadyWhen(step: TutorialStepDef, app: ReturnType<typeof useAppStore>): boolean {
  switch (step.readyWhen) {
    case 'last_report':
      return Boolean(app.lastReport)
    case 'evidence_rows':
      return app.evidenceRows.length > 0
    case 'db_explorer_open':
      return app.dbExplorerOpen
    case 'view_sessions':
      return app.activeView === 'sessions'
    case 'view_hypothesis':
      return app.activeView === 'hypothesis'
    case 'view_review':
      return app.activeView === 'review'
    default:
      return true
  }
}

/** Tailwind `lg` — desktop EvidenceSidebar column is shown from this width. */
export const TUTORIAL_LG_MIN_WIDTH_PX = 1024

function prefersEvidenceDrawer(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < TUTORIAL_LG_MIN_WIDTH_PX
}

function runEnsureVisible(keys: TutorialEnsure[] | undefined, app: ReturnType<typeof useAppStore>) {
  if (!keys?.length) return
  for (const key of keys) {
    if (key === 'assistant') {
      navigateHandler?.('assistant')
      app.switchView('assistant')
    } else if (key === 'sessions') {
      navigateHandler?.('sessions')
      app.switchView('sessions')
    } else if (key === 'hypothesis') {
      navigateHandler?.('hypothesis')
      app.switchView('hypothesis')
    } else if (key === 'review') {
      navigateHandler?.('review')
      app.switchView('review')
    } else if (key === 'filter_modal') {
      app.filterModalOpen = true
    } else if (key === 'diagnostics') {
      app.tutorialDiagnosticsOpen = true
    } else if (key === 'evidence_sidebar') {
      app.evidenceCollapsed = false
      app.tutorialEvidenceOpen = true
      // Desktop uses the lg column; opening the drawer there mounts a second
      // EvidenceSidebar and the spotlight measures the wrong (column) host.
      app.evidenceSidebarOpen = prefersEvidenceDrawer()
    } else if (key === 'db_explorer') {
      app.dbExplorerOpen = true
    } else if (key === 'report_actions') {
      // Report actions appear when report is ready; nothing else to force.
    }
  }
}

export function useTutorial() {
  const app = useAppStore()

  const steps = computed(() => getTutorialSteps(tutorialState.mode))
  const currentStep = computed(() => steps.value[tutorialState.stepIndex] ?? null)
  const isLastStep = computed(() => tutorialState.stepIndex >= steps.value.length - 1)

  const actionComplete = computed(() => {
    const step = currentStep.value
    if (!step?.requiredAction) return true
    return Boolean(tutorialState.actions[step.requiredAction])
  })

  const stepReady = computed(() => {
    const step = currentStep.value
    if (!step) return false
    return isReadyWhen(step, app)
  })

  const canAdvance = computed(() => actionComplete.value && stepReady.value)

  function syncAppFlag() {
    app.tutorialRunning = tutorialState.running
  }

  function start(mode: TutorialMode = 'short', manual = true) {
    if (!manual && !shouldAutoStartTutorial()) return
    tutorialState.mode = mode === 'full' ? 'full' : 'short'
    tutorialState.running = true
    tutorialState.stepIndex = 0
    tutorialState.actions = emptyActions()
    tutorialState.notice = ''
    app.settingsOpen = false
    syncAppFlag()
    ensureCurrentStepVisible()
  }

  function stop(status: TutorialStopStatus = '') {
    tutorialState.running = false
    tutorialState.stepIndex = 0
    syncAppFlag()
    if (status === 'completed') {
      saveTutorialProgress('completed')
      tutorialState.notice = 'tutorial_done'
    } else if (status === 'dismissed') {
      saveTutorialProgress('dismissed')
      tutorialState.notice = 'tutorial_stopped'
    }
  }

  function ensureCurrentStepVisible() {
    const step = currentStep.value
    if (!step) return
    runEnsureVisible(step.ensureVisible, app)
  }

  function next() {
    if (!tutorialState.running || !canAdvance.value) return
    if (isLastStep.value) {
      stop('completed')
      return
    }
    tutorialState.stepIndex += 1
    ensureCurrentStepVisible()
  }

  function back() {
    if (!tutorialState.running || tutorialState.stepIndex <= 0) return
    tutorialState.stepIndex -= 1
    ensureCurrentStepVisible()
  }

  function signal(action: TutorialAction | string) {
    const name = String(action || '').trim() as TutorialAction
    if (!name || !(name in tutorialState.actions)) return
    tutorialState.actions[name] = true
    if (name === 'db_explorer_opened') {
      app.dbExplorerOpen = true
    }
  }

  function clearNotice() {
    tutorialState.notice = ''
  }

  return {
    state: tutorialState,
    steps,
    currentStep,
    isLastStep,
    actionComplete,
    stepReady,
    canAdvance,
    start,
    stop,
    next,
    back,
    signal,
    ensureCurrentStepVisible,
    clearNotice,
    shouldAutoStartTutorial,
  }
}

/** Module-level signal helper for call sites that should not instantiate the full composable. */
export function tutorialSignal(action: TutorialAction | string) {
  const name = String(action || '').trim() as TutorialAction
  if (!name || !(name in tutorialState.actions)) return
  tutorialState.actions[name] = true
}
