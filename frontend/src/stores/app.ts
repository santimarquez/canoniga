import { defineStore } from 'pinia'
import {
  DEFAULT_FILTERS,
  type AppConfig,
  type AppView,
  type ChatMessage,
  type ChatReport,
  type CompareResponse,
  type EvidenceFilters,
  type EvidenceRow,
  type HypothesisQueueItem,
  type ReviewFlag,
} from '@/types/api'

export const useAppStore = defineStore('app', {
  state: () => ({
    config: {
      model: 'llama3.1:8b',
      dbPath: 'data/als_intel.sqlite',
      host: 'http://localhost:11434',
      contextLimit: 12,
      temperature: 0.2,
      timeoutSeconds: 300,
      authEnabled: true,
    } as AppConfig,
    activeView: 'assistant' as AppView,
    language: 'en' as 'en' | 'es',
    messages: [] as ChatMessage[],
    evidenceRows: [] as EvidenceRow[],
    lastReport: null as ChatReport | null,
    activeSessionId: null as string | null,
    currentEvidenceQuery: '',
    currentCompare: null as CompareResponse | null,
    filters: {
      ...DEFAULT_FILTERS,
      evidence_types: [...DEFAULT_FILTERS.evidence_types],
    } as EvidenceFilters,
    filtersCollapsed: false,
    evidenceCollapsed: false,
    evidenceSidebarOpen: false,
    reviewFlags: [] as ReviewFlag[],
    selectedReviewClaimId: '',
    hypothesisRows: [] as HypothesisQueueItem[],
    hypothesisRemovedEntities: [] as string[],
    hypothesisLimit: 10,
    streaming: false,
    streamStatus: '',
    streamAnswer: '',
    settingsOpen: false,
    profileOpen: false,
    claimDrawerOpen: false,
    claimDrawerClaimId: '',
    dbExplorerOpen: false,
    tutorialRunning: false,
  }),
  actions: {
    setConfig(config: Partial<AppConfig>) {
      this.config = { ...this.config, ...config }
    },
    switchView(view: AppView) {
      this.activeView = view
    },
    resetChat() {
      this.messages = []
      this.lastReport = null
      this.evidenceRows = []
      this.streamAnswer = ''
      this.streamStatus = ''
    },
    applySession(payload: {
      session_id: string
      messages: ChatMessage[]
      report: ChatReport
      filters: EvidenceFilters
    }) {
      this.activeSessionId = payload.session_id
      this.messages = payload.messages
      this.lastReport = payload.report
      this.evidenceRows = payload.report?.evidence_rows ?? []
      this.filters = payload.filters
    },
  },
})
