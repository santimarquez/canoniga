<template>
  <div ref="root" class="relative inline-block">
    <slot name="trigger" :toggle="toggle" :open="open" />
    <div
      v-if="open"
      class="absolute z-40 mt-2 min-w-[280px] rounded-xl border border-slate-200 bg-white p-4 shadow-xl"
      :class="alignClass"
    >
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = withDefaults(defineProps<{ align?: 'left' | 'right' }>(), { align: 'right' })
const open = ref(false)
const root = ref<HTMLElement | null>(null)

const alignClass = computed(() => (props.align === 'left' ? 'left-0' : 'right-0'))

function toggle() {
  open.value = !open.value
}

function close() {
  open.value = false
}

function onDocumentClick(event: MouseEvent) {
  if (!open.value || !root.value) return
  if (!root.value.contains(event.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))

defineExpose({ toggle, close, open })
</script>
