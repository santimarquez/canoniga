import { onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

export function useAuthRefresh(intervalMs = 60_000) {
  const auth = useAuthStore()
  const timer = ref<ReturnType<typeof setInterval> | null>(null)

  onMounted(async () => {
    await auth.refresh()
    timer.value = setInterval(() => {
      void auth.refresh()
    }, intervalMs)
  })

  onUnmounted(() => {
    if (timer.value) clearInterval(timer.value)
  })

  return auth
}
