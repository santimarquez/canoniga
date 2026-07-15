<template>
  <div class="h-2 overflow-hidden rounded-full bg-slate-200">
    <div class="h-full rounded-full bg-brand-primary transition-all duration-300" :style="{ width: `${clamped}%` }" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ value: number }>()
const clamped = computed(() => Math.max(0, Math.min(100, props.value)))
</script>
