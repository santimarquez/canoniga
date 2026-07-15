<template>
  <aside class="rounded-xl border border-slate-200 bg-white p-4">
    <div class="mb-4 flex items-center justify-between">
      <h2 class="text-sm font-semibold text-slate-900">{{ t('app.evidence_nodes') }}</h2>
      <span class="text-xs text-slate-500">{{ app.evidenceRows.length }} {{ t('app.found') }}</span>
    </div>
    <EvidenceList :rows="app.evidenceRows" @open="openClaim" />
    <div class="mt-4 border-t border-slate-200 pt-4">
      <h3 class="mb-2 text-sm font-semibold">{{ t('app.compare_nodes') }}</h3>
      <ComparePanel />
    </div>
    <DiagnosticsPanel class="mt-4 border-t border-slate-200 pt-4" />
  </aside>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import ComparePanel from '@/components/evidence/ComparePanel.vue'
import DiagnosticsPanel from '@/components/evidence/DiagnosticsPanel.vue'
import EvidenceList from '@/components/evidence/EvidenceList.vue'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()

function openClaim(claimId: string) {
  app.claimDrawerClaimId = claimId
  app.claimDrawerOpen = true
}
</script>
