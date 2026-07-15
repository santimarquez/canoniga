export type AppView = 'assistant' | 'sessions' | 'hypothesis' | 'review'
export type NoticeType = 'error' | 'success' | 'info' | 'warning'
export type DateWindow = 'last5' | 'last10' | 'all'

export interface NoticeOptions {
  type: NoticeType
  message: string
}

export interface ApiError {
  error: string
}

export interface AuthUser {
  user_id: string
  email: string
}

export interface UserProfile {
  display_name: string
  title: string
  institution: string
  has_avatar: boolean
  initials: string
  profile_updated_at?: string
}

export interface AuthStatusResponse {
  auth_enabled: boolean
  authenticated: boolean
  user: AuthUser | null
  profile: UserProfile | null
  csrf_token: string | null
}

export interface SourceBreakdownRow {
  source: string
  articles: number
}

export interface LoginMetadataResponse {
  db_path: string
  records_total: number
  source_breakdown: SourceBreakdownRow[]
  latest_sync_at: string | null
  avg_reliability: number
}

export interface ManualSyncSource {
  source: string
  display_name: string
  query: string
  last_successful_at: string
  last_attempt_at: string
  last_attempt_status: string
  last_attempt_notes?: string
  last_manual_sync_at: string
  sync_status: string
  failure_count: number
  can_trigger: boolean
  cooldown_remaining_seconds: number
  next_available_at: string | null
}

export interface ManualSyncSnapshot {
  can_trigger_all: boolean
  can_trigger: boolean
  cooldown_remaining_seconds: number
  next_available_at: string | null
  in_progress: boolean
  manual_sync_active: boolean
  current_scope: string | null
  current_source: string | null
  completed_sources: number
  total_sources: number
  progress_percent: number
  estimated_remaining_seconds: number
  estimated_completion_at: string | null
  sources: ManualSyncSource[]
}

export interface ManualSyncAuditEvent {
  id: number
  scope: string
  triggered_by: string
  started_at: string
  ended_at: string
  status: string
  error: string
  run_ids: number[]
  notes: string
}

export interface ManualSyncStatusResponse extends ManualSyncSnapshot {
  reconciled_stale_runs?: number
  latest_sync_at?: string | null
  error?: string | null
  last_completion_status?: 'success' | 'failed' | null
  last_completion_error?: string | null
  last_completion_at?: string | null
  last_completion_scope?: string | null
  audit_events?: ManualSyncAuditEvent[]
}

export interface StatusResponse {
  records_total: number
  avg_reliability: number
  supports_count: number
  contradicts_count: number
  review_flags_count: number
  model: string
  host: string
  context_limit: number
  temperature: number
  timeout_seconds: number
  db_synced: boolean
  source_breakdown: SourceBreakdownRow[]
  latest_sync_at: string | null
  manual_sync: ManualSyncSnapshot
}

export interface ChatMessage {
  role: string
  content: string
}

export interface EvidenceFilters {
  evidence_types: string[]
  date_window: DateWindow
  min_reliability: number
  highlight_contradictions: boolean
}

export interface EvidenceRow {
  claim_id: string
  claim_text: string
  disease: string
  entity: string
  relation: string
  outcome: string
  effect_direction: string
  study_type: string
  sample_size: number
  endpoint_validity: number
  replication_count: number
  peer_reviewed: boolean
  year: number
  source_title: string
  source_doi: string
  cohort: string
  model_system: string
  source_type: string
  extraction_confidence: number
  causal_evidence_type: string
  source_reliability_score: number
  reliability_score: number
  source_url?: string
}

export interface Synthesis {
  direct_answer: string
  mentioned_claim_ids?: string[]
  supporting_claim_ids?: string[]
  contradictions_summary?: string
  next_validation_step?: string
  verification_flags?: string[]
}

export interface QueryTelemetry {
  trace_id: string
  mode: string
  path: string
  started_at: number
  status: string
  model?: string
  language?: string
  user_id?: string
  phase_seconds: Record<string, number>
  evidence_count?: number
  cited_evidence_count?: number
  guardrail_flags?: string[]
  verification_flags?: string[]
  total_seconds?: number
  error?: string
}

export interface ChatReport {
  answer: string
  evidence_count: number
  model: string
  host: string
  generated_seconds: number
  synthesis: Synthesis
  evidence_rows: EvidenceRow[]
  response_mode: string
  guardrail_flags: string[]
  telemetry: QueryTelemetry
}

export interface ChatRequest {
  messages: ChatMessage[]
  db_path: string
  host: string
  model: string
  context_limit: number
  temperature: number
  timeout_seconds: number
  language: string
  filters: EvidenceFilters
}

export interface ChatStreamStatusEvent {
  type: 'status'
  phase: string
  message: string
}

export interface ChatStreamChunkEvent {
  type: 'chunk'
  delta: string
}

export interface ChatStreamFinalEvent extends ChatReport {
  type: 'final'
}

export interface ChatStreamErrorEvent {
  type: 'error'
  error: string
}

export type ChatStreamEvent =
  | ChatStreamStatusEvent
  | ChatStreamChunkEvent
  | ChatStreamFinalEvent
  | ChatStreamErrorEvent

export interface LineageClaim {
  claim_id: string
  claim_text: string
  entity: string
  relation: string
  outcome: string
  effect_direction: string
  source_doi: string
  reliability_score: number
}

export interface LineageCitation {
  claim_id: string
  source_doi: string
  effect_direction?: string
  reliability_score: number
}

export interface EvidenceLineageResponse {
  claim: LineageClaim
  lineage: {
    supporting_citations: LineageCitation[]
    contradicting_citations: LineageCitation[]
    neutral_citations: LineageCitation[]
  }
  lineage_counts: {
    supporting: number
    contradicting: number
    neutral: number
  }
}

export interface CompareResponse {
  claim_a: LineageClaim
  claim_b: LineageClaim
  shared_supporting_count: number
  shared_contradicting_count: number
  follow_up_suggestion: string
}

export interface SessionSummary {
  session_id: string
  title: string
  question: string
  created_at: string
  updated_at: string
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface SessionDetailResponse {
  user_id: string
  session_id: string
  title: string
  question: string
  messages: ChatMessage[]
  report: ChatReport
  filters: EvidenceFilters
  evidence_claim_ids: string[]
  created_at: string
  updated_at: string
}

export interface ReviewFlag {
  claim_id: string
  entity: string
  reliability_score: number
  confidence_delta: number
  contradiction_density: number
  risk_score: number
  requires_human_review: true
  reasons: string[]
}

export interface ReviewFlagsResponse {
  flags: ReviewFlag[]
  total: number
}

export interface ReviewDecisionRow {
  claim_id: string
  decision: string
  reviewer: string
  notes: string
  decided_at: string
}

export interface ReviewDecisionsResponse {
  rows: ReviewDecisionRow[]
  total: number
  limit: number
}

export interface HypothesisEvidenceRef {
  claim_id: string
  source_doi: string
  reliability_score: number
}

export interface HypothesisQueueItem {
  entity: string
  hypothesis: string
  biological_rationale: string
  supporting_evidence: HypothesisEvidenceRef[]
  contradictory_evidence: HypothesisEvidenceRef[]
  confidence_score: number
  false_inference_risk: number
  causal_risk_score: number
  causal_evidence_profile: string
  causal_gate_override_applied: boolean
  trial_feasibility_score: number
  trial_compatibility_notes: string
  priority_score: number
  suggested_validation_experiments: string[]
}

export interface HypothesisQueueResponse {
  queue: HypothesisQueueItem[]
  baseline_total: number
  total: number
  removed_entities: string[]
  require_review_signoff: boolean
  enforce_causal_gate: boolean
}

export interface TelemetryRow {
  trace_id: string
  mode: string
  status: string
  started_at: number
  total_seconds?: number
  model?: string
  evidence_count?: number
}

export interface TelemetryResponse {
  rows: TelemetryRow[]
}

export interface FailureAtlasRow {
  source: string
  failure_count: number
  last_failure_at: string
  last_error: string
}

export interface FailureAtlasResponse {
  rows: FailureAtlasRow[]
}

export interface DatabaseNodeSourceMetadataSummary {
  journal: string
  pubdate: string
  authors_count: number
  mesh_terms_count: number
  has_abstract: boolean
  enriched_at: string
  api_endpoint: string
  query_used: string
  source_version: string
  source_license: string
}

export interface DatabaseNodeRow extends EvidenceRow {
  source_metadata?: DatabaseNodeSourceMetadataSummary
}

export interface EvidenceSourceMetadata {
  claim_id: string
  source_name: string
  source_id: string
  abstract_text: string
  journal: string
  pubdate: string
  authors: string[]
  mesh_terms: string[]
  affiliations: string[]
  references: unknown[]
  metadata: Record<string, string>
  enriched_at: string
}

export interface DatabaseNodeMetadataResponse {
  claim_id: string
  found: boolean
  metadata: EvidenceSourceMetadata | null
}

export interface DatabaseNodesResponse {
  rows: DatabaseNodeRow[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface AppConfig {
  model: string
  dbPath: string
  host: string
  contextLimit: number
  temperature: number
  timeoutSeconds: number
  authEnabled: boolean
}

export const EVIDENCE_TYPE_OPTIONS = [
  'observational',
  'interventional',
  'mechanistic',
  'genetic',
  'negative',
] as const

export const DEFAULT_FILTERS: EvidenceFilters = {
  evidence_types: ['observational', 'interventional'],
  date_window: 'all',
  min_reliability: 0.6,
  highlight_contradictions: true,
}
