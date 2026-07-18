import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  findTutorialTarget,
  getTutorialSteps,
  measureTutorialSpotlight,
  SHORT_STEP_IDS,
  TUTORIAL_STORAGE_KEY,
  TUTORIAL_VERSION,
} from '@/composables/tutorialSteps'
import {
  loadTutorialProgress,
  saveTutorialProgress,
  shouldAutoStartTutorial,
  tutorialSignal,
  useTutorial,
} from '@/composables/useTutorial'
import { useAppStore } from '@/stores/app'

const memoryStore = new Map<string, string>()

beforeEach(() => {
  memoryStore.clear()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => memoryStore.get(key) ?? null,
    setItem: (key: string, value: string) => {
      memoryStore.set(key, value)
    },
    removeItem: (key: string) => {
      memoryStore.delete(key)
    },
  })
  setActivePinia(createPinia())
  document.body.innerHTML = ''
})

describe('tutorialSteps', () => {
  it('returns five short steps', () => {
    const steps = getTutorialSteps('short')
    expect(steps.map((step) => step.id)).toEqual(['query', 'send', 'validation', 'evidence', 'filters'])
    expect(steps.every((step) => SHORT_STEP_IDS.has(step.id))).toBe(true)
  })

  it('returns twenty full steps', () => {
    expect(getTutorialSteps('full')).toHaveLength(20)
  })

  it('findTutorialTarget prefers visible in-flow host over fixed drawer duplicate', () => {
    const drawer = document.createElement('div')
    drawer.className = 'fixed inset-0'
    const drawerTarget = document.createElement('div')
    drawerTarget.setAttribute('data-tutorial', 'evidence')
    Object.defineProperty(drawerTarget, 'getBoundingClientRect', {
      value: () => ({
        width: 200,
        height: 100,
        top: 80,
        left: 40,
        right: 240,
        bottom: 180,
        x: 40,
        y: 80,
        toJSON: () => ({}),
      }),
    })
    drawer.appendChild(drawerTarget)

    const columnTarget = document.createElement('div')
    columnTarget.setAttribute('data-tutorial', 'evidence')
    Object.defineProperty(columnTarget, 'getBoundingClientRect', {
      value: () => ({
        width: 300,
        height: 120,
        top: 200,
        left: 900,
        right: 1200,
        bottom: 320,
        x: 900,
        y: 200,
        toJSON: () => ({}),
      }),
    })

    document.body.appendChild(columnTarget)
    document.body.appendChild(drawer)

    expect(findTutorialTarget('evidence')).toBe(columnTarget)
  })

  it('findTutorialTarget skips zero-size (display:none) hosts', () => {
    const hidden = document.createElement('div')
    hidden.setAttribute('data-tutorial', 'evidence')
    Object.defineProperty(hidden, 'getBoundingClientRect', {
      value: () => ({
        width: 0,
        height: 0,
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
    })
    const visible = document.createElement('div')
    visible.className = 'fixed inset-0'
    const nested = document.createElement('div')
    nested.setAttribute('data-tutorial', 'evidence')
    Object.defineProperty(nested, 'getBoundingClientRect', {
      value: () => ({
        width: 180,
        height: 90,
        top: 40,
        left: 20,
        right: 200,
        bottom: 130,
        x: 20,
        y: 40,
        toJSON: () => ({}),
      }),
    })
    visible.appendChild(nested)
    document.body.appendChild(hidden)
    document.body.appendChild(visible)

    expect(findTutorialTarget('evidence')).toBe(nested)
  })

  it('measureTutorialSpotlight pads the full target rect without clipping', () => {
    const query = document.createElement('div')
    query.setAttribute('data-tutorial', 'query')
    Object.defineProperty(query, 'getBoundingClientRect', {
      value: () => ({
        width: 700,
        height: 120,
        top: 600,
        left: 100,
        right: 800,
        bottom: 720,
        x: 100,
        y: 600,
        toJSON: () => ({}),
      }),
    })
    document.body.appendChild(query)

    const spot = measureTutorialSpotlight(query, 6)
    expect(spot).toEqual({ left: 94, top: 594, width: 712, height: 132 })
  })
})

describe('useTutorial', () => {
  it('starts short mode and resets actions', () => {
    const tutorial = useTutorial()
    tutorialSignal('report_ready')
    tutorial.start('short', true)
    expect(tutorial.state.running).toBe(true)
    expect(tutorial.state.mode).toBe('short')
    expect(tutorial.state.stepIndex).toBe(0)
    expect(tutorial.state.actions.report_ready).toBe(false)
    expect(tutorial.steps.value).toHaveLength(5)
  })

  it('gates next until required action is signaled', () => {
    const tutorial = useTutorial()
    tutorial.start('short', true)
    expect(tutorial.canAdvance.value).toBe(false)
    tutorialSignal('question_typed')
    expect(tutorial.canAdvance.value).toBe(true)
    tutorial.next()
    expect(tutorial.state.stepIndex).toBe(1)
    expect(tutorial.canAdvance.value).toBe(false)
  })

  it('persists dismissed status and skips auto-start', () => {
    saveTutorialProgress('dismissed')
    const progress = loadTutorialProgress()
    expect(progress.version).toBe(TUTORIAL_VERSION)
    expect(progress.status).toBe('dismissed')
    expect(shouldAutoStartTutorial()).toBe(false)
  })

  it('auto-starts when storage is empty', () => {
    memoryStore.delete(TUTORIAL_STORAGE_KEY)
    expect(shouldAutoStartTutorial()).toBe(true)
  })

  it('finish on last step marks completed', () => {
    const tutorial = useTutorial()
    tutorial.start('short', true)
    tutorial.state.stepIndex = tutorial.steps.value.length - 1
    tutorialSignal('filters_applied')
    tutorial.next()
    expect(tutorial.state.running).toBe(false)
    expect(loadTutorialProgress().status).toBe('completed')
  })

  it('evidence_sidebar ensure opens drawer only below lg', () => {
    const app = useAppStore()
    const tutorial = useTutorial()
    tutorial.start('short', true)

    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 })
    tutorial.state.stepIndex = tutorial.steps.value.findIndex((step) => step.id === 'evidence')
    tutorial.ensureCurrentStepVisible()
    expect(app.evidenceCollapsed).toBe(false)
    expect(app.evidenceSidebarOpen).toBe(false)

    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 800 })
    tutorial.ensureCurrentStepVisible()
    expect(app.evidenceSidebarOpen).toBe(true)
  })
})
