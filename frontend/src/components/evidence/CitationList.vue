<template>
  <ul v-if="items.length" class="space-y-2">
    <li
      v-for="item in items"
      :key="item.claim_id"
      class="rounded-lg border border-slate-200 px-3 py-2"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span class="font-mono text-xs font-medium text-brand-primary">{{ item.claim_id }}</span>
        <div class="flex items-center gap-2">
          <UiBadge :tone="directionTone(item.effect_direction)">{{ displayDirection(item.effect_direction) }}</UiBadge>
          <UiBadge tone="info">{{ formatScore(item.reliability_score) }}</UiBadge>
        </div>
      </div>
      <p class="mt-1 text-xs text-slate-600">
        <a
          v-if="citationUrl(item)"
          :href="citationUrl(item)"
          class="text-brand-primary hover:underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ item.source_doi }}
        </a>
        <span v-else>{{ item.source_doi || '—' }}</span>
      </p>
    </li>
  </ul>
  <p v-else class="text-xs text-slate-500">{{ t('app.lineage_no_rows') }}</p>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UiBadge from '@/components/ui/UiBadge.vue'
import { buildSourceUrl } from '@/lib/sourceUrl'
import type { LineageCitation } from '@/types/api'

defineProps<{ items: LineageCitation[] }>()

const { t } = useI18n()

function citationUrl(item: LineageCitation) {
  if (!item.source_doi) return ''
  return buildSourceUrl({ claim_id: item.claim_id, source_doi: item.source_doi })
}

function formatScore(score: number | undefined) {
  return `${Math.round((score || 0) * 100)}%`
}

function displayDirection(direction: string | undefined) {
  const value = String(direction || '').trim()
  return value || '—'
}

function directionTone(direction: string | undefined): 'success' | 'danger' | 'warning' | 'neutral' {
  const value = displayDirection(direction).toLowerCase()
  if (value.includes('support')) return 'success'
  if (value.includes('contradict')) return 'danger'
  if (value === 'neutral') return 'neutral'
  return 'warning'
}
</script>
