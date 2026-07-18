import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useToastStore } from '@/stores/toast'

describe('useToastStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('auto-dismisses toasts after 5 seconds', () => {
    const toast = useToastStore()
    toast.push({ type: 'success', message: 'session_saved' })
    expect(toast.items).toHaveLength(1)

    vi.advanceTimersByTime(4999)
    expect(toast.items).toHaveLength(1)

    vi.advanceTimersByTime(1)
    expect(toast.items).toHaveLength(0)
  })

  it('dismisses a toast early', () => {
    const toast = useToastStore()
    const id = toast.push({ type: 'info', message: 'filters_reset' })
    toast.dismiss(id)
    expect(toast.items).toHaveLength(0)
  })
})
