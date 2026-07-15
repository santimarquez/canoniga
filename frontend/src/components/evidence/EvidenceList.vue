<template>
  <div class="max-h-[480px] space-y-2 overflow-y-auto">
    <EvidenceRow
      v-for="row in rows"
      :key="row.claim_id"
      :row="row"
      @open="$emit('open', row.claim_id)"
    />
  </div>
</template>

<script setup lang="ts">
import EvidenceRow from '@/components/evidence/EvidenceRow.vue'
import type { EvidenceRow as EvidenceRowType } from '@/types/api'

defineProps<{ rows: EvidenceRowType[] }>()
defineEmits<{ open: [claimId: string] }>()
</script>
