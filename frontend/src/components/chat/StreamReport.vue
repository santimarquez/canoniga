<template>
  <article class="rounded-xl border border-slate-200 bg-slate-50 p-4">
    <div v-if="app.streaming && app.streamStatus" class="mb-3 flex items-center gap-2 text-sm text-slate-600">
      <UiSpinner size="sm" />
      <span>{{ app.streamStatus }}</span>
    </div>
    <div v-if="content" class="prose prose-sm max-w-none whitespace-pre-wrap text-slate-800">{{ content }}</div>
    <p v-else class="text-sm text-slate-500">{{ t('app.report_placeholder') }}</p>
    <div v-if="report" class="mt-4 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
      <span>{{ t('app.report_evidence_count', { count: report.evidence_count }) }}</span>
      <span>{{ t('app.report_model', { model: report.model }) }}</span>
      <span>{{ t('app.generated_in', { seconds: report.generated_seconds }) }}</span>
    </div>
    <div v-if="report?.synthesis?.direct_answer" class="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm text-blue-950">
      <h3 class="font-semibold">{{ t('app.direct_answer') }}</h3>
      <p class="mt-1">{{ report.synthesis.direct_answer }}</p>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()

const report = computed(() => app.lastReport)
const content = computed(() => app.streaming ? app.streamAnswer : report.value?.answer || app.streamAnswer)
</script>
