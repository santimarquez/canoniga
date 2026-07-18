import { defineStore } from 'pinia'
import { compareEvidence } from '@/api/chat'
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

const MODEL_SELECTION_KEY = 'als_model_selection'

function loadModelSelection(): string {
  if (typeof localStorage === 'undefined') return 'auto'
  const raw = localStorage.getItem(MODEL_SELECTION_KEY)
  const value = String(raw || '').trim()
  return value || 'auto'
}

export const useAppStore = defineStore('app', {
  state: () => ({
    config: {
      model: 'llama3.1:8b',
      modelSelection: loadModelSelection(),
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
    compareClaimA: '',
    compareClaimB: '',
    compareModalOpen: false,
    compareLoading: false,
    compareError: '',
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
    streamPhase: null as string | null,
    streamEvidenceCount: null as number | null,
    streamCitedCount: null as number | null,
    streamDoneVisible: false,
    settingsOpen: false,
    profileOpen: false,
    claimDrawerOpen: false,
    claimDrawerClaimId: '',
    dbExplorerOpen: false,
    filterModalOpen: false,
    tutorialDiagnosticsOpen: false,
    tutorialEvidenceOpen: false,
    tutorialRunning: false,
  }),
  actions: {
    setConfig(config: Partial<AppConfig>) {
      this.config = { ...this.config, ...config }
      if (config.modelSelection !== undefined) {
        localStorage.setItem(MODEL_SELECTION_KEY, String(config.modelSelection || 'auto'))
      }
    },
    setModelSelection(selection: string) {
      const value = String(selection || '').trim() || 'auto'
      this.config.modelSelection = value
      localStorage.setItem(MODEL_SELECTION_KEY, value)
    },
    switchView(view: AppView) {
      this.activeView = view
    },
    addToCompare(claimId: string) {
      const id = claimId.trim()
      if (!id) return
      if (!this.compareClaimA) {
        this.compareClaimA = id
        return
      }
      this.compareClaimB = id
      if (this.compareClaimA && this.compareClaimB) {
        void this.runCompare({ openModal: true })
      }
    },
    async runCompare(options: { openModal?: boolean } = {}) {
      const claimA = this.compareClaimA.trim()
      const claimB = this.compareClaimB.trim()
      if (!claimA || !claimB) {
        this.compareError = 'compare_prompt'
        return
      }
      this.compareLoading = true
      this.compareError = ''
      if (options.openModal !== false) {
        this.compareModalOpen = true
      }
      try {
        const result = await compareEvidence(claimA, claimB)
        this.currentCompare = result
      } catch (err) {
        this.compareError = err instanceof Error ? err.message : 'Compare failed'
        this.currentCompare = null
      } finally {
        this.compareLoading = false
      }
    },
    resetChat() {
      this.messages = []
      this.lastReport = null
      this.evidenceRows = []
      this.streamAnswer = ''
      this.streamStatus = ''
      this.streamPhase = null
      this.streamEvidenceCount = null
      this.streamCitedCount = null
      this.streamDoneVisible = false
      this.compareClaimA = ''
      this.compareClaimB = ''
      this.currentCompare = null
      this.compareModalOpen = false
      this.compareLoading = false
      this.compareError = ''
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
      this.streaming = false
      this.streamPhase = null
      this.streamEvidenceCount = null
      this.streamCitedCount = null
      this.streamDoneVisible = false
      this.streamAnswer = ''
      this.streamStatus = ''
    },
  },
})
