import { apiJson } from './client'
import type {
  DatabaseNodeMetadataResponse,
  DatabaseNodesResponse,
  FailureAtlasResponse,
  HypothesisQueueResponse,
  ManualSyncStatusResponse,
  ModelsResponse,
  ReviewDecisionsResponse,
  ReviewFlagsResponse,
  SessionDetailResponse,
  SessionListResponse,
  TelemetryResponse,
} from '@/types/api'
import type { ChatMessage, ChatReport, EvidenceFilters } from '@/types/api'

export function fetchManualSyncStatus() {
  return apiJson<ManualSyncStatusResponse>('/api/sync/manual/status')
}

export function fetchModels() {
  return apiJson<ModelsResponse>('/api/models')
}

export function triggerManualSync(payload: { scope: 'all' } | { source: string }) {
  return apiJson<{ status: 'started'; scope: string; plan_path: string }>('/api/sync/manual/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchSessions(limit = 50, offset = 0) {
  return apiJson<SessionListResponse>(`/api/session/list?limit=${limit}&offset=${offset}`)
}

export function fetchSession(sessionId: string) {
  return apiJson<SessionDetailResponse>(`/api/session/${encodeURIComponent(sessionId)}`)
}

export function saveSession(payload: {
  session_id: string
  title: string
  question: string
  report: ChatReport
  messages: ChatMessage[]
  filters: EvidenceFilters
  evidence_claim_ids: string[]
}) {
  return apiJson<{ user_id: string; session_id: string; updated_at: string }>('/api/session/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchReviewFlags() {
  return apiJson<ReviewFlagsResponse>('/api/review/flags', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
}

export function submitReviewDecision(payload: {
  claim_id: string
  decision: string
  reviewer: string
  notes: string
}) {
  return apiJson<{ ok: true; claim_id: string; decision: string; reviewer: string }>(
    '/api/review/decision',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export function fetchReviewDecisions(claimId: string, limit = 20) {
  return apiJson<ReviewDecisionsResponse>('/api/review/decisions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ claim_id: claimId, limit }),
  })
}

export function fetchHypothesisQueue(payload: {
  limit: number
  require_review_signoff: boolean
  enforce_causal_gate: boolean
}) {
  return apiJson<HypothesisQueueResponse>('/api/hypothesis/queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchRecentTelemetry(limit = 8) {
  return apiJson<TelemetryResponse>(`/api/telemetry/recent?limit=${limit}`)
}

export function fetchFailureAtlas() {
  return apiJson<FailureAtlasResponse>('/api/failure-atlas')
}

export function searchDatabaseNodes(payload: {
  query: string
  limit: number
  offset: number
}) {
  return apiJson<DatabaseNodesResponse>('/api/database/nodes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchDatabaseNodeMetadata(claimId: string) {
  return apiJson<DatabaseNodeMetadataResponse>('/api/database/node/metadata', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ claim_id: claimId }),
  })
}

export function exportSummary(payload: Record<string, unknown>) {
  return apiJson<Record<string, unknown>>('/api/export/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function composeSynthesis(payload: Record<string, unknown>) {
  return apiJson<Record<string, unknown>>('/api/synthesis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
