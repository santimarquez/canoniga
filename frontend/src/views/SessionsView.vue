<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4">
    <div class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold text-slate-900">{{ t('app.saved_sessions') }}</h2>
      <UiButton variant="secondary" size="sm" :loading="loading" @click="load">{{ t('app.refresh') }}</UiButton>
    </div>
    <div v-if="sessions.length === 0" class="text-sm text-slate-500">{{ t('app.no_saved_sessions') }}</div>
    <div class="space-y-2">
      <button
        v-for="session in sessions"
        :key="session.session_id"
        type="button"
        class="w-full rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50"
        @click="openSession(session.session_id)"
      >
        <p class="font-medium text-slate-900">{{ session.title }}</p>
        <p class="text-xs text-slate-500">{{ session.updated_at }}</p>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { fetchSession, fetchSessions } from '@/api/app'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'
import type { SessionSummary } from '@/types/api'

const { t } = useI18n()
const app = useAppStore()
const router = useRouter()
const sessions = ref<SessionSummary[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await fetchSessions()
    sessions.value = data.sessions
  } finally {
    loading.value = false
  }
}

async function openSession(sessionId: string) {
  const data = await fetchSession(sessionId)
  app.applySession({
    session_id: data.session_id,
    messages: data.messages,
    report: data.report,
    filters: data.filters,
  })
  await router.push({ name: 'assistant' })
}

onMounted(() => {
  void load()
})
</script>
