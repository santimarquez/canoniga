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
    <div
      class="disclosure-expand grid border-t border-slate-200 transition-[grid-template-rows,opacity] duration-200 ease-out"
      :class="isOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0 border-t-transparent'"
    >
      <div class="disclosure-expand-inner overflow-hidden">
        <div class="px-3 py-2">
          <slot />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  defaultOpen: { type: Boolean, default: false },
  // default undefined avoids Boolean casting of a missing prop to false
  open: { type: Boolean, default: undefined },
})

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const uncontrolledOpen = ref(props.defaultOpen)
const isControlled = computed(() => props.open !== undefined)

watch(
  () => props.open,
  (value) => {
    if (value !== undefined) uncontrolledOpen.value = value
  },
)

const isOpen = computed(() => (isControlled.value ? Boolean(props.open) : uncontrolledOpen.value))

function toggle() {
  const next = !isOpen.value
  if (!isControlled.value) {
    uncontrolledOpen.value = next
  }
  emit('update:open', next)
}
</script>
