import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'

export function useStreamStatus() {
  const { t } = useI18n()
  const app = useAppStore()

  const statusText = computed(() => {
    if (!app.streaming || !app.streamPhase) return ''
    const phase = app.streamPhase
    if (phase === 'loading_evidence') return t('app.stream_loading_evidence')
    if (phase === 'building_prompt') {
      if (app.streamEvidenceCount !== null) {
        return `${t('app.stream_building_prompt')} · ${t('app.stream_evidence_loaded', { count: app.streamEvidenceCount })}`
      }
      return t('app.stream_building_prompt')
    }
    if (phase === 'generating') return t('app.stream_generating')
    if (phase === 'post_processing') return t('app.stream_post_processing')
    return t('app.in_progress')
  })

  const statusVisible = computed(() => app.streaming)

  return { statusText, statusVisible }
}
