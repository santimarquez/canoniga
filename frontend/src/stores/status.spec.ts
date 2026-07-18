import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useStatusStore } from '@/stores/status'
import type { ManualSyncStatusResponse, StatusResponse } from '@/types/api'

vi.mock('@/api/auth', () => ({
  fetchStatus: vi.fn(),
}))

vi.mock('@/api/app', () => ({
  fetchManualSyncStatus: vi.fn(),
  triggerManualSync: vi.fn(),
}))

vi.mock('@/stores/toast', () => ({
  useToastStore: () => ({
    push: vi.fn(),
    clear: vi.fn(),
  }),
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => ({
    setConfig: vi.fn(),
  }),
}))

import { fetchStatus } from '@/api/auth'
import { fetchManualSyncStatus } from '@/api/app'

const idleManualSync: ManualSyncStatusResponse = {
  can_trigger_all: true,
  can_trigger: true,
  cooldown_remaining_seconds: 0,
  next_available_at: null,
  in_progress: false,
  manual_sync_active: false,
  current_scope: null,
  current_source: null,
  completed_sources: 0,
  total_sources: 0,
  progress_percent: 0,
  estimated_remaining_seconds: null,
  estimated_completion_at: null,
  sources: [],
  error: null,
  last_completion_status: 'success',
  last_completion_error: null,
  last_completion_at: null,
  last_completion_scope: 'all',
}

const statusPayload: StatusResponse = {
  records_total: 42,
  avg_reliability: 0.7,
  supports_count: 20,
  contradicts_count: 5,
  review_flags_count: 0,
  model: 'test',
  host: 'http://localhost',
  context_limit: 20,
  temperature: 0.1,
  timeout_seconds: 60,
  db_synced: true,
  source_breakdown: [{ source: 'pubmed', articles: 42 }],
  latest_sync_at: '2026-07-18T00:00:00+00:00',
  manual_sync: idleManualSync as unknown as StatusResponse['manual_sync'],
}

describe('useStatusStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(fetchStatus).mockReset()
    vi.mocked(fetchManualSyncStatus).mockReset()
  })

  it('refreshes totals after a manual sync completes', async () => {
    vi.mocked(fetchManualSyncStatus).mockResolvedValue(idleManualSync)
    vi.mocked(fetchStatus).mockResolvedValue(statusPayload)

    const status = useStatusStore()
    status.wasActive = true
    status.pendingScope = 'all'
    status.snapshot = {
      ...statusPayload,
      records_total: 10,
      source_breakdown: [{ source: 'pubmed', articles: 10 }],
    }

    await status.refreshManualSync()

    expect(fetchStatus).toHaveBeenCalledTimes(1)
    expect(status.snapshot?.records_total).toBe(42)
    expect(status.snapshot?.source_breakdown).toEqual([{ source: 'pubmed', articles: 42 }])
  })

  it('does not refresh totals while sync is still active', async () => {
    vi.mocked(fetchManualSyncStatus).mockResolvedValue({
      ...idleManualSync,
      manual_sync_active: true,
      in_progress: true,
      last_completion_status: null,
    })

    const status = useStatusStore()
    status.wasActive = true
    await status.refreshManualSync()

    expect(fetchStatus).not.toHaveBeenCalled()
    status.schedulePolling(false)
  })
})
