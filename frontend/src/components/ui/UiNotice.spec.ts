import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import UiNotice from '@/components/ui/UiNotice.vue'

describe('UiNotice', () => {
  it('renders error notice text', () => {
    const wrapper = mount(UiNotice, {
      props: { type: 'error', message: 'Sync failed' },
    })
    expect(wrapper.text()).toContain('Sync failed')
    expect(wrapper.classes().join(' ')).toContain('text-red-800')
  })
})
