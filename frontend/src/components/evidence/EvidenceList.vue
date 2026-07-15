<template>
  <div class="max-h-[480px] space-y-2 overflow-y-auto">
    <EvidenceRow
      v-for="row in displayRows"
      :key="row.claim_id"
      :row="row"
      :highlight-contradictions="highlightContradictions"
      @open="$emit('open', row.claim_id)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import EvidenceRow from '@/components/evidence/EvidenceRow.vue'
import type { EvidenceRow as EvidenceRowType } from '@/types/api'

const props = defineProps<{
  rows: EvidenceRowType[]
  highlightContradictions?: boolean
}>()

defineEmits<{ open: [claimId: string] }>()

const displayRows = computed(() => {
  if (!props.highlightContradictions) return props.rows
  return [...props.rows].sort((a, b) => {
    const aContradicts = a.effect_direction?.toLowerCase().includes('contradict') ? 0 : 1
    const bContradicts = b.effect_direction?.toLowerCase().includes('contradict') ? 0 : 1
    if (aContradicts !== bContradicts) return aContradicts - bContradicts
    return (b.reliability_score || 0) - (a.reliability_score || 0)
  })
})
</script>
