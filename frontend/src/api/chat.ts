import { apiFetch, apiJson, readNdjsonStream } from './client'
import type {
  ChatReport,
  ChatRequest,
  ChatStreamEvent,
  CompareResponse,
  EvidenceFilters,
  EvidenceLineageResponse,
  EvidenceRow,
} from '@/types/api'

export function filterEvidence(filters: EvidenceFilters, limit = 200, offset = 0) {
  return apiJson<{ rows: EvidenceRow[]; total: number; limit: number; offset: number; has_more: boolean }>(
    '/api/evidence/filter',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filters, limit, offset }),
    },
  )
}

export function fetchEvidenceLineage(claimId: string) {
  return apiJson<EvidenceLineageResponse>(`/api/evidence/${encodeURIComponent(claimId)}`)
}

export function compareEvidence(claimA: string, claimB: string) {
  return apiJson<CompareResponse>('/api/evidence/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ claim_a: claimA, claim_b: claimB }),
  })
}

export async function chatSync(body: ChatRequest) {
  return apiJson<ChatReport>('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function* streamChat(body: ChatRequest): AsyncGenerator<ChatStreamEvent> {
  const response = await apiFetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const message =
      typeof payload === 'object' && payload && 'error' in payload
        ? String((payload as { error: string }).error)
        : `Stream failed (${response.status})`
    throw new Error(message)
  }
  yield* readNdjsonStream<ChatStreamEvent>(response)
}
