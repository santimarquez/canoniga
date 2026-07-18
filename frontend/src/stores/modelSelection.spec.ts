import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from '@/stores/app'

describe('modelSelection', () => {
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, String(value))
      },
      removeItem: (key: string) => {
        store.delete(key)
      },
      clear: () => store.clear(),
    })
    setActivePinia(createPinia())
  })

  it('defaults to auto and persists selection', () => {
    const app = useAppStore()
    expect(app.config.modelSelection).toBe('auto')
    app.setModelSelection('qwen2.5:14b')
    expect(app.config.modelSelection).toBe('qwen2.5:14b')
    expect(localStorage.getItem('als_model_selection')).toBe('qwen2.5:14b')
  })
})
