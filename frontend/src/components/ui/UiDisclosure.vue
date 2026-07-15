<template>
  <div class="rounded-lg border border-slate-200">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-semibold text-slate-900 hover:bg-slate-50"
      :aria-expanded="isOpen"
      @click="toggle"
    >
      <span class="min-w-0 truncate">{{ title }}</span>
      <span
        class="material-symbols-outlined shrink-0 text-[20px] text-slate-500 transition-transform"
        :class="isOpen ? 'rotate-180' : ''"
      >
        expand_more
      </span>
    </button>
    <div v-show="isOpen" class="border-t border-slate-200 px-3 py-2">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    defaultOpen?: boolean
    open?: boolean
  }>(),
  {
    defaultOpen: false,
  },
)

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const internalOpen = ref(props.defaultOpen)

watch(
  () => props.open,
  (value) => {
    if (value !== undefined) internalOpen.value = value
  },
)

const isOpen = computed({
  get: () => (props.open !== undefined ? props.open : internalOpen.value),
  set: (value: boolean) => {
    internalOpen.value = value
    emit('update:open', value)
  },
})

function toggle() {
  isOpen.value = !isOpen.value
}
</script>
