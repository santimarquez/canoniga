<template>
  <label class="flex flex-col gap-1 text-sm">
    <span class="font-medium text-slate-700">{{ label }}</span>
    <select
      class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
      :value="modelValue"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value as 'en' | 'es')"
    >
      <option value="en">English</option>
      <option value="es">Español</option>
    </select>
  </label>
</template>

<script setup lang="ts">
defineProps<{ modelValue: 'en' | 'es'; label: string }>()
defineEmits<{ 'update:modelValue': ['en' | 'es'] }>()
</script>
