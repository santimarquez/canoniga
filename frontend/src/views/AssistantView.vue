<template>
  <div class="flex h-full min-h-0 w-full flex-col overflow-hidden">
    <div class="flex shrink-0 items-center justify-end gap-2 px-4 pt-2 lg:px-6">
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

    <div
      ref="scrollRef"
      class="min-h-0 flex-1 overflow-y-auto overscroll-contain"
      @scroll="onScroll"
    >
      <div
        class="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-4 lg:px-6"
        :class="app.streaming ? 'min-h-full justify-end' : ''"
      >
        <UiNotice v-if="error" type="error" :message="error" />
        <UiNotice v-if="info" type="info" :message="info" />

        <div v-if="hasSession" class="flex w-full flex-col gap-4">
          <StreamReport ref="streamReportRef" />
          <Transition name="fade-slide">
            <ReportActions v-if="reportReady" />
          </Transition>
        </div>
      </div>
    </div>

    <div class="composer-dock shrink-0 border-t border-slate-200 bg-white px-4 py-4 lg:px-6">
      <div class="mx-auto w-full max-w-3xl">
        <ChatComposer @send="onSend" @open-filters="app.filterModalOpen = true" />
      </div>
    </div>

    <FilterModal :open="app.filterModalOpen" @close="app.filterModalOpen = false" />
    <EvidenceSidebarDrawer :open="app.evidenceSidebarOpen" @close="app.evidenceSidebarOpen = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import EvidenceSidebarDrawer from '@/components/evidence/EvidenceSidebarDrawer.vue'
import FilterModal from '@/components/evidence/FilterModal.vue'
import ReportActions from '@/components/chat/ReportActions.vue'
import StreamReport from '@/components/chat/StreamReport.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import { useChatStream } from '@/composables/useChatStream'
import { useAppStore } from '@/stores/app'

const BOTTOM_THRESHOLD_PX = 64

const { t } = useI18n()
const app = useAppStore()
const { send, error, info } = useChatStream()

const scrollRef = ref<HTMLElement | null>(null)
const streamReportRef = ref<InstanceType<typeof StreamReport> | null>(null)
const stickToBottom = ref(true)
const applyingAutoScroll = ref(false)

const hasSession = computed(
  () => app.activeSessionId !== null || app.messages.some((message) => message.role === 'user'),
)

const reportReady = computed(() => hasSession.value && !app.streaming && Boolean(app.lastReport))

function onSend(question: string) {
  stickToBottom.value = true
  void send(question)
}

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD_PX
}

function scrollToBottom() {
  const el = scrollRef.value
  if (!el || !stickToBottom.value) return
  applyingAutoScroll.value = true
  el.scrollTop = el.scrollHeight
  requestAnimationFrame(() => {
    applyingAutoScroll.value = false
  })
}

function onScroll() {
  if (applyingAutoScroll.value) return
  const el = scrollRef.value
  if (!el) return
  stickToBottom.value = isNearBottom(el)
}

watch(
  () => app.streaming,
  (streaming) => {
    if (streaming) stickToBottom.value = true
  },
)

watch(
  () => [app.streamAnswer, app.streaming] as const,
  async ([, streaming]) => {
    if (!streaming || !stickToBottom.value) return
    await nextTick()
    requestAnimationFrame(scrollToBottom)
  },
)
</script>

<style scoped>
.composer-dock {
  flex-shrink: 0;
  background: #fff;
}
</style>
