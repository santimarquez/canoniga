<template>
  <div class="space-y-2">
    <p v-if="rows.length === 0" class="text-xs text-slate-500">{{ emptyLabel }}</p>
    <div v-for="row in rows" :key="row.source" class="flex items-center gap-2 text-xs">
      <span class="w-24 truncate text-slate-600" :title="row.source">{{ row.source }}</span>
      <div class="h-2 flex-1 rounded bg-slate-200">
        <div class="h-2 rounded bg-brand-primary" :style="{ width: barWidth(row.articles) }" />
      </div>
      <span class="w-10 text-right tabular-nums text-slate-500">{{ formatCompactCount(row.articles) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatCompactCount } from '@/i18n/numbers'
import type { SourceBreakdownRow } from '@/types/api'

const props = withDefaults(
  defineProps<{
    rows: SourceBreakdownRow[]
    emptyLabel?: string
  }>(),
  {
    emptyLabel: '',
  },
)

const maxArticles = computed(() => Math.max(...props.rows.map((row) => row.articles), 1))

function barWidth(articles: number) {
  return `${Math.round((articles / maxArticles.value) * 100)}%`
}
</script>
