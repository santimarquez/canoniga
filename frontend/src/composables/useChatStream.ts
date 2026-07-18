import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { chatSync, streamChat } from '@/api/chat'
import { isStreamPhase, isTimeoutError } from '@/composables/chatStreamPhases'
import { tutorialSignal } from '@/composables/useTutorial'
import { useAppStore } from '@/stores/app'
import type { ChatReport, ChatStreamEvent } from '@/types/api'

let doneTimer: ReturnType<typeof setTimeout> | null = null

export function useChatStream() {
  const { t } = useI18n()
  const app = useAppStore()
  const error = ref('')
  const info = ref('')

  function clearDoneTimer() {
    if (doneTimer) {
      clearTimeout(doneTimer)
      doneTimer = null
    }
  }

  function resetStreamState() {
    clearDoneTimer()
    app.streamPhase = 'loading_evidence'
    app.streamEvidenceCount = null
    app.streamCitedCount = null
    app.streamDoneVisible = false
    app.streamAnswer = ''
    app.streamStatus = ''
  }

  function showDoneBanner(citedCount: number) {
    app.streamCitedCount = citedCount
    app.streamDoneVisible = true
    clearDoneTimer()
    doneTimer = setTimeout(() => {
      app.streamDoneVisible = false
    }, 3000)
  }

  function formatError(err: unknown): string {
    const message = err instanceof Error ? err.message : 'Chat failed'
    if (isTimeoutError(message)) return t('app.llm_timeout_hint')
    return message
  }

  async function send(question: string) {
    error.value = ''
    info.value = ''
    app.messages.push({ role: 'user', content: question })
    app.streaming = true
    resetStreamState()

    const body = {
      messages: app.messages,
      db_path: app.config.dbPath,
      host: app.config.host,
      model: app.config.modelSelection || 'auto',
      context_limit: app.config.contextLimit,
      temperature: app.config.temperature,
      timeout_seconds: app.config.timeoutSeconds,
      language: app.language,
      filters: app.filters,
    }

    try {
      let finalReport: ChatReport | null = null
      let usedFallback = false
      try {
        for await (const event of streamChat(body)) {
          handleEvent(event)
          if (event.type === 'final') finalReport = event
          if (event.type === 'error') throw new Error(event.error)
        }
      } catch {
        usedFallback = true
        info.value = t('app.stream_fallback')
        const fallback = await chatSync(body)
        finalReport = fallback
        app.streamAnswer = fallback.answer
        app.streamPhase = 'post_processing'
      }
      if (finalReport) {
        app.lastReport = finalReport
        app.evidenceRows = finalReport.evidence_rows
        app.messages.push({ role: 'assistant', content: finalReport.answer })
        tutorialSignal('report_ready')
        showDoneBanner(finalReport.evidence_rows.length)
        if (usedFallback) {
          app.streamDoneVisible = false
        }
      }
    } catch (err) {
      error.value = formatError(err)
    } finally {
      app.streaming = false
      app.streamStatus = ''
      app.streamPhase = null
    }
  }

  function handleEvent(event: ChatStreamEvent) {
    if (event.type === 'status') {
      if (isStreamPhase(event.phase)) {
        app.streamPhase = event.phase
      }
      if (typeof event.evidence_count === 'number') {
        app.streamEvidenceCount = event.evidence_count
      }
      return
    }
    if (event.type === 'chunk') {
      if (app.streamPhase !== 'generating') {
        app.streamPhase = 'generating'
      }
      app.streamAnswer += event.delta
      return
    }
    if (event.type === 'final') {
      app.streamAnswer = event.answer
      app.streamPhase = 'post_processing'
    }
  }

  return { send, error, info }
}
