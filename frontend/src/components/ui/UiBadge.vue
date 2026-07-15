<template>
  <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium" :class="classes">
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' }>(), {
  tone: 'neutral',
})

const classes = computed(() => {
  const map = {
    neutral: 'bg-slate-100 text-slate-700',
    success: 'bg-emerald-100 text-emerald-800',
    warning: 'bg-amber-100 text-amber-900',
    danger: 'bg-red-100 text-red-800',
    info: 'bg-blue-100 text-blue-900',
  }
  return map[props.tone]
})
</script>
