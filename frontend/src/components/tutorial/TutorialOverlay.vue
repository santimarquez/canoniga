<template>
  <div v-if="app.tutorialRunning" class="fixed inset-0 z-50 bg-black/40">
    <div class="absolute bottom-6 left-1/2 w-[min(92vw,480px)] -translate-x-1/2 rounded-xl bg-white p-4 shadow-xl">
      <p class="text-sm text-slate-700">{{ stepText }}</p>
      <div class="mt-4 flex justify-end gap-2">
        <UiButton variant="secondary" size="sm" @click="skip">{{ t('app.tutorial_stop') }}</UiButton>
        <UiButton size="sm" @click="next">{{ t('app.tutorial_next') }}</UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()
const step = ref(0)

const steps = ['tutorial_step_query_body', 'tutorial_step_send_body', 'tutorial_step_report_body', 'tutorial_step_sessions_nav_body']

const stepText = computed(() => t(`app.${steps[step.value] || steps[0]}`))

function next() {
  if (step.value >= steps.length - 1) {
    app.tutorialRunning = false
    step.value = 0
    return
  }
  step.value += 1
}

function skip() {
  app.tutorialRunning = false
  step.value = 0
}
</script>
