import { ref } from 'vue'
import { chatSync, streamChat } from '@/api/chat'
import { useAppStore } from '@/stores/app'
import type { ChatReport, ChatStreamEvent } from '@/types/api'

export function useChatStream() {
  const app = useAppStore()
  const error = ref('')

  async function send(question: string) {
    error.value = ''
    app.messages.push({ role: 'user', content: question })
    app.streaming = true
    app.streamAnswer = ''
    app.streamStatus = ''

    const body = {
      messages: app.messages,
      db_path: app.config.dbPath,
      host: app.config.host,
      model: app.config.model,
      context_limit: app.config.contextLimit,
      temperature: app.config.temperature,
      timeout_seconds: app.config.timeoutSeconds,
      language: app.language,
      filters: app.filters,
    }

    try {
      let finalReport: ChatReport | null = null
      try {
        for await (const event of streamChat(body)) {
          handleEvent(event)
          if (event.type === 'final') finalReport = event
          if (event.type === 'error') throw new Error(event.error)
        }
      } catch {
        const fallback = await chatSync(body)
        finalReport = fallback
        app.streamAnswer = fallback.answer
      }
      if (finalReport) {
        app.lastReport = finalReport
        app.evidenceRows = finalReport.evidence_rows
        app.messages.push({ role: 'assistant', content: finalReport.answer })
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Chat failed'
    } finally {
      app.streaming = false
      app.streamStatus = ''
    }
  }

  function handleEvent(event: ChatStreamEvent) {
    if (event.type === 'status') {
      app.streamStatus = event.message
      return
    }
    if (event.type === 'chunk') {
      app.streamAnswer += event.delta
      return
    }
    if (event.type === 'final') {
      app.streamAnswer = event.answer
    }
  }

  return { send, error }
}
