<template>
  <div class="flex flex-wrap gap-2" data-tutorial="report_actions">
    <UiButton data-tutorial="save_session" variant="secondary" size="sm" :disabled="!report" @click="save">
      <span class="material-symbols-outlined text-[18px]">bookmark</span>
      {{ t('app.save_session') }}
    </UiButton>
    <UiButton data-tutorial="export_summary" variant="secondary" size="sm" :disabled="!report" @click="downloadSummary">
      <span class="material-symbols-outlined text-[18px]">download</span>
      {{ t('app.export_summary') }}
    </UiButton>
    <UiButton data-tutorial="copy_citations" variant="secondary" size="sm" :disabled="!report" @click="copyCitations">
      <span class="material-symbols-outlined text-[18px]">content_copy</span>
      {{ t('app.copy_citations') }}
    </UiButton>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { exportSummary as exportSummaryApi, saveSession } from '@/api/app'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'
import { useToastStore } from '@/stores/toast'

const { t } = useI18n()
const app = useAppStore()
const toast = useToastStore()

const report = computed(() => app.lastReport)

async function save() {
  if (!report.value) return
  const sessionId = app.activeSessionId || crypto.randomUUID()
  await saveSession({
    session_id: sessionId,
    title: report.value.synthesis?.direct_answer?.slice(0, 80) || 'Session',
    question: app.messages.find((m) => m.role === 'user')?.content || '',
    report: report.value,
    messages: app.messages,
    filters: app.filters,
    evidence_claim_ids: report.value.evidence_rows.map((row) => row.claim_id),
  })
  app.activeSessionId = sessionId
  toast.push({ type: 'success', message: t('app.session_saved') })
}

async function downloadSummary() {
  if (!report.value) return
  const data = await exportSummaryApi({
    report: report.value,
    messages: app.messages,
  })
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'als-intel-summary.json'
  anchor.click()
  URL.revokeObjectURL(url)
}

async function copyCitations() {
  if (!report.value) return
  const lines = report.value.evidence_rows.map((row) => `${row.claim_id} ${row.source_doi}`)
  await navigator.clipboard.writeText(lines.join('\n'))
  toast.push({ type: 'success', message: t('app.citations_copied') })
}
</script>
