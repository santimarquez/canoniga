<template>
  <section class="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
    <div class="rounded-xl border border-slate-200 bg-white p-4">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-slate-900">{{ t('app.review_queue') }}</h2>
        <UiButton variant="secondary" size="sm" :loading="loadingFlags" @click="loadFlags">{{ t('app.refresh') }}</UiButton>
      </div>
      <div class="space-y-2">
        <button
          v-for="flag in flags"
          :key="flag.claim_id"
          type="button"
          class="w-full rounded-lg border p-3 text-left"
          :class="selectedId === flag.claim_id ? 'border-brand-primary bg-blue-50' : 'border-slate-200 hover:bg-slate-50'"
          @click="select(flag.claim_id)"
        >
          <p class="font-medium text-slate-900">{{ flag.claim_id }}</p>
          <p class="text-xs text-slate-500">{{ flag.entity }} · risk {{ flag.risk_score.toFixed(2) }}</p>
        </button>
      </div>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white p-4">
      <div v-if="selectedFlag">
        <h3 class="text-lg font-semibold text-slate-900">{{ selectedFlag.claim_id }}</h3>
        <ul class="mt-2 list-disc pl-5 text-sm text-slate-700">
          <li v-for="reason in selectedFlag.reasons" :key="reason">{{ reason }}</li>
        </ul>
        <div class="mt-4 flex flex-wrap gap-2">
          <UiButton size="sm" @click="decide('approve')">{{ t('app.approve') }}</UiButton>
          <UiButton size="sm" variant="secondary" @click="decide('needs_evidence')">{{ t('app.needs_more_evidence') }}</UiButton>
          <UiButton size="sm" variant="danger" @click="decide('reject')">{{ t('app.reject') }}</UiButton>
        </div>
        <div class="mt-6">
          <h4 class="text-sm font-semibold text-slate-900">{{ t('app.decision_history') }}</h4>
          <ul class="mt-2 space-y-1 text-xs text-slate-600">
            <li v-for="row in history" :key="`${row.claim_id}-${row.decided_at}`">
              {{ row.decision }} · {{ row.reviewer }} · {{ row.decided_at }}
            </li>
          </ul>
        </div>
      </div>
      <p v-else class="text-sm text-slate-500">{{ t('app.no_review_flags') }}</p>
      <UiNotice v-if="message" class="mt-4" :type="noticeType" :message="message" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchReviewDecisions, fetchReviewFlags, submitReviewDecision } from '@/api/app'
import UiButton from '@/components/ui/UiButton.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type { NoticeType, ReviewDecisionRow, ReviewFlag } from '@/types/api'

const { t } = useI18n()
const app = useAppStore()
const auth = useAuthStore()
const flags = ref<ReviewFlag[]>([])
const history = ref<ReviewDecisionRow[]>([])
const selectedId = ref('')
const loadingFlags = ref(false)
const message = ref('')
const noticeType = ref<NoticeType>('info')

const selectedFlag = computed(() => flags.value.find((flag) => flag.claim_id === selectedId.value) || null)

async function loadFlags() {
  loadingFlags.value = true
  try {
    const data = await fetchReviewFlags()
    flags.value = data.flags
    app.reviewFlags = data.flags
    if (!selectedId.value && data.flags.length) {
      await select(data.flags[0].claim_id)
    }
  } finally {
    loadingFlags.value = false
  }
}

async function select(claimId: string) {
  selectedId.value = claimId
  app.selectedReviewClaimId = claimId
  const data = await fetchReviewDecisions(claimId)
  history.value = data.rows
}

async function decide(decision: string) {
  if (!selectedId.value) return
  await submitReviewDecision({
    claim_id: selectedId.value,
    decision,
    reviewer: auth.displayName || 'reviewer',
    notes: '',
  })
  message.value = t('app.review_decision_saved')
  noticeType.value = 'success'
  await loadFlags()
  await select(selectedId.value)
}

onMounted(() => {
  void loadFlags()
})
</script>
