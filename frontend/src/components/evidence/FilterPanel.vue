<template>
  <div class="space-y-3 text-sm">
    <div>
      <span class="mb-2 block font-medium text-slate-700">{{ t('app.evidence_types_to_include') }}</span>
      <div class="flex flex-wrap justify-start gap-2">
        <button
          v-for="type in EVIDENCE_TYPE_OPTIONS"
          :key="type"
          type="button"
          class="rounded-full border px-3 py-1 text-xs font-medium transition-colors"
          :class="
            isTypeActive(type)
              ? 'border-brand-primary bg-brand-primary text-white'
              : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'
          "
          :aria-pressed="isTypeActive(type)"
          @click="toggleType(type)"
        >
          {{ t(`app.evidence_type_${type}`) }}
        </button>
      </div>
    </div>

    <div class="flex flex-col gap-3 md:grid md:grid-cols-[minmax(140px,200px)_minmax(140px,180px)_auto] md:grid-rows-[auto_auto] md:items-center md:gap-x-4 md:gap-y-1.5">
      <span class="font-medium text-slate-700 md:col-start-1 md:row-start-1">
        {{ t('app.min_reliability') }}
      </span>
      <span class="font-medium text-slate-700 md:col-start-2 md:row-start-1">
        {{ t('app.publication_date') }}
      </span>

      <div class="flex items-center gap-2 md:col-start-1 md:row-start-2">
        <input
          v-model.number="app.filters.min_reliability"
          type="range"
          min="0"
          max="1"
          step="0.01"
          class="h-1.5 min-w-0 flex-1 cursor-pointer accent-brand-primary"
        />
        <span class="w-8 shrink-0 text-right font-mono text-xs text-brand-primary">{{ reliabilityPercent }}%</span>
      </div>

      <select
        v-model="app.filters.date_window"
        class="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm md:col-start-2 md:row-start-2"
      >
        <option value="all">{{ t('app.date_window_all') }}</option>
        <option value="last5">{{ t('app.date_window_last5') }}</option>
        <option value="last10">{{ t('app.date_window_last10') }}</option>
      </select>

      <label class="flex items-center gap-2 text-slate-700 md:col-start-3 md:row-start-2 md:self-center">
        <input v-model="app.filters.highlight_contradictions" type="checkbox" class="accent-brand-primary" />
        <span class="whitespace-nowrap">{{ t('app.highlight_contradictions') }}</span>
      </label>
    </div>

    <div class="flex items-center gap-2">
      <UiButton variant="ghost" size="sm" @click="reset">{{ t('app.reset_filters') }}</UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'
import { useToastStore } from '@/stores/toast'
import { DEFAULT_FILTERS, EVIDENCE_TYPE_OPTIONS } from '@/types/api'

const { t } = useI18n()
const app = useAppStore()
const toast = useToastStore()

const reliabilityPercent = computed(() => Math.round(app.filters.min_reliability * 100))

function isTypeActive(type: string) {
  return app.filters.evidence_types.includes(type)
}

function toggleType(type: string) {
  const next = new Set(app.filters.evidence_types)
  if (next.has(type)) next.delete(type)
  else next.add(type)
  app.filters.evidence_types = [...next]
}

function reset() {
  app.filters = { ...DEFAULT_FILTERS, evidence_types: [...DEFAULT_FILTERS.evidence_types] }
  toast.push({ type: 'info', message: t('app.filters_reset') })
}
</script>
