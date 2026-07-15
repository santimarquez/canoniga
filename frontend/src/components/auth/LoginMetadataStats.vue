<template>
  <div class="rounded-lg border border-slate-200 bg-white/90 p-4 shadow-sm backdrop-blur-sm">
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-semibold uppercase tracking-widest text-slate-800">{{ t('login.db_status') }}</h3>
      <span class="text-[11px] text-slate-600">{{ updatedLabel }}</span>
    </div>
    <div class="mt-2 flex items-baseline gap-2">
      <span class="text-xl font-semibold text-brand-primary">{{ metadata?.records_total ?? '-' }}</span>
      <span class="text-xs text-slate-600">{{ t('login.db_total_nodes') }}</span>
    </div>
    <div class="mt-3 space-y-2">
      <div v-for="row in metadata?.source_breakdown ?? []" :key="row.source" class="flex items-center gap-2 text-xs">
        <span class="w-24 truncate text-slate-600">{{ row.source }}</span>
        <div class="h-2 flex-1 rounded bg-slate-200">
          <div class="h-2 rounded bg-brand-primary" :style="{ width: barWidth(row.articles) }" />
        </div>
        <span class="w-10 text-right text-slate-500">{{ row.articles }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchLoginMetadata } from '@/api/auth'
import { formatRelativeTime } from '@/i18n/time'
import type { LoginMetadataResponse } from '@/types/api'

const { t } = useI18n()
const metadata = ref<LoginMetadataResponse | null>(null)

const updatedLabel = computed(() => {
  const stamp = metadata.value?.latest_sync_at
  return stamp ? t('login.db_last_updated', { time: formatRelativeTime(stamp) }) : t('login.db_checking')
})

function barWidth(articles: number) {
  const max = Math.max(...(metadata.value?.source_breakdown ?? []).map((row) => row.articles), 1)
  return `${Math.round((articles / max) * 100)}%`
}

onMounted(async () => {
  metadata.value = await fetchLoginMetadata()
})
</script>
