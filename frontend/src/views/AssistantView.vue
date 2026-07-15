<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4">
    <ChatComposer @send="onSend" />
    <UiNotice v-if="error" class="mt-3" type="error" :message="error" />
    <StreamReport class="mt-4" />
    <ReportActions class="mt-4" />
  </section>
</template>

<script setup lang="ts">
import ChatComposer from '@/components/chat/ChatComposer.vue'
import ReportActions from '@/components/chat/ReportActions.vue'
import StreamReport from '@/components/chat/StreamReport.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import { useChatStream } from '@/composables/useChatStream'

const { send, error } = useChatStream()

function onSend(question: string) {
  void send(question)
}
</script>
