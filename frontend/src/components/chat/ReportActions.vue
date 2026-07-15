<template>
  <div class="flex flex-wrap gap-2">
    <UiButton variant="secondary" size="sm" :disabled="!report" @click="save">{{ t('app.save_session') }}</UiButton>
    <UiButton variant="secondary" size="sm" :disabled="!report" @click="downloadSummary">{{ t('app.export_summary') }}</UiButton>
    <UiButton variant="secondary" size="sm" :disabled="!report" @click="copyCitations">{{ t('app.copy_citations') }}</UiButton>
    <UiNotice v-if="message" class="w-full" :type="noticeType" :message="message" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { exportSummary as exportSummaryApi, saveSession } from '@/api/app'
import UiButton from '@/components/ui/UiButton.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import { useAppStore } from '@/stores/app'
import type { NoticeType } from '@/types/api'

const { t } = useI18n()
const app = useAppStore()
const message = ref('')
const noticeType = ref<NoticeType>('info')

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
  message.value = t('app.session_saved')
  noticeType.value = 'success'
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
  message.value = t('app.citations_copied')
  noticeType.value = 'success'
}
</script>
