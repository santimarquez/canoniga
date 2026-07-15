<template>
  <div
    v-if="message"
    class="notice flex items-start gap-2 rounded-lg px-3 py-2 text-sm"
    :class="noticeClass"
    role="status"
  >
    <span class="material-symbols-outlined text-[18px]">{{ icon }}</span>
    <span class="flex-1">{{ message }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NoticeType } from '@/types/api'

const props = withDefaults(
  defineProps<{
    type?: NoticeType
    message?: string
  }>(),
  { type: 'info', message: '' },
)

const noticeClass = computed(() => {
  const map: Record<NoticeType, string> = {
    error: 'bg-red-50 text-red-800 border border-red-200',
    success: 'bg-emerald-50 text-emerald-800 border border-emerald-200',
    info: 'bg-blue-50 text-blue-900 border border-blue-200',
    warning: 'bg-amber-50 text-amber-900 border border-amber-200',
  }
  return map[props.type]
})

const icon = computed(() => {
  const map: Record<NoticeType, string> = {
    error: 'error',
    success: 'check_circle',
    info: 'info',
    warning: 'warning',
  }
  return map[props.type]
})
</script>
