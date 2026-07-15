<template>
  <label class="block text-sm">
    <span v-if="label" class="mb-1 block font-medium text-slate-700">{{ label }}</span>
    <select
      :id="id"
      :value="modelValue"
      :disabled="disabled"
      class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 transition-colors focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/20 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
      @change="onChange"
    >
      <slot />
    </select>
    <span v-if="hint" class="mt-1 block text-xs text-slate-500">{{ hint }}</span>
  </label>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string | number
  label?: string
  hint?: string
  id?: string
  disabled?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [string | number] }>()

function onChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:modelValue', target.value)
}
</script>
