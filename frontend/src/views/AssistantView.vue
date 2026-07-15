<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4">
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <UiButton variant="secondary" size="sm" @click="app.filtersCollapsed = !app.filtersCollapsed">
        <span class="material-symbols-outlined text-[18px]">filter_list</span>
        {{ t('app.filter_title') }}
      </UiButton>
      <div class="ml-auto flex flex-wrap gap-2">
        <UiButton
          v-if="app.evidenceCollapsed"
          class="hidden lg:inline-flex"
          variant="secondary"
          size="sm"
          @click="app.evidenceCollapsed = false"
        >
          {{ t('app.evidence_nodes') }}
        </UiButton>
        <UiButton class="lg:hidden" variant="secondary" size="sm" @click="app.evidenceSidebarOpen = true">
          {{ t('app.evidence_nodes') }}
        </UiButton>
      </div>
    </div>
    <FilterPanel v-if="!app.filtersCollapsed" class="mb-4" />
    <ChatComposer @send="onSend" />
    <UiNotice v-if="error" class="mt-3" type="error" :message="error" />
    <StreamReport v-if="hasSession" class="mt-4" />
    <ReportActions v-if="hasSession" class="mt-4" />
    <EvidenceSidebarDrawer :open="app.evidenceSidebarOpen" @close="app.evidenceSidebarOpen = false" />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import EvidenceSidebarDrawer from '@/components/evidence/EvidenceSidebarDrawer.vue'
import FilterPanel from '@/components/evidence/FilterPanel.vue'
import ReportActions from '@/components/chat/ReportActions.vue'
import StreamReport from '@/components/chat/StreamReport.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import { useChatStream } from '@/composables/useChatStream'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()
const { send, error } = useChatStream()

const hasSession = computed(
  () => app.activeSessionId !== null || app.messages.some((message) => message.role === 'user'),
)

function onSend(question: string) {
  void send(question)
}
</script>
