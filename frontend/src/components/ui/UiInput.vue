<template>
  <label class="block text-sm">
    <span v-if="label" class="mb-1 block font-medium text-slate-700">
      <UiFieldHelp v-if="labelHelp" :text="labelHelp">{{ label }}</UiFieldHelp>
      <span v-else>{{ label }}</span>
    </span>
    <input
      :id="id"
      v-bind="$attrs"
      :value="modelValue"
      :readonly="readonly"
      class="w-full rounded-lg border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2"
      :class="inputClass"
      @input="onInput"
    />
    <span v-if="hint" class="mt-1 block text-xs text-slate-500">{{ hint }}</span>
  </label>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UiFieldHelp from '@/components/ui/UiFieldHelp.vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    label?: string
    labelHelp?: string
    hint?: string
    id?: string
    readonly?: boolean
  }>(),
  {
    readonly: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [string | number] }>()

const inputClass = computed(() =>
  props.readonly
    ? 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-600 focus:ring-0'
    : 'border-slate-300 bg-white text-slate-900 focus:border-brand-primary focus:ring-brand-primary/20',
)

function onInput(event: Event) {
  if (props.readonly) return
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>

<script lang="ts">
export default {
  inheritAttrs: false,
}
</script>
