<template>
  <div class="flex min-w-0 items-center gap-1.5 text-xs text-slate-600">
    <span class="material-symbols-outlined shrink-0 text-[16px] text-brand-primary">smart_toy</span>
    <span class="max-w-[7rem] truncate sm:max-w-[11rem]">{{ modelLabel }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { useStatusStore } from '@/stores/status'

const app = useAppStore()
const status = useStatusStore()

const modelLabel = computed(() => status.snapshot?.model || app.config.model)
</script>
