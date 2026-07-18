import { defineStore } from 'pinia'
import { fetchStatus } from '@/api/auth'
import { fetchManualSyncStatus, triggerManualSync } from '@/api/app'
import { useAppStore } from '@/stores/app'
import { useToastStore } from '@/stores/toast'
import type { ManualSyncStatusResponse, NoticeOptions, StatusResponse } from '@/types/api'

function syncSucceeded(data: ManualSyncStatusResponse, scope: string | null): boolean {
  if (data.last_completion_status === 'success') return true
  if (data.last_completion_status === 'failed') return false
  if (data.error) return false
  if (!scope) return false
  if (scope === 'all') return false
  const source = data.sources?.find((row) => row.source === scope)
  if (!source) return false
  return source.sync_status === 'ok' && source.last_attempt_status === 'ok'
}

export const useStatusStore = defineStore('status', {
  state: () => ({
    snapshot: null as StatusResponse | null,
    manualSync: null as ManualSyncStatusResponse | null,
    pollTimer: null as ReturnType<typeof setInterval> | null,
    wasActive: false,
    pendingScope: null as string | null,
    configSeeded: false,
  }),
  actions: {
    applyServerConfig(data: StatusResponse) {
      const app = useAppStore()
      app.setConfig({
        model: data.model,
        host: data.host,
        contextLimit: data.context_limit,
        temperature: data.temperature,
        timeoutSeconds: data.timeout_seconds,
      })
      this.configSeeded = true
    },
    async refresh() {
      const data = await fetchStatus()
      this.snapshot = data
      this.manualSync = data.manual_sync
      if (!this.configSeeded) {
        this.applyServerConfig(data)
      }
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
          if (syncSucceeded(data, this.pendingScope)) {
            this.setFlash({ type: 'success', message: 'sync_completed' })
          } else {
            const message = data.last_completion_error || data.error || 'sync_failed'
            this.setFlash({ type: 'error', message })
          }
          this.pendingScope = null
          // Refresh totals + per-source breakdown after sync finishes.
          await this.refresh()
        }
        this.wasActive = false
      }
      return data
    },
    async trigger(payload: { scope: 'all' } | { source: string }) {
      this.pendingScope = 'scope' in payload ? payload.scope : payload.source
      this.wasActive = true
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
      useToastStore().push(options)
    },
    clearFlash() {
      useToastStore().clear()
    },
  },
})
