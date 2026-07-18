<template>
  <UiModal
    :open="app.compareModalOpen"
    :title="t('app.compare_modal_title')"
    panel-class="max-w-4xl"
    @close="close"
  >
    <div v-if="loading" class="flex items-center justify-center py-10 text-sm text-slate-500">
      {{ t('app.status_loading') }}
    </div>
    <div v-else-if="error" class="text-sm text-red-700">{{ errorMessage }}</div>
    <div v-else-if="result" class="space-y-5 overflow-y-auto">
      <div class="flex flex-wrap items-center gap-2">
        <UiBadge :tone="conflictTone">{{ conflictLabel }}</UiBadge>
        <span class="text-xs text-slate-600">
          {{ t('app.shared_supporting', { count: result.shared_supporting_count }) }}
        </span>
        <span class="text-xs text-slate-600">
          {{ t('app.shared_contradicting', { count: result.shared_contradicting_count }) }}
        </span>
      </div>

      <div class="grid gap-4 md:grid-cols-2">
        <section class="rounded-lg border border-slate-200 p-3">
          <h3 class="text-sm font-semibold text-slate-900">{{ t('app.claim_a') }} · {{ result.claim_a.claim_id }}</h3>
          <p class="mt-2 text-sm text-slate-700">{{ result.claim_a.claim_text || t('app.lineage_no_claim_text') }}</p>
        </section>
        <section class="rounded-lg border border-slate-200 p-3">
          <h3 class="text-sm font-semibold text-slate-900">{{ t('app.claim_b') }} · {{ result.claim_b.claim_id }}</h3>
          <p class="mt-2 text-sm text-slate-700">{{ result.claim_b.claim_text || t('app.lineage_no_claim_text') }}</p>
        </section>
      </div>

      <div class="overflow-x-auto rounded-lg border border-slate-200">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-3 py-2 font-semibold">{{ t('app.compare_field') }}</th>
              <th class="px-3 py-2 font-semibold">{{ t('app.claim_a') }}</th>
              <th class="px-3 py-2 font-semibold">{{ t('app.claim_b') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in fieldDiffs"
              :key="row.field"
              :class="row.differs ? 'bg-amber-50' : 'bg-white'"
            >
              <td class="border-t border-slate-100 px-3 py-2 font-medium text-slate-800">
                {{ fieldLabel(row.field) }}
                <span v-if="row.differs" class="ml-1 text-[10px] font-semibold uppercase text-amber-700">
                  {{ t('app.compare_differs') }}
                </span>
              </td>
              <td class="border-t border-slate-100 px-3 py-2 text-slate-700">{{ displayValue(row.value_a) }}</td>
              <td class="border-t border-slate-100 px-3 py-2 text-slate-700">{{ displayValue(row.value_b) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="result.follow_up_suggestion" class="text-sm text-slate-700">
        <span class="font-medium text-slate-900">{{ t('app.follow_up') }}:</span>
        {{ result.follow_up_suggestion }}
      </p>
    </div>
  </UiModal>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiModal from '@/components/ui/UiModal.vue'
import { useAppStore } from '@/stores/app'

const { t, te } = useI18n()
const app = useAppStore()

const result = computed(() => app.currentCompare)
const loading = computed(() => app.compareLoading)
const error = computed(() => app.compareError)
const errorMessage = computed(() => {
  const key = error.value
  if (!key) return ''
  return te(`app.${key}`) ? String(t(`app.${key}`)) : key
})

const fieldDiffs = computed(() => result.value?.conflict?.field_diffs ?? [])

const conflictType = computed(() => result.value?.conflict?.contradiction_type || '')

const conflictLabel = computed(() => {
  const key = `app.conflict_type_${conflictType.value}`
  return te(key) ? String(t(key)) : conflictType.value || t('app.conflict_type_unknown')
})

const conflictTone = computed(() => {
  if (conflictType.value === 'aligned') return 'success' as const
  if (conflictType.value) return 'warning' as const
  return 'neutral' as const
})

watch(
  () => app.compareModalOpen,
  (open) => {
    if (open && window.matchMedia('(max-width: 1023px)').matches) {
      app.evidenceSidebarOpen = true
    }
  },
)

function fieldLabel(field: string) {
  const key = `app.compare_field_${field}`
  return te(key) ? String(t(key)) : field
}

function displayValue(value: string) {
  return value?.trim() || '—'
}

function close() {
  app.compareModalOpen = false
}
</script>
