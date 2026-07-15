<template>
  <div>
    <h3 class="mb-2 text-sm font-semibold text-slate-900">{{ t('app.diagnostics_title') }}</h3>
    <ul class="space-y-1 text-xs text-slate-600">
      <li v-for="row in telemetry" :key="row.trace_id">
        {{ row.mode }} · {{ row.status }} · {{ row.total_seconds ?? '—' }}s
      </li>
    </ul>
    <h3 class="mb-2 mt-4 text-sm font-semibold text-slate-900">{{ t('app.failure_atlas_title') }}</h3>
    <ul class="space-y-1 text-xs text-slate-600">
      <li v-for="row in failures" :key="row.source">{{ row.source }} · {{ row.failure_count }}</li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchFailureAtlas, fetchRecentTelemetry } from '@/api/app'
import type { FailureAtlasRow, TelemetryRow } from '@/types/api'

const { t } = useI18n()
const telemetry = ref<TelemetryRow[]>([])
const failures = ref<FailureAtlasRow[]>([])

onMounted(async () => {
  const [recent, atlas] = await Promise.all([fetchRecentTelemetry(), fetchFailureAtlas()])
  telemetry.value = recent.rows ?? []
  failures.value = atlas.rows ?? []
})
</script>
