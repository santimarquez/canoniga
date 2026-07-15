<template>
  <component
    :is="tag"
    :type="nativeType"
    class="inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60"
    :class="classes"
    :disabled="disabled || loading"
    v-bind="$attrs"
  >
    <span v-if="loading" class="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
    <slot />
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
    size?: 'sm' | 'md' | 'lg'
    loading?: boolean
    disabled?: boolean
    type?: 'button' | 'submit' | 'reset'
    tag?: 'button' | 'a'
  }>(),
  {
    variant: 'primary',
    size: 'md',
    loading: false,
    disabled: false,
    type: 'button',
    tag: 'button',
  },
)

const nativeType = computed(() => (props.tag === 'button' ? props.type : undefined))

const classes = computed(() => {
  const sizes = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2.5 text-sm',
    lg: 'px-5 py-3 text-base',
  }
  const variants = {
    primary: 'bg-brand-primary text-white hover:bg-brand-accent shadow-sm',
    secondary: 'bg-surface-container text-on-surface hover:bg-slate-200 border border-outline/30',
    ghost: 'bg-transparent text-brand-primary hover:bg-brand-primary/10',
    danger: 'bg-error text-white hover:bg-red-700',
  }
  return [sizes[props.size], variants[props.variant]]
})
</script>
