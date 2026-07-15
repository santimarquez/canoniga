import type { EvidenceRow } from '@/types/api'

const STUDY_TYPE_WEIGHT: Record<string, number> = {
  meta_analysis: 1.0,
  interventional: 0.85,
  observational: 0.7,
  preclinical: 0.45,
}

const SOURCE_TYPE_WEIGHT: Record<string, number> = {
  journal: 1.0,
  registry: 0.9,
  conference: 0.8,
  preprint: 0.65,
}

export type ScoreBreakdownRow = {
  key: string
  component: number
  weight: number
  contribution: number
}

export type ReliabilityBreakdown = {
  rows: ScoreBreakdownRow[]
  total: number
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value))
}

function round4(value: number) {
  return Math.round(value * 10000) / 10000
}

export function scoreComponents(row: Pick<
  EvidenceRow,
  | 'study_type'
  | 'sample_size'
  | 'replication_count'
  | 'peer_reviewed'
  | 'endpoint_validity'
  | 'source_type'
  | 'extraction_confidence'
>): ReliabilityBreakdown {
  const studyComponent = STUDY_TYPE_WEIGHT[row.study_type] ?? 0.7
  const sampleComponent = Math.min((row.sample_size || 0) / 300, 1)
  const replicationComponent = Math.min((row.replication_count || 0) / 3, 1)
  const peerComponent = row.peer_reviewed ? 1 : 0.65
  const endpointComponent = row.endpoint_validity || 0
  const sourceComponent = SOURCE_TYPE_WEIGHT[String(row.source_type || '').toLowerCase()] ?? 0.7
  const extractionComponent = row.extraction_confidence || 0

  const rows: ScoreBreakdownRow[] = [
    { key: 'study', component: round4(studyComponent), weight: 24, contribution: round4(0.24 * studyComponent) },
    { key: 'sample', component: round4(sampleComponent), weight: 16, contribution: round4(0.16 * sampleComponent) },
    { key: 'replication', component: round4(replicationComponent), weight: 16, contribution: round4(0.16 * replicationComponent) },
    { key: 'peer_review', component: round4(peerComponent), weight: 14, contribution: round4(0.14 * peerComponent) },
    { key: 'endpoint', component: round4(endpointComponent), weight: 12, contribution: round4(0.12 * endpointComponent) },
    { key: 'source', component: round4(sourceComponent), weight: 10, contribution: round4(0.1 * sourceComponent) },
    { key: 'extraction', component: round4(extractionComponent), weight: 8, contribution: round4(0.08 * extractionComponent) },
  ]

  const total = round4(clamp01(rows.reduce((sum, item) => sum + item.contribution, 0)))
  return { rows, total }
}

export function sourceReliabilityBreakdown(row: Pick<
  EvidenceRow,
  'source_type' | 'peer_reviewed' | 'extraction_confidence'
>): ReliabilityBreakdown {
  const sourceComponent = SOURCE_TYPE_WEIGHT[String(row.source_type || '').toLowerCase()] ?? 0.7
  const peerComponent = row.peer_reviewed ? 1 : 0.65
  const extractionComponent = row.extraction_confidence || 0

  const rows: ScoreBreakdownRow[] = [
    { key: 'source', component: round4(sourceComponent), weight: 45, contribution: round4(0.45 * sourceComponent) },
    { key: 'peer_review', component: round4(peerComponent), weight: 35, contribution: round4(0.35 * peerComponent) },
    { key: 'extraction', component: round4(extractionComponent), weight: 20, contribution: round4(0.2 * extractionComponent) },
  ]

  const total = round4(clamp01(rows.reduce((sum, item) => sum + item.contribution, 0)))
  return { rows, total }
}
