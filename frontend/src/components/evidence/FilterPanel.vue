<template>
  <aside class="rounded-xl border border-slate-200 bg-white p-4">
    <h2 class="mb-4 text-sm font-semibold text-slate-900">{{ t('app.filter_title') }}</h2>
    <div class="space-y-4 text-sm">
      <label class="block">
        <span class="mb-1 block font-medium">{{ t('app.min_reliability') }}</span>
        <input v-model.number="app.filters.min_reliability" type="range" min="0" max="1" step="0.05" class="w-full" />
        <span class="text-xs text-slate-500">{{ app.filters.min_reliability.toFixed(2) }}</span>
      </label>
      <label class="block">
        <span class="mb-1 block font-medium">{{ t('app.publication_date') }}</span>
        <select v-model="app.filters.date_window" class="w-full rounded-lg border border-slate-300 px-3 py-2">
          <option value="all">{{ t('app.date_window_all') }}</option>
          <option value="last5">{{ t('app.date_window_last5') }}</option>
          <option value="last10">{{ t('app.date_window_last10') }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2">
        <input v-model="app.filters.highlight_contradictions" type="checkbox" />
        <span>{{ t('app.highlight_contradictions') }}</span>
      </label>
      <div class="flex gap-2">
        <UiButton variant="secondary" class="flex-1" @click="reset">{{ t('app.reset') }}</UiButton>
        <UiButton class="flex-1" :loading="loading" @click="apply">{{ t('app.apply') }}</UiButton>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { filterEvidence } from '@/api/chat'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'
import { DEFAULT_FILTERS } from '@/types/api'

const { t } = useI18n()
const app = useAppStore()
const loading = ref(false)

function reset() {
  app.filters = { ...DEFAULT_FILTERS }
}

async function apply() {
  loading.value = true
  try {
    const data = await filterEvidence(app.filters)
    app.evidenceRows = data.rows
  } finally {
    loading.value = false
  }
}
</script>
