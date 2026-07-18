import { defineStore } from 'pinia'
import type { NoticeOptions, NoticeType } from '@/types/api'

export interface ToastItem {
  id: string
  type: NoticeType
  message: string
}

const DEFAULT_DURATION_MS = 5000

export const useToastStore = defineStore('toast', {
  state: () => ({
    items: [] as ToastItem[],
    timers: {} as Record<string, ReturnType<typeof setTimeout>>,
  }),
  actions: {
    push(options: NoticeOptions, durationMs = DEFAULT_DURATION_MS) {
      const id =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`
      this.items.push({
        id,
        type: options.type,
        message: options.message,
      })
      if (durationMs > 0) {
        this.timers[id] = setTimeout(() => {
          this.dismiss(id)
        }, durationMs)
      }
      return id
    },
    dismiss(id: string) {
      const timer = this.timers[id]
      if (timer) {
        clearTimeout(timer)
        delete this.timers[id]
      }
      this.items = this.items.filter((item) => item.id !== id)
    },
    clear() {
      for (const id of Object.keys(this.timers)) {
        clearTimeout(this.timers[id])
      }
      this.timers = {}
      this.items = []
    },
  },
})
