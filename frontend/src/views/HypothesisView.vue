<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4">
    <div class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold text-slate-900">{{ t('app.hypothesis_queue') }}</h2>
      <UiButton variant="secondary" size="sm" :loading="loading" @click="load">{{ t('app.refresh') }}</UiButton>
    </div>
    <label class="mb-4 flex items-center gap-2 text-sm">
      <input v-model="requireSignoff" type="checkbox" />
      <span>{{ t('app.require_review_signoff') }}</span>
    </label>
    <div v-if="rows.length === 0" class="text-sm text-slate-500">{{ t('app.no_hypotheses') }}</div>
    <div class="space-y-3">
      <article v-for="item in rows" :key="item.entity" class="rounded-lg border border-slate-200 p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="font-semibold text-slate-900">{{ item.entity }}</h3>
            <p class="mt-1 text-sm text-slate-700">{{ item.hypothesis }}</p>
          </div>
          <UiBadge tone="info">{{ item.priority_score.toFixed(2) }}</UiBadge>
        </div>
        <p class="mt-2 text-xs text-slate-500">{{ item.biological_rationale }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchHypothesisQueue } from '@/api/app'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'
import type { HypothesisQueueItem } from '@/types/api'

const { t } = useI18n()
const app = useAppStore()
const rows = ref<HypothesisQueueItem[]>([])
const loading = ref(false)
const requireSignoff = ref(true)

async function load() {
  loading.value = true
  try {
    const data = await fetchHypothesisQueue({
      limit: app.hypothesisLimit,
      require_review_signoff: requireSignoff.value,
      enforce_causal_gate: true,
    })
    rows.value = data.queue
    app.hypothesisRows = data.queue
    app.hypothesisRemovedEntities = data.removed_entities
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

watch(requireSignoff, () => {
  void load()
})
</script>
