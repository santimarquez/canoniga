<template>
  <UiSelect :id="id" :label="label" :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event as 'en' | 'es')">
    <option value="en">English</option>
    <option value="es">Español</option>
  </UiSelect>
</template>

<script setup lang="ts">
import UiSelect from '@/components/ui/UiSelect.vue'

defineProps<{ modelValue: 'en' | 'es'; label: string; id?: string }>()
defineEmits<{ 'update:modelValue': ['en' | 'es'] }>()
</script>
