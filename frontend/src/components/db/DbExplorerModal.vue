<template>
  <UiModal
    :open="app.dbExplorerOpen"
    panel-class="h-[calc(100vh-2rem)] max-w-4xl"
    @close="close"
  >
    <template #header>
      <div v-if="view === 'detail'" class="flex min-w-0 flex-1 items-center gap-2">
        <UiIconButton :aria-label="t('app.db_back_to_list')" @click="backToList">arrow_back</UiIconButton>
        <h2 class="truncate text-lg font-semibold text-slate-900">{{ selectedClaimId }}</h2>
      </div>
      <h2 v-else class="text-lg font-semibold text-slate-900">{{ t('app.db_explorer_title') }}</h2>
    </template>

    <div class="relative min-h-0 flex-1">
      <div
        v-show="view === 'list'"
        class="absolute inset-0 flex flex-col gap-3"
      >
        <form class="shrink-0 space-y-2" @submit.prevent="runSearch">
        <label class="block text-xs font-medium text-slate-700" for="dbExplorerSearch">
          {{ t('app.db_search_label') }}
        </label>
        <div class="flex gap-2">
          <input
            id="dbExplorerSearch"
            v-model="query"
            class="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            :placeholder="t('app.db_search_placeholder')"
            autocomplete="off"
          />
          <UiButton type="submit" :loading="loading && !loadingMore">{{ t('app.db_search') }}</UiButton>
          <UiButton variant="secondary" type="button" @click="clear">{{ t('app.db_clear') }}</UiButton>
        </div>
      </form>

      <div
        ref="listRef"
        class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-200"
        @scroll="onScroll"
      >
        <div v-if="loading && rows.length === 0" class="flex justify-center py-12">
          <UiSpinner size="lg" />
        </div>
        <p v-else-if="rows.length === 0" class="p-4 text-sm text-slate-500">{{ t('app.db_no_rows') }}</p>
        <div v-else class="divide-y divide-slate-100">
          <button
            v-for="row in rows"
            :key="row.claim_id"
            type="button"
            class="block w-full px-4 py-3 text-left hover:bg-slate-50"
            @click="openClaim(row.claim_id)"
          >
            <p class="text-sm font-medium text-slate-900">{{ row.claim_id }}</p>
            <p class="mt-1 line-clamp-2 text-xs text-slate-600">{{ row.claim_text }}</p>
            <p class="mt-1 text-[11px] text-slate-500">
              {{ row.entity }} · {{ row.outcome }} · {{ formatReliability(row.reliability_score) }}
            </p>
          </button>
        </div>
        <div v-if="loadingMore" class="flex justify-center py-4">
          <UiSpinner size="sm" />
        </div>
      </div>

      <p class="shrink-0 text-xs text-slate-500">
        {{ t('app.db_results_count', { shown: rows.length, total }) }}
      </p>
      </div>

      <div
        v-show="view === 'detail'"
        class="absolute inset-0 overflow-y-auto"
      >
        <ClaimLineagePanel :claim-id="selectedClaimId" />
      </div>
    </div>
  </UiModal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { searchDatabaseNodes } from '@/api/app'
import ClaimLineagePanel from '@/components/evidence/ClaimLineagePanel.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiModal from '@/components/ui/UiModal.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useAppStore } from '@/stores/app'
import type { DatabaseNodeRow } from '@/types/api'

const PAGE_SIZE = 30
const SCROLL_THRESHOLD_PX = 120

type ExplorerView = 'list' | 'detail'

const { t } = useI18n()
const app = useAppStore()
const view = ref<ExplorerView>('list')
const selectedClaimId = ref('')
const query = ref('')
const rows = ref<DatabaseNodeRow[]>([])
const offset = ref(0)
const total = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const listRef = ref<HTMLElement | null>(null)
const listScrollTop = ref(0)

async function fetchPage(reset: boolean) {
  if (reset) {
    if (loading.value) return
    loading.value = true
    offset.value = 0
    hasMore.value = false
  } else {
    if (loading.value || loadingMore.value || !hasMore.value) return
    loadingMore.value = true
  }

  try {
    const data = await searchDatabaseNodes({
      query: query.value.trim(),
      limit: PAGE_SIZE,
      offset: offset.value,
    })
    rows.value = reset ? data.rows : [...rows.value, ...data.rows]
    total.value = data.total
    hasMore.value = data.has_more
    offset.value = rows.value.length
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function runSearch() {
  if (listRef.value) listRef.value.scrollTop = 0
  listScrollTop.value = 0
  void fetchPage(true)
}

function clear() {
  query.value = ''
  runSearch()
}

function onScroll() {
  const el = listRef.value
  if (!el || loading.value || loadingMore.value || !hasMore.value) return
  const remaining = el.scrollHeight - el.scrollTop - el.clientHeight
  if (remaining <= SCROLL_THRESHOLD_PX) {
    void fetchPage(false)
  }
}

function openClaim(claimId: string) {
  if (listRef.value) listScrollTop.value = listRef.value.scrollTop
  selectedClaimId.value = claimId
  view.value = 'detail'
}

function backToList() {
  view.value = 'list'
  if (listRef.value) listRef.value.scrollTop = listScrollTop.value
}

function formatReliability(score: number) {
  return `${Math.round((score || 0) * 100)}%`
}

function close() {
  app.dbExplorerOpen = false
}

function resetState() {
  view.value = 'list'
  selectedClaimId.value = ''
  query.value = ''
  rows.value = []
  offset.value = 0
  total.value = 0
  hasMore.value = false
  loading.value = false
  loadingMore.value = false
  listScrollTop.value = 0
}

watch(
  () => app.dbExplorerOpen,
  (open) => {
    if (open) {
      void fetchPage(true)
      return
    }
    resetState()
  },
)
</script>
