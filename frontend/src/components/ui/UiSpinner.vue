<template>
  <span class="material-symbols-outlined animate-spin text-brand-primary" :class="sizeClass">progress_activity</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ size?: 'sm' | 'md' | 'lg' }>(), { size: 'md' })
const sizeClass = computed(() => ({ sm: 'text-[16px]', md: 'text-[20px]', lg: 'text-[28px]' }[props.size]))
</script>
