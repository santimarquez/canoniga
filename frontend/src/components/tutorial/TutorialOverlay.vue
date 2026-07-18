<template>
  <Transition name="overlay-fade">
    <div
      v-if="state.running"
      class="tutorial-overlay pointer-events-none fixed inset-0 z-[60]"
      aria-live="polite"
    >
      <!-- Catch clicks outside the hole; passthrough over the spotlight lets the target stay usable. -->
      <div
        v-for="(style, key) in blockerStyles"
        :key="key"
        class="tutorial-blocker pointer-events-auto absolute"
        :style="style"
        aria-hidden="true"
      />
      <div
        class="tutorial-spotlight pointer-events-none absolute rounded-lg ring-2 ring-brand-primary ring-offset-2 transition-all duration-200"
        :style="spotlightStyle"
      />
      <div
        ref="cardRef"
        class="ui-modal-panel tutorial-card pointer-events-auto absolute z-[61] w-[min(92vw,420px)] rounded-xl border border-slate-200 bg-white p-4 shadow-xl"
        :style="cardStyle"
        role="dialog"
        :aria-label="t('app.tutorial_title')"
      >
        <p class="text-xs font-medium uppercase tracking-wide text-slate-500">
          {{ t('app.tutorial_progress', { current: state.stepIndex + 1, total: steps.length }) }}
        </p>
        <h2 class="mt-1 text-base font-semibold text-slate-900">{{ titleText }}</h2>
        <p class="mt-2 text-sm text-slate-700">{{ bodyText }}</p>
        <p v-if="!canAdvance" class="mt-2 text-xs text-amber-700">
          {{ t('app.tutorial_wait_for_action') }}
        </p>
        <div class="mt-4 flex flex-wrap justify-end gap-2">
          <UiButton variant="secondary" size="sm" :disabled="state.stepIndex <= 0" @click="back()">
            {{ t('app.tutorial_back') }}
          </UiButton>
          <UiButton variant="secondary" size="sm" @click="stop('dismissed')">
            {{ t('app.tutorial_stop') }}
          </UiButton>
          <UiButton size="sm" :disabled="!canAdvance" @click="next()">
            {{ isLastStep ? t('app.tutorial_finish') : t('app.tutorial_next') }}
          </UiButton>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import UiButton from '@/components/ui/UiButton.vue'
import { computeTutorialCardPosition, type RectLike } from '@/composables/tutorialCardPosition'
import { findTutorialTarget, measureTutorialSpotlight } from '@/composables/tutorialSteps'
import { setTutorialNavigateHandler, useTutorial } from '@/composables/useTutorial'

const { t, locale } = useI18n()
const router = useRouter()
const {
  state,
  steps,
  currentStep,
  isLastStep,
  canAdvance,
  stepReady,
  next,
  back,
  stop,
  ensureCurrentStepVisible,
} = useTutorial()
const cardRef = ref<HTMLElement | null>(null)

const spotlight = ref({ left: 0, top: 0, width: 0, height: 0 })
const cardPos = ref({ left: 12, top: 12 })
let renderTimer: ReturnType<typeof setTimeout> | null = null
let highlightedEl: HTMLElement | null = null

const titleText = computed(() => {
  const step = currentStep.value
  if (!step) return t('app.tutorial_title')
  const raw = String(t(`app.${step.titleKey}`))
  const stripped = raw.replace(/^(Step|Paso)\s*\d+\s*:\s*/i, '').trim()
  const current = state.stepIndex + 1
  const prefix = String(locale.value || 'en').toLowerCase().startsWith('es')
    ? `Paso ${current}`
    : `Step ${current}`
  return `${prefix}: ${stripped}`
})

const bodyText = computed(() => {
  const step = currentStep.value
  return step ? t(`app.${step.bodyKey}`) : ''
})

const spotlightStyle = computed(() => ({
  left: `${spotlight.value.left}px`,
  top: `${spotlight.value.top}px`,
  width: `${spotlight.value.width}px`,
  height: `${spotlight.value.height}px`,
  opacity: spotlight.value.width > 0 ? 1 : 0,
}))

/** Four panels (or one full-screen) so only the spotlight cutout passes pointer events. */
const blockerStyles = computed(() => {
  const { left, top, width, height } = spotlight.value
  if (width <= 0 || height <= 0) {
    return {
      full: { left: '0', top: '0', right: '0', bottom: '0' },
    }
  }
  const right = left + width
  const bottom = top + height
  return {
    top: { left: '0', top: '0', width: '100%', height: `${top}px` },
    left: { left: '0', top: `${top}px`, width: `${left}px`, height: `${height}px` },
    right: { left: `${right}px`, top: `${top}px`, right: '0', height: `${height}px` },
    bottom: { left: '0', top: `${bottom}px`, right: '0', bottom: '0' },
  }
})

const cardStyle = computed(() => ({
  left: `${cardPos.value.left}px`,
  top: `${cardPos.value.top}px`,
}))

function clearHighlight() {
  if (highlightedEl) {
    highlightedEl.classList.remove('tutorial-target')
    highlightedEl = null
  }
}

function positionCard(targetRect: RectLike) {
  const card = cardRef.value
  const cardWidth = card?.offsetWidth || 360
  const cardHeight = card?.offsetHeight || 200
  cardPos.value = computeTutorialCardPosition(
    targetRect,
    { width: cardWidth, height: cardHeight },
    { width: window.innerWidth, height: window.innerHeight },
  )
}

function applySpotlight(target: HTMLElement) {
  clearHighlight()
  highlightedEl = target
  highlightedEl.classList.add('tutorial-target')
  const measured = measureTutorialSpotlight(target)
  spotlight.value = measured
  void nextTick(() =>
    positionCard({
      left: measured.left,
      top: measured.top,
      right: measured.left + measured.width,
      bottom: measured.top + measured.height,
      width: measured.width,
      height: measured.height,
    }),
  )
}

function renderStep() {
  if (!state.running) return
  const step = currentStep.value
  if (!step) return

  if (renderTimer) {
    clearTimeout(renderTimer)
    renderTimer = null
  }

  if (!stepReady.value) {
    clearHighlight()
    spotlight.value = { left: 0, top: 0, width: 0, height: 0 }
    cardPos.value = {
      left: Math.max(8, Math.round(window.innerWidth / 2 - 210)),
      top: Math.max(8, Math.round(window.innerHeight - 220)),
    }
    renderTimer = setTimeout(renderStep, 250)
    return
  }

  const target = findTutorialTarget(step.target)
  if (!target) {
    clearHighlight()
    spotlight.value = { left: 0, top: 0, width: 0, height: 0 }
    ensureCurrentStepVisible()
    renderTimer = setTimeout(renderStep, 250)
    return
  }

  target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  applySpotlight(target)

  // Re-measure after disclosure / column layout settles.
  const stepId = step.id
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (!state.running || currentStep.value?.id !== stepId) return
      const fresh = findTutorialTarget(step.target)
      if (fresh) applySpotlight(fresh)
    })
  })
}

function onKeydown(event: KeyboardEvent) {
  if (!state.running) return
  if (event.key === 'Escape') {
    event.preventDefault()
    stop('dismissed')
    return
  }
  const tag = (event.target as HTMLElement | null)?.tagName
  if (tag === 'TEXTAREA' || tag === 'INPUT') return
  if (event.key === 'Enter' && canAdvance.value) {
    event.preventDefault()
    next()
  }
}

function scheduleRender() {
  void nextTick(renderStep)
}

setTutorialNavigateHandler((name) => {
  void router.push({ name })
})

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', scheduleRender)
  window.addEventListener('scroll', scheduleRender, true)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', scheduleRender)
  window.removeEventListener('scroll', scheduleRender, true)
  if (renderTimer) clearTimeout(renderTimer)
  clearHighlight()
  setTutorialNavigateHandler(null)
})

watch(
  () => [state.running, state.stepIndex, state.mode] as const,
  ([running]) => {
    if (running) ensureCurrentStepVisible()
    scheduleRender()
  },
  { immediate: true },
)

watch(
  () => [canAdvance.value, stepReady.value, JSON.stringify(state.actions)],
  scheduleRender,
)
</script>

<style scoped>
.tutorial-spotlight {
  box-shadow: 0 0 0 9999px rgb(15 23 42 / 0.45);
  background: transparent;
}
</style>

<style>
/*
 * Visual elevation only. Interaction goes through the overlay cutout (pointer-events),
 * not by stacking the target above the overlay (that fails inside nested contexts
 * and position:relative would break absolute targets like send).
 */
.tutorial-target {
  z-index: 62 !important;
}
</style>
