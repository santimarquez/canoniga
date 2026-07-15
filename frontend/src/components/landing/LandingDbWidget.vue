<template>
  <section id="database" class="mx-auto max-w-container-max scroll-mt-24 px-4 py-16 md:px-8">
    <p class="text-xs font-semibold uppercase tracking-widest text-brand-primary">{{ t('landing.database.badge') }}</p>
    <h2 class="mt-2 text-3xl font-semibold text-slate-900">{{ t('landing.database.title') }}</h2>
    <p class="mt-3 max-w-3xl text-slate-600">{{ t('landing.database.body') }}</p>
    <div class="mt-8 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex items-center justify-between">
        <h3 class="font-semibold text-slate-900">{{ t('landing.database.status_title') }}</h3>
        <span class="text-sm text-slate-500">{{ updatedLabel }}</span>
      </div>
      <p class="mt-4 text-3xl font-semibold text-brand-primary">{{ totalLabel }}</p>
      <p class="text-sm text-slate-600">{{ t('landing.database.nodes_label') }}</p>
      <div class="mt-4 space-y-2">
        <div v-for="row in sources" :key="row.source" class="flex items-center gap-3 text-sm">
          <span class="w-28 truncate text-slate-600">{{ row.source }}</span>
          <div class="h-2 flex-1 rounded bg-slate-200"><div class="h-2 rounded bg-brand-primary" :style="{ width: barWidth(row.articles) }" /></div>
          <span>{{ row.articles }}</span>
        </div>
      </div>
      <p class="mt-4 text-sm text-slate-500">{{ stateLabel }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchStatus } from '@/api/auth'
import type { StatusResponse } from '@/types/api'

const { t } = useI18n()
const status = ref<StatusResponse | null>(null)

const sources = computed(() => status.value?.source_breakdown ?? [])
const totalLabel = computed(() => String(status.value?.records_total ?? '-'))
const updatedLabel = computed(() => status.value?.latest_sync_at || t('landing.database.checking'))
const stateLabel = computed(() =>
  (status.value?.records_total ?? 0) > 0 ? t('landing.database.ready') : t('landing.database.waiting'),
)

function barWidth(articles: number) {
  const max = Math.max(...sources.value.map((row) => row.articles), 1)
  return `${Math.round((articles / max) * 100)}%`
}

onMounted(async () => {
  status.value = await fetchStatus()
})
</script>
