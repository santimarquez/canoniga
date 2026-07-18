<template>
  <UiPopover
    ref="menuRef"
    align="left"
    side="top"
    panel-class="w-[300px] overflow-hidden p-0"
  >
    <template #trigger="{ toggle }">
      <button
        type="button"
        class="inline-flex max-w-[10.5rem] items-center gap-0.5 rounded-lg px-2 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        :disabled="disabled"
        :aria-label="t('app.model_picker_aria')"
        @click="toggle"
      >
        <span class="truncate">{{ selectedLabel }}</span>
        <span class="material-symbols-outlined text-[16px] text-slate-400">expand_more</span>
      </button>
    </template>

    <div class="flex flex-col">
      <div class="border-b border-slate-200 px-3 py-2.5">
        <input
          v-model="query"
          type="search"
          class="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
          :placeholder="t('app.model_search_placeholder')"
          autocomplete="off"
          autofocus
          @click.stop
          @keydown.enter.prevent="selectFirstResult"
        />
      </div>

      <div class="p-2">
        <div
          v-if="showAutoCard"
          class="flex items-start justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3"
        >
          <div class="min-w-0">
            <p class="text-sm font-semibold text-slate-900">{{ t('app.model_auto') }}</p>
            <p class="mt-1 text-xs leading-snug text-slate-500">{{ t('app.model_auto_hint') }}</p>
          </div>
          <button
            type="button"
            role="switch"
            class="relative mt-0.5 h-5 w-9 shrink-0 rounded-full bg-emerald-500 transition-colors"
            :aria-checked="true"
            :aria-label="t('app.model_auto')"
            @click.stop="setAuto(false)"
          >
            <span class="absolute top-0.5 left-0.5 size-4 translate-x-4 rounded-full bg-white shadow" />
          </button>
        </div>

        <div
          v-else-if="showAutoToggle"
          class="flex items-center justify-between gap-3 px-1 py-2"
        >
          <span class="text-sm font-medium text-slate-900">{{ t('app.model_auto') }}</span>
          <button
            type="button"
            role="switch"
            class="relative h-5 w-9 shrink-0 rounded-full transition-colors"
            :class="autoEnabled ? 'bg-emerald-500' : 'bg-slate-300'"
            :aria-checked="autoEnabled"
            :aria-label="t('app.model_auto')"
            @click.stop="setAuto(!autoEnabled)"
          >
            <span
              class="absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow transition-transform"
              :class="autoEnabled ? 'translate-x-4' : 'translate-x-0'"
            />
          </button>
        </div>

        <div v-if="showModelList" class="mt-1">
          <div
            v-if="showAutoToggle || showAutoCard"
            class="mb-1 border-t border-slate-200"
          />

          <p v-if="error" class="px-2 py-2 text-xs text-amber-700">{{ error }}</p>
          <p v-else-if="!loading && filteredModels.length === 0" class="px-2 py-2 text-xs text-slate-500">
            {{ models.length === 0 ? t('app.model_catalog_empty') : t('app.model_search_empty') }}
          </p>

          <div class="max-h-56 overflow-y-auto">
            <button
              v-for="model in filteredModels"
              :key="model.id"
              type="button"
              class="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left hover:bg-slate-50"
              :class="selection === model.name ? 'bg-slate-100' : ''"
              @click="choose(model.name)"
            >
              <span class="min-w-0">
                <span class="block truncate text-sm font-medium text-slate-900">{{ model.name }}</span>
                <span
                  class="block text-xs text-slate-500"
                  :title="t('app.model_quality_estimate')"
                >{{ modelQuality(model) }}</span>
              </span>
              <span
                v-if="selection === model.name"
                class="material-symbols-outlined shrink-0 text-[16px] text-slate-700"
              >check</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </UiPopover>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchModels } from '@/api/app'
import UiPopover from '@/components/ui/UiPopover.vue'
import { useAppStore } from '@/stores/app'
import type { OllamaModelInfo } from '@/types/api'

defineProps<{ disabled?: boolean }>()

const { t } = useI18n()
const app = useAppStore()
const menuRef = ref<InstanceType<typeof UiPopover> | null>(null)
const models = ref<OllamaModelInfo[]>([])
const loading = ref(false)
const error = ref('')
const query = ref('')

const selection = computed(() => app.config.modelSelection || 'auto')
const autoEnabled = computed(() => selection.value === 'auto')
const hasSearch = computed(() => Boolean(query.value.trim()))

const selectedLabel = computed(() => {
  if (selection.value === 'auto') return t('app.model_auto')
  return selection.value
})

const autoMatchesSearch = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return true
  return t('app.model_auto').toLowerCase().includes(needle)
})

const filteredModels = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return models.value
  return models.value.filter((row) => row.name.toLowerCase().includes(needle))
})

/** Featured Auto card when Auto is on and the user is not searching. */
const showAutoCard = computed(() => autoEnabled.value && !hasSearch.value)

/** Compact Auto toggle when Auto is off, or while searching and Auto still matches. */
const showAutoToggle = computed(() => {
  if (showAutoCard.value) return false
  if (!hasSearch.value) return true
  return autoMatchesSearch.value
})

/** Model list when Auto is off, or whenever the user is searching. */
const showModelList = computed(() => !autoEnabled.value || hasSearch.value)

function choose(value: string) {
  query.value = ''
  app.setModelSelection(value)
  menuRef.value?.close()
}

function setAuto(enabled: boolean) {
  if (enabled) {
    query.value = ''
    app.setModelSelection('auto')
    return
  }
  const fallback = filteredModels.value[0]?.name || models.value[0]?.name
  if (fallback) {
    app.setModelSelection(fallback)
  }
}

function selectFirstResult() {
  if (hasSearch.value && autoMatchesSearch.value && filteredModels.value.length === 0) {
    setAuto(true)
    menuRef.value?.close()
    return
  }
  const first = filteredModels.value[0]
  if (first) choose(first.name)
}

function modelQuality(model: OllamaModelInfo): string {
  const parameterCount = model.name.match(/(?:^|[:\s-])(\d+(?:\.\d+)?)b(?:$|[-_:])/i)
  const billions = parameterCount ? Number(parameterCount[1]) : null

  if (billions === null || Number.isNaN(billions)) {
    return t('app.model_quality_standard')
  }
  if (billions <= 3.5) return t('app.model_quality_fast')
  if (billions <= 8) return t('app.model_quality_balanced')
  if (billions <= 20) return t('app.model_quality_high')
  return t('app.model_quality_best')
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const catalog = await fetchModels()
    models.value = catalog.models ?? []
    if (catalog.error) {
      error.value = t('app.model_catalog_unavailable')
    }
    if (
      selection.value !== 'auto' &&
      models.value.length > 0 &&
      !models.value.some((row) => row.name === selection.value)
    ) {
      app.setModelSelection('auto')
    }
  } catch {
    error.value = t('app.model_catalog_unavailable')
    models.value = []
  } finally {
    loading.value = false
  }
})
</script>
