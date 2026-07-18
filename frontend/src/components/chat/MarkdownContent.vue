<template>
  <div
    class="md-content"
    :class="{ 'streaming-cursor': showCursor }"
    v-html="html"
  />
</template>

<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    content: string
    showCursor?: boolean
  }>(),
  {
    showCursor: false,
  },
)

marked.setOptions({
  gfm: true,
  breaks: true,
})

const html = computed(() => {
  const source = props.content || ''
  if (!source.trim()) return ''
  const raw = marked.parse(source, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true },
  })
})
</script>
