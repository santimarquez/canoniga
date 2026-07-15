<template>
  <UiPopover ref="popoverRef" align="left">
    <template #trigger="{ toggle }">
      <button
        type="button"
        class="relative inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white p-2 text-brand-primary hover:bg-slate-50"
        :title="statusTitle"
        :aria-label="statusTitle"
        @click="toggle"
      >
        <span class="material-symbols-outlined text-[20px]">database</span>
        <span
          class="absolute right-1 top-1 size-2.5 rounded-full ring-2 ring-white"
          :class="statusDotClass"
        />
      </button>
    </template>

    <div class="flex w-[380px] flex-col gap-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="text-sm font-semibold text-slate-900">{{ t('app.db_popover_title') }}</h3>
          <p class="mt-1 text-xs text-slate-600">{{ statusTitle }}</p>
        </div>
        <div class="text-right">
          <p class="text-lg font-semibold text-brand-primary">{{ recordsTotal }}</p>
          <p class="text-[11px] text-slate-500">{{ t('app.db_popover_total_label') }}</p>
        </div>
      </div>

      <p v-if="lastSyncLabel" class="text-xs text-slate-500">
        {{ t('app.db_popover_last_sync') }}: {{ lastSyncLabel }}
      </p>

      <DbSourceBreakdown :rows="sourceBreakdown" :empty-label="t('login.no_sources')" />

      <UiButton class="w-full" variant="secondary" @click="openExplorer">
        <span class="material-symbols-outlined text-[18px]">manage_search</span>
        {{ t('app.db_open_hint') }}
      </UiButton>

      <UiNotice v-if="flashMessage" :type="status.flash?.type || 'info'" :message="flashMessage" />

      <div v-if="active" class="space-y-2 border-t border-slate-100 pt-3">
        <p class="text-xs font-medium text-slate-700">{{ t('app.sync_progress_title') }}</p>
        <UiProgress :value="progressPercent" />
        <p class="text-xs text-slate-600">{{ progressDetail }}</p>
        <p v-if="etaLabel" class="text-xs text-slate-500">{{ etaLabel }}</p>
      </div>

      <div v-else class="space-y-3 border-t border-slate-100 pt-3">
        <UiButton
          class="w-full"
          :disabled="!manualSync?.can_trigger_all"
          :loading="triggeringAll"
          @click="triggerAll"
        >
          {{ t('app.sync_update_all') }}
        </UiButton>
        <div>
          <p class="mb-2 text-xs font-medium text-slate-700">{{ t('app.sync_sources_title') }}</p>
          <ManualSyncSourceList />
        </div>
      </div>

      <p v-if="syncError" class="text-xs text-red-700">{{ syncError }}</p>
    </div>
  </UiPopover>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DbSourceBreakdown from '@/components/db/DbSourceBreakdown.vue'
import ManualSyncSourceList from '@/components/db/ManualSyncSourceList.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import UiPopover from '@/components/ui/UiPopover.vue'
import UiProgress from '@/components/ui/UiProgress.vue'
import { formatRelativeTime } from '@/i18n/time'
import { useAppStore } from '@/stores/app'
import { useStatusStore } from '@/stores/status'

const { t, te } = useI18n()
const status = useStatusStore()
const app = useAppStore()
const popoverRef = ref<InstanceType<typeof UiPopover> | null>(null)
const triggeringAll = ref(false)

const manualSync = computed(() => status.manualSync)
const active = computed(() => Boolean(manualSync.value?.manual_sync_active || manualSync.value?.in_progress))
const progressPercent = computed(() => manualSync.value?.progress_percent ?? 0)
const syncError = computed(() => manualSync.value?.error || '')
const sourceBreakdown = computed(() => status.snapshot?.source_breakdown ?? [])
const recordsTotal = computed(() => status.snapshot?.records_total ?? 0)

const statusTitle = computed(() => {
  if (active.value) return t('app.in_progress')
  if (!status.snapshot) return t('app.db_popover_loading')
  if (!status.snapshot.db_synced) return t('app.db_out_of_sync')
  if ((status.snapshot.records_total ?? 0) === 0) return t('app.db_popover_waiting')
  return t('app.db_popover_ready')
})

const statusDotClass = computed(() => {
  if (active.value) return 'bg-amber-500'
  if (!status.snapshot) return 'bg-slate-400'
  if (!status.snapshot.db_synced) return 'bg-red-500'
  if ((status.snapshot.records_total ?? 0) === 0) return 'bg-amber-500'
  return 'bg-emerald-500'
})

const lastSyncLabel = computed(() => {
  const stamp = status.snapshot?.latest_sync_at
  return stamp ? formatRelativeTime(stamp) : ''
})

const progressDetail = computed(() => {
  const done = manualSync.value?.completed_sources ?? 0
  const total = manualSync.value?.total_sources ?? 0
  const source = manualSync.value?.current_source || manualSync.value?.current_scope || ''
  return t('app.sync_progress_step', { done, total, source })
})

const etaLabel = computed(() => {
  const seconds = manualSync.value?.estimated_remaining_seconds ?? 0
  if (!seconds) return ''
  const minutes = Math.max(1, Math.round(seconds / 60))
  return t('app.sync_progress_eta_remaining', { time: `${minutes}m` })
})

const flashMessage = computed(() => {
  const key = status.flash?.message
  if (!key) return ''
  return te(`app.${key}`) ? t(`app.${key}`) : key
})

function openExplorer() {
  popoverRef.value?.close()
  app.dbExplorerOpen = true
}

async function triggerAll() {
  triggeringAll.value = true
  try {
    await status.trigger({ scope: 'all' })
  } catch (err) {
    status.setFlash({
      type: 'error',
      message: err instanceof Error ? err.message : t('app.sync_failed'),
    })
  } finally {
    triggeringAll.value = false
  }
}
</script>
