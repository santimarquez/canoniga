import { defineStore } from 'pinia'
import { fetchStatus } from '@/api/auth'
import { fetchManualSyncStatus, triggerManualSync } from '@/api/app'
import type { ManualSyncStatusResponse, NoticeOptions, StatusResponse } from '@/types/api'

export const useStatusStore = defineStore('status', {
  state: () => ({
    snapshot: null as StatusResponse | null,
    manualSync: null as ManualSyncStatusResponse | null,
    pollTimer: null as ReturnType<typeof setInterval> | null,
    wasActive: false,
    flash: null as NoticeOptions | null,
    flashTimer: null as ReturnType<typeof setTimeout> | null,
  }),
  actions: {
    async refresh() {
      const data = await fetchStatus()
      this.snapshot = data
      this.manualSync = data.manual_sync
      return data
    },
    async refreshManualSync() {
      const data = await fetchManualSyncStatus()
      const completed = this.wasActive && !data.manual_sync_active && !data.in_progress
      this.manualSync = data
      if (data.manual_sync_active || data.in_progress) {
        this.wasActive = true
        this.schedulePolling(true)
      } else {
        this.schedulePolling(false)
        if (completed) {
          this.setFlash({ type: 'success', message: 'sync_completed' })
        }
        this.wasActive = false
      }
      return data
    },
    async trigger(payload: { scope: 'all' } | { source: string }) {
      await triggerManualSync(payload)
      await this.refreshManualSync()
    },
    schedulePolling(active: boolean) {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
      if (active) {
        this.pollTimer = setInterval(() => {
          void this.refreshManualSync()
        }, 2000)
      }
    },
    setFlash(options: NoticeOptions) {
      this.flash = options
      if (this.flashTimer) clearTimeout(this.flashTimer)
      this.flashTimer = setTimeout(() => {
        this.flash = null
        this.flashTimer = null
      }, 8000)
    },
    clearFlash() {
      this.flash = null
      if (this.flashTimer) clearTimeout(this.flashTimer)
      this.flashTimer = null
    },
  },
})
