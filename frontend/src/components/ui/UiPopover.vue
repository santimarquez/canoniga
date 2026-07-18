<template>
  <div ref="root" class="relative inline-block">
    <slot name="trigger" :toggle="toggle" :open="open" />
    <Transition name="panel-scale">
      <div
        v-if="open"
        class="absolute z-40 rounded-xl border border-slate-200 bg-white shadow-xl"
        :class="[alignClass, sideClass, panelClass, originClass]"
      >
        <slot />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{ align?: 'left' | 'right'; side?: 'top' | 'bottom'; panelClass?: string }>(),
  {
    align: 'right',
    side: 'bottom',
    panelClass: 'min-w-[280px] p-4',
  },
)
const open = ref(false)
const root = ref<HTMLElement | null>(null)

const alignClass = computed(() => (props.align === 'left' ? 'left-0' : 'right-0'))
const sideClass = computed(() => (props.side === 'top' ? 'bottom-full mb-2' : 'top-full mt-2'))
const originClass = computed(() => {
  if (props.side === 'top') {
    return props.align === 'left' ? 'origin-bottom-left' : 'origin-bottom-right'
  }
  return props.align === 'left' ? 'origin-top-left' : 'origin-top-right'
})

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
