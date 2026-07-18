import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MarkdownContent from '@/components/chat/MarkdownContent.vue'

describe('MarkdownContent', () => {
  it('renders markdown headings and lists', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: '## Direct Answer\n\n- item one',
      },
    })

    expect(wrapper.html()).toContain('<h2>')
    expect(wrapper.html()).toContain('Direct Answer')
    expect(wrapper.html()).toContain('<li>')
  })

  it('sanitizes unsafe html', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: '<script>alert(1)</script>**safe**',
      },
    })

    expect(wrapper.html()).not.toContain('<script')
    expect(wrapper.html()).toContain('safe')
  })

  it('adds streaming cursor class when requested', () => {
    const wrapper = mount(MarkdownContent, {
      props: {
        content: 'typing',
        showCursor: true,
      },
    })

    expect(wrapper.classes()).toContain('streaming-cursor')
  })
})
