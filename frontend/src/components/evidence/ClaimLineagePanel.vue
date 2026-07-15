<template>
  <div v-if="loading" class="flex justify-center py-8"><UiSpinner /></div>
  <div v-else-if="lineage" :key="claimId" class="space-y-3 text-sm">
    <div class="flex flex-wrap items-center gap-2">
      <UiBadge tone="info">{{ formatScore(lineage.claim.reliability_score) }} {{ t('app.lineage_reliability') }}</UiBadge>
      <UiBadge tone="success">{{ lineage.lineage_counts.supporting }} {{ t('app.lineage_chip_supporting_count') }}</UiBadge>
      <UiBadge tone="danger">{{ lineage.lineage_counts.contradicting }} {{ t('app.lineage_chip_contradicting_count') }}</UiBadge>
      <UiBadge tone="neutral">{{ lineage.lineage_counts.neutral }} {{ t('app.lineage_chip_neutral_count') }}</UiBadge>
    </div>

    <div class="space-y-2">
      <p class="rounded-lg bg-slate-50 p-3 text-slate-800">
        {{ lineage.claim.claim_text || t('app.lineage_no_claim_text') }}
      </p>
      <a
        v-if="sourceUrl"
        :href="sourceUrl"
        class="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-primary hover:underline"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span class="material-symbols-outlined text-[18px]">open_in_new</span>
        {{ t('app.db_view_source') }}
      </a>
    </div>

    <DetailFieldList :fields="summaryFields" />

    <UiDisclosure v-if="reliabilityBreakdown" :title="t('app.db_reliability_breakdown')">
      <ReliabilityBreakdown :breakdown="reliabilityBreakdown" />
    </UiDisclosure>

    <UiDisclosure v-if="sourceReliabilityBreakdownData" :title="t('app.db_source_reliability_breakdown')">
      <ReliabilityBreakdown :breakdown="sourceReliabilityBreakdownData" />
    </UiDisclosure>

    <UiDisclosure :title="t('app.db_detail_study_section')">
      <DetailFieldList :fields="studyFields" />
    </UiDisclosure>

    <UiDisclosure :title="t('app.db_detail_source_section')">
      <div class="space-y-3 text-xs">
        <DetailFieldList :fields="sourceFields" columns="two" />

        <p v-if="!sourceMetadata" class="text-slate-500">{{ t('app.db_meta_not_found') }}</p>
        <template v-else>
          <div v-if="sourceMetadata.authors.length">
            <p class="font-semibold text-slate-700">{{ t('app.db_meta_authors') }}</p>
            <p class="mt-1 text-slate-600">{{ sourceMetadata.authors.join('; ') }}</p>
          </div>
          <div v-if="sourceMetadata.mesh_terms.length">
            <p class="font-semibold text-slate-700">{{ t('app.db_meta_mesh_terms') }}</p>
            <p class="mt-1 text-slate-600">{{ sourceMetadata.mesh_terms.join('; ') }}</p>
          </div>
          <div v-if="sourceMetadata.affiliations.length">
            <p class="font-semibold text-slate-700">{{ t('app.db_meta_affiliations') }}</p>
            <p class="mt-1 text-slate-600">{{ sourceMetadata.affiliations.join('; ') }}</p>
          </div>
          <div v-if="sourceMetadata.abstract_text">
            <p class="font-semibold text-slate-700">{{ t('app.db_meta_abstract') }}</p>
            <p class="mt-1 whitespace-pre-wrap text-slate-600">{{ sourceMetadata.abstract_text }}</p>
          </div>
          <div v-if="provenanceFields.length">
            <p class="font-semibold text-slate-700">{{ t('app.db_meta_provenance') }}</p>
            <DetailFieldList :fields="provenanceFields" columns="two" />
          </div>
          <div v-if="sourceMetadata.references.length">
            <p class="font-semibold text-slate-700">{{ t('app.db_meta_references') }} ({{ sourceMetadata.references.length }})</p>
          </div>
        </template>
      </div>
    </UiDisclosure>

    <UiDisclosure :title="sectionTitle('lineage_supporting', lineage.lineage_counts.supporting)">
      <CitationList :items="lineage.lineage.supporting_citations" />
    </UiDisclosure>

    <UiDisclosure :title="sectionTitle('lineage_contradicting', lineage.lineage_counts.contradicting)">
      <CitationList :items="lineage.lineage.contradicting_citations" />
    </UiDisclosure>

    <UiDisclosure :title="sectionTitle('lineage_neutral', lineage.lineage_counts.neutral)">
      <CitationList :items="lineage.lineage.neutral_citations" />
    </UiDisclosure>
  </div>
  <UiNotice v-else-if="error" type="error" :message="error" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchDatabaseNodeMetadata, searchDatabaseNodes } from '@/api/app'
import { fetchEvidenceLineage } from '@/api/chat'
import CitationList from '@/components/evidence/CitationList.vue'
import DetailFieldList, { type DetailField } from '@/components/evidence/DetailFieldList.vue'
import ReliabilityBreakdown from '@/components/evidence/ReliabilityBreakdown.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiDisclosure from '@/components/ui/UiDisclosure.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { scoreComponents, sourceReliabilityBreakdown } from '@/lib/reliability'
import { buildSourceUrl } from '@/lib/sourceUrl'
import type { DatabaseNodeRow, EvidenceLineageResponse, EvidenceSourceMetadata } from '@/types/api'

const props = defineProps<{ claimId: string }>()

const { t } = useI18n()
const loading = ref(false)
const error = ref('')
const lineage = ref<EvidenceLineageResponse | null>(null)
const evidence = ref<DatabaseNodeRow | null>(null)
const sourceMetadata = ref<EvidenceSourceMetadata | null>(null)

function sectionTitle(key: 'lineage_supporting' | 'lineage_contradicting' | 'lineage_neutral', count: number) {
  return `${t(`app.${key}`)} (${count})`
}

function formatScore(score: number | undefined) {
  return `${Math.round((score || 0) * 100)}%`
}

function formatDecimal(score: number | undefined) {
  if (score === undefined || Number.isNaN(score)) return '—'
  return score.toFixed(2)
}

function display(value: string | number | boolean | undefined | null) {
  if (value === undefined || value === null || value === '') return '—'
  if (typeof value === 'boolean') return value ? t('app.yes') : t('app.no')
  return String(value)
}

function pickText(...values: Array<string | undefined | null>) {
  for (const value of values) {
    const text = String(value || '').trim()
    if (text) return text
  }
  return '—'
}

const sourceUrl = computed(() => {
  const row = evidence.value
  if (row?.source_url) return row.source_url
  if (row) return buildSourceUrl({ claim_id: row.claim_id, source_doi: row.source_doi })
  const claim = lineage.value?.claim
  if (claim) return buildSourceUrl({ claim_id: props.claimId, source_doi: claim.source_doi })
  return ''
})

const reliabilityBreakdown = computed(() => (evidence.value ? scoreComponents(evidence.value) : null))
const sourceReliabilityBreakdownData = computed(() =>
  evidence.value ? sourceReliabilityBreakdown(evidence.value) : null,
)

const summaryFields = computed<DetailField[]>(() => {
  const claim = lineage.value?.claim
  const row = evidence.value
  return [
    { label: t('app.db_field_entity'), value: pickText(row?.entity, claim?.entity) },
    { label: t('app.db_field_outcome'), value: pickText(row?.outcome, claim?.outcome) },
    { label: t('app.db_field_relation'), value: pickText(row?.relation, claim?.relation), helpKey: 'help_relation' },
    { label: t('app.db_field_effect'), value: pickText(row?.effect_direction, claim?.effect_direction), helpKey: 'help_effect_direction' },
    { label: t('app.db_field_disease'), value: display(row?.disease) },
    { label: t('app.db_field_year'), value: display(row?.year || undefined) },
    { label: t('app.db_field_causal_type'), value: display(row?.causal_evidence_type), helpKey: 'help_causal_evidence_type' },
    {
      label: t('app.db_field_reliability'),
      value: formatScore(row?.reliability_score ?? claim?.reliability_score),
      helpKey: 'help_reliability_score',
    },
    {
      label: t('app.db_field_source_reliability'),
      value: formatScore(row?.source_reliability_score),
      helpKey: 'help_source_reliability',
    },
  ]
})

const studyFields = computed<DetailField[]>(() => {
  const row = evidence.value
  return [
    { label: t('app.db_field_study'), value: display(row?.study_type), helpKey: 'help_study_type' },
    { label: t('app.db_field_sample_size'), value: display(row?.sample_size), helpKey: 'help_sample_size' },
    { label: t('app.db_field_peer_reviewed'), value: display(row?.peer_reviewed), helpKey: 'help_peer_reviewed' },
    { label: t('app.db_field_replication'), value: display(row?.replication_count), helpKey: 'help_replication_count' },
    { label: t('app.db_field_endpoint_validity'), value: formatDecimal(row?.endpoint_validity), helpKey: 'help_endpoint_validity' },
    { label: t('app.db_field_extraction_confidence'), value: formatDecimal(row?.extraction_confidence), helpKey: 'help_extraction_confidence' },
    { label: t('app.db_field_cohort'), value: display(row?.cohort) },
    { label: t('app.db_field_model_system'), value: display(row?.model_system) },
    { label: t('app.db_field_source_type'), value: display(row?.source_type) },
  ]
})

const sourceFields = computed<DetailField[]>(() => {
  const row = evidence.value
  const claim = lineage.value?.claim
  const meta = sourceMetadata.value
  const url = sourceUrl.value
  const sourceDoi = pickText(row?.source_doi, claim?.source_doi)
  return [
    { label: t('app.db_field_source_title'), value: display(row?.source_title) },
    {
      label: t('app.db_field_source'),
      value: sourceDoi,
      href: url && sourceDoi !== '—' ? url : undefined,
    },
    { label: t('app.db_meta_source_name'), value: display(meta?.source_name) },
    { label: t('app.db_meta_source_id'), value: display(meta?.source_id) },
    { label: t('app.db_meta_journal'), value: display(meta?.journal) },
    { label: t('app.db_meta_pubdate'), value: display(meta?.pubdate) },
    { label: t('app.db_meta_enriched_at'), value: display(meta?.enriched_at) },
  ]
})

const provenanceFields = computed<DetailField[]>(() => {
  const meta = sourceMetadata.value
  if (!meta) return []
  const payload = meta.metadata || {}
  return [
    { label: t('app.db_meta_api_endpoint'), value: display(payload.api_endpoint) },
    { label: t('app.db_meta_query_used'), value: display(payload.query_used) },
    { label: t('app.db_meta_source_version'), value: display(payload.source_version) },
    { label: t('app.db_meta_source_license'), value: display(payload.source_license) },
  ].filter((field) => field.value !== '—')
})

async function loadClaim(claimId: string) {
  loading.value = true
  error.value = ''
  lineage.value = null
  evidence.value = null
  sourceMetadata.value = null

  try {
    const [lineageRes, nodesRes, metadataRes] = await Promise.all([
      fetchEvidenceLineage(claimId),
      searchDatabaseNodes({ query: claimId, limit: 100, offset: 0 }),
      fetchDatabaseNodeMetadata(claimId),
    ])
    lineage.value = lineageRes
    evidence.value = nodesRes.rows.find((row) => row.claim_id === claimId) ?? null
    sourceMetadata.value = metadataRes.found ? metadataRes.metadata : null
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load claim details'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.claimId,
  (claimId) => {
    if (!claimId) {
      lineage.value = null
      evidence.value = null
      sourceMetadata.value = null
      error.value = ''
      return
    }
    void loadClaim(claimId)
  },
  { immediate: true },
)
</script>
