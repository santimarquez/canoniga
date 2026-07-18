<template>
  <div class="space-y-4">
    <UiDisclosure
      v-model:open="diagnosticsOpen"
      data-tutorial="diagnostics"
      :title="t('app.diagnostics_title')"
    >
      <div class="space-y-2">
        <div class="flex justify-end">
          <UiButton
            variant="secondary"
            size="sm"
            :loading="diagnosticsLoading"
            @click="loadDiagnostics"
          >
            {{ t('app.refresh') }}
          </UiButton>
        </div>

        <UiNotice v-if="diagnosticsError" type="error" :message="diagnosticsError" />
        <div v-else-if="diagnosticsLoading && !traces.length" class="flex items-center gap-2 py-2 text-xs text-slate-500">
          <UiSpinner size="sm" />
          {{ t('app.status_loading') }}
        </div>
        <p v-else-if="!traces.length" class="text-xs text-slate-500">{{ t('app.diagnostics_empty') }}</p>
        <div v-else class="max-h-64 space-y-2 overflow-y-auto">
          <article
            v-for="trace in traces"
            :key="trace.trace_id"
            class="rounded-lg border border-slate-200 bg-white p-2 text-xs text-slate-700"
          >
            <div class="flex justify-between gap-2">
              <span class="font-mono text-[11px] text-slate-800">{{ trace.trace_id || 'trace' }}</span>
              <span>{{ modeLabel(trace) }}</span>
            </div>
            <p class="mt-1 text-slate-500">
              {{
                t('app.telemetry_phase_summary', {
                  loading: formatSeconds(trace.phase_seconds?.loading_evidence),
                  prompt: formatSeconds(trace.phase_seconds?.building_prompt),
                  gen: formatSeconds(trace.phase_seconds?.generating),
                  post: formatSeconds(trace.phase_seconds?.post_processing),
                  total: formatSeconds(trace.total_seconds),
                })
              }}
            </p>
            <p class="mt-1">
              {{ t('app.rows_retrieved') }}: {{ Number(trace.evidence_count || 0) }}
              |
              {{ t('app.rows_cited') }}: {{ Number(trace.cited_evidence_count || 0) }}
            </p>
            <p class="mt-0.5">{{ t('app.guardrail_flags') }}: {{ joinFlags(trace.guardrail_flags) }}</p>
            <p class="mt-0.5">{{ t('app.verification_flags') }}: {{ joinFlags(trace.verification_flags) }}</p>
          </article>
        </div>
      </div>
    </UiDisclosure>

    <UiDisclosure v-model:open="atlasOpen" :title="t('app.failure_atlas_title')">
      <div class="space-y-2">
        <div class="flex justify-end">
          <UiButton
            variant="secondary"
            size="sm"
            :loading="atlasLoading"
            @click="loadFailureAtlas"
          >
            {{ t('app.refresh') }}
          </UiButton>
        </div>

        <UiNotice v-if="atlasError" type="error" :message="atlasError" />
        <div v-else-if="atlasLoading && !atlasEntries.length" class="flex items-center gap-2 py-2 text-xs text-slate-500">
          <UiSpinner size="sm" />
          {{ t('app.status_loading') }}
        </div>
        <p v-else-if="!atlasEntries.length" class="text-xs text-slate-500">{{ t('app.failure_atlas_empty') }}</p>
        <div v-else class="space-y-2">
          <p class="text-xs text-slate-500">
            {{ t('app.failure_atlas_total') }}: {{ atlasSummary.total }}
            |
            {{ t('app.failure_atlas_structured') }}: {{ atlasSummary.structured }}
          </p>
          <div class="max-h-64 space-y-2 overflow-y-auto">
            <article
              v-for="entry in atlasEntries"
              :key="entry.claim_id"
              class="rounded-lg border border-slate-200 bg-white p-2 text-xs text-slate-700"
            >
              <div class="flex justify-between gap-2">
                <span class="font-mono text-[11px] text-slate-800">{{ entry.claim_id || 'claim' }}</span>
                <span>{{ entry.entity || '' }}</span>
              </div>
              <p v-if="entry.outcome" class="mt-1 text-slate-500">{{ entry.outcome }}</p>
              <p class="mt-1">{{ t('app.trial_status') }}: {{ entry.trial_status || '-' }}</p>
              <p class="mt-0.5">{{ t('app.termination_reason') }}: {{ entry.termination_reason || '-' }}</p>
              <p class="mt-0.5">
                {{ t('app.primary_endpoint_result') }}: {{ entry.primary_endpoint_result || '-' }}
              </p>
              <p class="mt-0.5">{{ t('app.root_cause') }}: {{ entry.root_cause || '-' }}</p>
            </article>
          </div>
        </div>
      </div>
    </UiDisclosure>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchFailureAtlas, fetchRecentTelemetry } from '@/api/app'
import UiButton from '@/components/ui/UiButton.vue'
import UiDisclosure from '@/components/ui/UiDisclosure.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useAppStore } from '@/stores/app'
import type { FailureAtlasEntry, QueryTelemetry } from '@/types/api'

const ATLAS_ENTRY_LIMIT = 12

const { t } = useI18n()
const app = useAppStore()

const diagnosticsOpen = ref(false)
const atlasOpen = ref(false)

const traces = ref<QueryTelemetry[]>([])
const diagnosticsLoading = ref(false)
const diagnosticsError = ref('')

const atlasEntries = ref<FailureAtlasEntry[]>([])
const atlasSummary = ref({ total: 0, structured: 0 })
const atlasLoading = ref(false)
const atlasError = ref('')

function formatSeconds(value: unknown): string {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(2) : '0.00'
}

function joinFlags(flags: string[] | undefined): string {
  return Array.isArray(flags) && flags.length ? flags.join(', ') : '-'
}

function modeLabel(trace: QueryTelemetry): string {
  if (trace.fallback_used) return t('app.response_mode_sync_fallback')
  return trace.mode === 'stream' ? t('app.response_mode_stream') : t('app.response_mode_sync')
}

async function loadDiagnostics() {
  diagnosticsLoading.value = true
  diagnosticsError.value = ''
  try {
    const recent = await fetchRecentTelemetry()
    traces.value = Array.isArray(recent.traces) ? recent.traces : []
  } catch (error) {
    traces.value = []
    diagnosticsError.value = error instanceof Error ? error.message : String(error)
  } finally {
    diagnosticsLoading.value = false
  }
}

async function loadFailureAtlas() {
  atlasLoading.value = true
  atlasError.value = ''
  try {
    const atlas = await fetchFailureAtlas()
    const entries = Array.isArray(atlas.entries) ? atlas.entries : []
    atlasEntries.value = entries.slice(0, ATLAS_ENTRY_LIMIT)
    atlasSummary.value = {
      total: Number(atlas.total_failed_or_negative_records || 0),
      structured: Number(atlas.structured_trial_failures || 0),
    }
  } catch (error) {
    atlasEntries.value = []
    atlasSummary.value = { total: 0, structured: 0 }
    atlasError.value = error instanceof Error ? error.message : String(error)
  } finally {
    atlasLoading.value = false
  }
}

watch(
  () => app.tutorialDiagnosticsOpen,
  (open) => {
    if (open) {
      diagnosticsOpen.value = true
      app.tutorialDiagnosticsOpen = false
    }
  },
)

onMounted(() => {
  void loadDiagnostics()
  void loadFailureAtlas()
})

watch(
  () => app.lastReport?.telemetry?.trace_id,
  (traceId, previous) => {
    if (traceId && traceId !== previous) {
      void loadDiagnostics()
    }
  },
)
</script>
