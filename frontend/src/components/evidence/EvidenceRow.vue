<template>
  <button
    type="button"
    class="w-full rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50"
    :class="{ 'border-amber-300 bg-amber-50': highlight }"
    @click="$emit('open')"
  >
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-mono text-brand-primary">{{ row.claim_id }}</span>
      <UiBadge tone="info">{{ reliabilityPercent }}%</UiBadge>
    </div>
    <p class="mt-1 text-sm text-slate-800">{{ row.claim_text }}</p>
    <p class="mt-1 text-xs text-slate-500">{{ row.entity }} · {{ row.effect_direction }} · {{ row.study_type }}</p>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import type { EvidenceRow } from '@/types/api'

const props = defineProps<{
  row: EvidenceRow
  highlightContradictions?: boolean
}>()

defineEmits<{ open: [] }>()

const reliabilityPercent = computed(() => Math.round((props.row.reliability_score || 0) * 100))

const highlight = computed(() => {
  if (!props.highlightContradictions) return false
  return props.row.effect_direction?.toLowerCase().includes('contradict') ?? false
})
</script>
