<template>
  <aside :class="embedded ? '' : 'rounded-xl border border-slate-200 bg-white p-4'">
    <UiDisclosure v-model:open="evidenceOpen" :title="disclosureTitle">
      <div class="space-y-4">
        <p v-if="hint" class="text-sm text-slate-500">{{ hint }}</p>
        <EvidenceList
          :rows="app.evidenceRows"
          :highlight-contradictions="app.filters.highlight_contradictions"
          @open="openClaim"
        />
        <div class="border-t border-slate-200 pt-4">
          <h3 class="mb-2 text-sm font-semibold">{{ t('app.compare_nodes') }}</h3>
          <ComparePanel />
        </div>
        <DiagnosticsPanel class="border-t border-slate-200 pt-4" />
      </div>
    </UiDisclosure>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ComparePanel from '@/components/evidence/ComparePanel.vue'
import DiagnosticsPanel from '@/components/evidence/DiagnosticsPanel.vue'
import EvidenceList from '@/components/evidence/EvidenceList.vue'
import UiDisclosure from '@/components/ui/UiDisclosure.vue'
import { useAppStore } from '@/stores/app'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), {
  embedded: false,
})

const { t } = useI18n()
const app = useAppStore()
const drawerOpen = ref(true)

const evidenceOpen = computed({
  get: () => (props.embedded ? drawerOpen.value : !app.evidenceCollapsed),
  set: (value: boolean) => {
    if (props.embedded) {
      drawerOpen.value = value
      return
    }
    app.evidenceCollapsed = !value
  },
})

const disclosureTitle = computed(() => {
  const count = app.evidenceRows.length
  return `${t('app.evidence_nodes')} (${count} ${t('app.found')})`
})

const hint = computed(() => {
  const hasQuery = app.messages.some((message) => message.role === 'user')
  if (!hasQuery && !app.activeSessionId) return t('app.evidence_hint_idle')
  if (app.lastReport && app.evidenceRows.length === 0) return t('app.evidence_hint_empty')
  return ''
})

function openClaim(claimId: string) {
  app.claimDrawerClaimId = claimId
  app.claimDrawerOpen = true
}
</script>
