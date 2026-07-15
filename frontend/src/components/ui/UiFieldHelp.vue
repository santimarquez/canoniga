<template>
  <span
    class="cursor-help underline decoration-dotted decoration-slate-300/0 underline-offset-2 transition-colors hover:decoration-slate-300/90"
    :title="text"
    :aria-label="text"
    tabindex="0"
  >
    <slot />
  </span>
</template>

<script setup lang="ts">
defineProps<{ text: string }>()
</script>
