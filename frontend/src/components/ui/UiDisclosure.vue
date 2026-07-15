<template>
  <div class="rounded-lg border border-slate-200">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-semibold text-slate-900 hover:bg-slate-50"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="min-w-0 truncate">{{ title }}</span>
      <span
        class="material-symbols-outlined shrink-0 text-[20px] text-slate-500 transition-transform"
        :class="open ? 'rotate-180' : ''"
      >
        expand_more
      </span>
    </button>
    <div v-show="open" class="border-t border-slate-200 px-3 py-2">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    defaultOpen?: boolean
  }>(),
  {
    defaultOpen: false,
  },
)

const open = ref(props.defaultOpen)
</script>
