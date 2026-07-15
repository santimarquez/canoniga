<template>
  <button
    type="button"
    class="w-full rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50"
    :class="{ 'border-amber-300 bg-amber-50': highlight }"
    @click="$emit('open')"
  >
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-mono text-brand-primary">{{ row.claim_id }}</span>
      <UiBadge tone="info">{{ row.reliability_score.toFixed(2) }}</UiBadge>
    </div>
    <p class="mt-1 text-sm text-slate-800">{{ row.claim_text }}</p>
    <p class="mt-1 text-xs text-slate-500">{{ row.entity }} · {{ row.effect_direction }} · {{ row.study_type }}</p>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import type { EvidenceRow } from '@/types/api'

const props = defineProps<{ row: EvidenceRow }>()
defineEmits<{ open: [] }>()

const highlight = computed(() => props.row.effect_direction?.toLowerCase().includes('contradict'))
</script>
