<template>
  <article ref="reportRef" class="w-full" data-tutorial="report">
    <MarkdownContent
      v-if="app.streaming || displayAnswer"
      :content="displayAnswer"
      :show-cursor="app.streaming"
    />

    <Transition name="fade-slide">
      <div v-if="report && !app.streaming" key="post-stream">
        <div v-if="supportingIds.length" class="mt-6">
          <h4 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {{ t('app.supporting_nodes') }}
          </h4>
          <div class="chips">
            <button
              v-for="claimId in supportingIds"
              :key="claimId"
              type="button"
              class="chip"
              @click="openClaim(claimId)"
            >
              {{ claimId }}
            </button>
          </div>
        </div>

        <div
          class="mt-6 space-y-6"
          data-tutorial="validation"
        >
          <div v-if="report.synthesis?.contradictions_summary">
            <h4 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              {{ t('app.contradictions_uncertainty') }}
            </h4>
            <MarkdownContent :content="report.synthesis.contradictions_summary" />
          </div>

          <div v-if="report.synthesis?.next_validation_step">
            <h4 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              {{ t('app.next_validation_step') }}
            </h4>
            <MarkdownContent :content="report.synthesis.next_validation_step" />
          </div>

          <div
            v-if="followUpQuery"
            class="rounded-lg border border-slate-200 bg-slate-50 p-3"
          >
            <h4 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              {{ t('app.executable_follow_up') }}
            </h4>
            <p class="mb-3 text-sm text-slate-800">{{ followUpQuery }}</p>
            <UiButton
              size="sm"
              :disabled="app.streaming"
              :loading="app.streaming"
              @click="runFollowUp"
            >
              {{ t('app.run_this_query') }}
            </UiButton>
          </div>
        </div>

        <div class="report-meta mt-6">
          <span class="runtime-badge">{{ t('app.report_model', { model: report.model }) }}</span>
          <span class="runtime-badge">{{ t('app.generated_in', { seconds: formattedSeconds }) }}</span>
        </div>
      </div>
    </Transition>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownContent from '@/components/chat/MarkdownContent.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useChatStream } from '@/composables/useChatStream'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()
const { send } = useChatStream()
const reportRef = ref<HTMLElement | null>(null)

const report = computed(() => app.lastReport)

const displayAnswer = computed(() => {
  if (app.streaming) return app.streamAnswer
  const fromSynthesis = report.value?.synthesis?.direct_answer?.trim() ?? ''
  const fromAnswer = report.value?.answer?.trim() ?? ''
  return fromSynthesis || fromAnswer || app.streamAnswer
})

const supportingIds = computed(() => {
  const ids = report.value?.synthesis?.supporting_claim_ids ?? []
  return ids.filter((id) => id.trim())
})

const followUpQuery = computed(() => {
  return report.value?.synthesis?.executable_follow_up_query?.trim() || ''
})

const formattedSeconds = computed(() => {
  const seconds = Number(report.value?.generated_seconds ?? 0)
  return seconds.toFixed(1)
})

function openClaim(claimId: string) {
  app.claimDrawerClaimId = claimId
  app.claimDrawerOpen = true
}

function runFollowUp() {
  const query = followUpQuery.value
  if (!query || app.streaming) return
  void send(query)
}

defineExpose({ reportRef })
</script>
