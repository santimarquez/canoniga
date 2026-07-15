<template>
  <UiDrawer :open="app.settingsOpen" :title="t('app.settings')" @close="app.settingsOpen = false">
    <div class="space-y-4">
      <LocaleSwitcher v-model="locale" :label="t('app.language')" />
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.model') }}</span>
        <input v-model="app.config.model" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.host') }}</span>
        <input v-model="app.config.host" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.context_limit') }}</span>
        <input v-model.number="app.config.contextLimit" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.temperature') }}</span>
        <input v-model.number="app.config.temperature" type="number" step="0.1" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.timeout_seconds') }}</span>
        <input v-model.number="app.config.timeoutSeconds" type="number" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <UiButton class="w-full" @click="save">{{ t('app.apply_settings') }}</UiButton>
    </div>
  </UiDrawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import LocaleSwitcher from '@/components/ui/LocaleSwitcher.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import { setAppLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()

const locale = computed({
  get: () => app.language,
  set: (value: 'en' | 'es') => {
    app.language = value
    setAppLocale(value)
  },
})

function save() {
  app.settingsOpen = false
}
</script>
