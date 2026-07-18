<template>
  <div
    class="w-full rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50"
    data-tutorial="lineage"
    :class="{ 'border-amber-300 bg-amber-50': highlight }"
  >
    <button type="button" class="w-full text-left" @click="$emit('open')">
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-mono text-brand-primary">{{ row.claim_id }}</span>
        <UiBadge tone="info">{{ reliabilityPercent }}%</UiBadge>
      </div>
      <p class="mt-1 text-sm text-slate-800">{{ row.claim_text }}</p>
      <p class="mt-1 text-xs text-slate-500">{{ row.entity }} · {{ row.effect_direction }} · {{ row.study_type }}</p>
    </button>
    <div class="mt-2 border-t border-slate-100 pt-2">
      <UiButton variant="secondary" size="sm" @click="addToCompare">
        {{ t('app.use_in_compare') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'
import type { EvidenceRow } from '@/types/api'

const props = defineProps<{
  row: EvidenceRow
  highlightContradictions?: boolean
}>()

defineEmits<{ open: [] }>()

const { t } = useI18n()
const app = useAppStore()

const reliabilityPercent = computed(() => Math.round((props.row.reliability_score || 0) * 100))

const highlight = computed(() => {
  if (!props.highlightContradictions) return false
  return props.row.effect_direction?.toLowerCase().includes('contradict') ?? false
})

function addToCompare(event: MouseEvent) {
  event.stopPropagation()
  app.addToCompare(props.row.claim_id)
}
</script>
