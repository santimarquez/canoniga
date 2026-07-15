<template>
  <div class="block text-sm">
    <div class="flex items-baseline justify-between gap-3">
      <span :id="labelId" class="font-medium text-slate-700">{{ label }}</span>
      <span class="shrink-0 font-mono text-sm font-semibold text-brand-primary">{{ displayValue }}</span>
    </div>
    <p v-if="help" class="mt-1 text-xs leading-relaxed text-slate-500">{{ help }}</p>
    <input
      :id="id"
      v-model.number="localValue"
      type="range"
      class="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-brand-primary"
      :min="min"
      :max="max"
      :step="step"
      :aria-labelledby="labelId"
      @input="onInput"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    id?: string
    label: string
    help?: string
    modelValue: number
    min?: number
    max?: number
    step?: number
    format?: (value: number) => string
  }>(),
  {
    min: 0,
    max: 100,
    step: 1,
  },
)

const emit = defineEmits<{ 'update:modelValue': [number] }>()

const labelId = computed(() => (props.id ? `${props.id}-label` : undefined))

const localValue = computed({
  get: () => props.modelValue,
  set: (value: number) => emit('update:modelValue', value),
})

const displayValue = computed(() => {
  if (props.format) return props.format(props.modelValue)
  return String(props.modelValue)
})

function onInput(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', Number(target.value))
}
</script>
