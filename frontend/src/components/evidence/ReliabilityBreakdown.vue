<template>
  <table class="w-full text-left text-xs">
    <thead>
      <tr class="text-slate-500">
        <th class="pb-1 font-medium">{{ t('app.db_breakdown_component') }}</th>
        <th class="pb-1 font-medium">{{ t('app.db_breakdown_raw') }}</th>
        <th class="pb-1 font-medium">{{ t('app.db_breakdown_weight') }}</th>
        <th class="pb-1 font-medium">{{ t('app.db_breakdown_contribution') }}</th>
      </tr>
    </thead>
    <tbody class="text-slate-800">
      <tr v-for="row in breakdown.rows" :key="row.key" class="border-t border-slate-100">
        <td class="py-1 pr-2">{{ componentLabel(row.key) }}</td>
        <td class="py-1 pr-2">{{ formatDecimal(row.component) }}</td>
        <td class="py-1 pr-2">{{ row.weight }}%</td>
        <td class="py-1">{{ formatPercent(row.contribution) }}</td>
      </tr>
      <tr class="border-t border-slate-200 font-semibold">
        <td class="py-1" colspan="3">{{ t('app.db_breakdown_total') }}</td>
        <td class="py-1">{{ formatPercent(breakdown.total) }}</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ReliabilityBreakdown } from '@/lib/reliability'

defineProps<{ breakdown: ReliabilityBreakdown }>()

const { t } = useI18n()

function componentLabel(key: string) {
  const labels: Record<string, string> = {
    study: t('app.db_breakdown_component_study'),
    sample: t('app.db_breakdown_component_sample'),
    replication: t('app.db_breakdown_component_replication'),
    peer_review: t('app.db_breakdown_component_peer_review'),
    endpoint: t('app.db_breakdown_component_endpoint'),
    source: t('app.db_breakdown_component_source'),
    extraction: t('app.db_breakdown_component_extraction'),
  }
  return labels[key] || key
}

function formatDecimal(value: number) {
  return value.toFixed(2)
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}
</script>
