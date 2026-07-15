<template>
  <div class="max-h-72 space-y-2 overflow-y-auto">
    <ManualSyncSourceRow
      v-for="source in sources"
      :key="source.source"
      :source="source"
      @trigger="triggerSource"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ManualSyncSourceRow from '@/components/db/ManualSyncSourceRow.vue'
import { useStatusStore } from '@/stores/status'

const status = useStatusStore()
const sources = computed(() => {
  const rows = [...(status.manualSync?.sources ?? [])]
  return rows.sort((a, b) => {
    const aTime = a.last_successful_at || a.last_attempt_at || ''
    const bTime = b.last_successful_at || b.last_attempt_at || ''
    return aTime.localeCompare(bTime)
  })
})

async function triggerSource(source: string) {
  try {
    await status.trigger({ source })
  } catch (err) {
    status.setFlash({
      type: 'error',
      message: err instanceof Error ? err.message : 'Sync failed',
    })
  }
}
</script>
