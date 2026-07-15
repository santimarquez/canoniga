import { onMounted, onUnmounted } from 'vue'
import { useStatusStore } from '@/stores/status'

export function useManualSync() {
  const status = useStatusStore()

  onMounted(() => {
    void status.refreshManualSync()
  })

  onUnmounted(() => {
    status.schedulePolling(false)
  })

  return status
}
