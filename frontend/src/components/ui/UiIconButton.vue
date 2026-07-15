<template>
  <button
    type="button"
    class="inline-flex items-center justify-center rounded-lg p-2 text-on-surface hover:bg-surface-container disabled:opacity-50"
    :disabled="disabled"
    v-bind="$attrs"
  >
    <span class="material-symbols-outlined text-[20px]"><slot /></span>
  </button>
</template>

<script setup lang="ts">
defineProps<{ disabled?: boolean }>()
</script>
