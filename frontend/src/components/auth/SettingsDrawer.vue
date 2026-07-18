<template>
  <UiDrawer :open="app.settingsOpen" :title="t('app.settings')" @close="close">
    <form class="space-y-6" @submit.prevent="save">
      <section class="space-y-5">
        <h3 class="text-sm font-semibold text-slate-900">{{ t('app.settings_editable') }}</h3>
        <LocaleSwitcher id="settingsLanguage" v-model="draft.language" :label="t('app.language')" />
        <UiSliderField
          id="settingsTemperature"
          v-model="draft.temperature"
          :label="t('app.temperature')"
          :help="t('app.help_temperature')"
          :min="0"
          :max="2"
          :step="0.01"
          :format="formatTemperature"
        />
        <UiSliderField
          id="settingsTimeout"
          v-model="draft.timeoutSeconds"
          :label="t('app.timeout_seconds')"
          :help="t('app.help_timeout_seconds')"
          :min="1"
          :max="600"
          :step="1"
          :format="formatTimeout"
        />
      </section>

      <section class="space-y-4 border-t border-slate-200 pt-6">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-slate-900">{{ t('app.settings_read_only') }}</h3>
          <UiBadge tone="neutral">{{ t('app.settings_server_managed') }}</UiBadge>
        </div>
        <p class="text-xs text-slate-500">{{ t('app.settings_read_only_hint') }}</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <UiInput id="settingsHost" :model-value="readonlyConfig.host" :label="t('app.host')" readonly />
          <UiInput
            id="settingsContextLimit"
            :model-value="readonlyConfig.contextLimit"
            :label="t('app.context_limit')"
            readonly
          />
        </div>
      </section>

      <section class="space-y-4 border-t border-slate-200 pt-6">
        <h3 class="text-sm font-semibold text-slate-900">{{ t('app.tutorial_controls_label') }}</h3>
        <p class="text-xs text-slate-500">{{ t('app.tutorial_title') }}</p>
        <div class="flex flex-wrap gap-2">
          <UiButton type="button" variant="secondary" size="sm" @click="startShort">
            {{ t('app.tutorial_short_button') }}
          </UiButton>
          <UiButton type="button" variant="secondary" size="sm" @click="startLong">
            {{ t('app.tutorial_long_button') }}
          </UiButton>
        </div>
      </section>

      <UiButton class="w-full" type="submit">{{ t('app.apply_settings') }}</UiButton>
    </form>
  </UiDrawer>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import LocaleSwitcher from '@/components/ui/LocaleSwitcher.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSliderField from '@/components/ui/UiSliderField.vue'
import { setAppLocale } from '@/i18n'
import { useTutorial } from '@/composables/useTutorial'
import { useAppStore } from '@/stores/app'
import { useStatusStore } from '@/stores/status'
import { useToastStore } from '@/stores/toast'

const { t } = useI18n()
const app = useAppStore()
const status = useStatusStore()
const toast = useToastStore()
const tutorial = useTutorial()

const draft = reactive({
  language: 'en' as 'en' | 'es',
  temperature: 0.2,
  timeoutSeconds: 300,
})

const readonlyConfig = computed(() => {
  const snapshot = status.snapshot
  return {
    host: snapshot?.host || app.config.host,
    contextLimit: String(snapshot?.context_limit ?? app.config.contextLimit),
  }
})

function formatTemperature(value: number) {
  return value.toFixed(2)
}

function formatTimeout(value: number) {
  return `${Math.round(value)}s`
}

function resetDraft() {
  draft.language = app.language
  draft.temperature = app.config.temperature
  draft.timeoutSeconds = app.config.timeoutSeconds
}

function close() {
  app.settingsOpen = false
}

function startShort() {
  app.settingsOpen = false
  tutorial.start('short', true)
}

function startLong() {
  app.settingsOpen = false
  tutorial.start('full', true)
}

function clampTemperature(value: number) {
  if (!Number.isFinite(value)) return app.config.temperature
  return Math.round(Math.min(2, Math.max(0, value)) * 100) / 100
}

function clampTimeout(value: number) {
  if (!Number.isFinite(value)) return app.config.timeoutSeconds
  return Math.min(600, Math.max(1, Math.round(value)))
}

function save() {
  app.language = draft.language
  setAppLocale(draft.language)
  app.setConfig({
    temperature: clampTemperature(draft.temperature),
    timeoutSeconds: clampTimeout(draft.timeoutSeconds),
  })
  toast.push({ type: 'success', message: t('app.settings_applied') })
  window.setTimeout(() => {
    app.settingsOpen = false
  }, 600)
}

watch(
  () => app.settingsOpen,
  (open) => {
    if (!open) return
    resetDraft()
  },
)
</script>
