<template>
  <div class="w-full">
    <Transition name="fade-slide">
      <p
        v-if="statusVisible && statusText"
        class="mb-2 flex items-center gap-2 px-1 text-xs text-slate-600"
      >
        <span class="loading-dot shrink-0" aria-hidden="true" />
        <span>{{ statusText }}</span>
      </p>
    </Transition>

    <div
      data-tutorial="query"
      class="relative w-full rounded-2xl border border-slate-300 bg-white shadow-sm focus-within:border-brand-primary focus-within:ring-2 focus-within:ring-brand-primary/15"
    >
      <textarea
        ref="textareaRef"
        v-model="question"
        rows="1"
        class="block w-full resize-none border-0 bg-transparent px-4 pb-12 pt-4 text-sm text-slate-900 outline-none placeholder:text-slate-400"
        :placeholder="t('app.question_placeholder')"
        :disabled="app.streaming"
        @input="onInput"
        @keydown.enter.exact.prevent="submit"
      />

      <div class="absolute bottom-2 left-2 flex items-center gap-1">
        <UiPopover ref="menuRef" align="left" side="top" panel-class="min-w-[240px] p-1">
          <template #trigger="{ toggle }">
            <button
              type="button"
              class="inline-flex size-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100"
              :aria-label="t('app.composer_add_menu')"
              @click="toggle"
            >
              <span class="material-symbols-outlined text-[22px]">add</span>
            </button>
          </template>
          <button
            type="button"
            class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
            @click="openExplorer"
          >
            <span class="material-symbols-outlined text-[18px] text-slate-500">manage_search</span>
            {{ t('app.db_open_hint') }}
          </button>
          <button
            type="button"
            class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
            @click="openFilters"
          >
            <span class="material-symbols-outlined text-[18px] text-slate-500">filter_list</span>
            {{ t('app.modify_filter_rules') }}
          </button>
        </UiPopover>
        <ModelPicker :disabled="app.streaming" />
      </div>

      <button
        type="button"
        data-tutorial="send"
        class="absolute bottom-2 right-2 inline-flex size-9 items-center justify-center rounded-lg bg-brand-primary text-white transition-colors hover:bg-brand-accent disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!canSubmit"
        :aria-label="t('app.title_send')"
        @click="submit"
      >
        <span v-if="app.streaming" class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span>
        <span v-else class="material-symbols-outlined text-[20px]">arrow_upward</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelPicker from '@/components/chat/ModelPicker.vue'
import UiPopover from '@/components/ui/UiPopover.vue'
import { useStreamStatus } from '@/composables/useStreamStatus'
import { tutorialSignal, useTutorial } from '@/composables/useTutorial'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()
const tutorial = useTutorial()
const { statusText, statusVisible } = useStreamStatus()

const question = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const menuRef = ref<InstanceType<typeof UiPopover> | null>(null)

const emit = defineEmits<{
  send: [question: string]
  'open-filters': []
}>()

/** On the query tutorial step, typing is allowed but Send must wait for Paso 2. */
const sendBlockedByTutorial = computed(
  () => tutorial.state.running && tutorial.currentStep.value?.id === 'query',
)

const canSubmit = computed(
  () => Boolean(question.value.trim()) && !app.streaming && !sendBlockedByTutorial.value,
)

function resizeTextarea() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

function onInput() {
  resizeTextarea()
  if (question.value.trim()) tutorialSignal('question_typed')
}

function submit() {
  if (!canSubmit.value) return
  const value = question.value.trim()
  emit('send', value)
  question.value = ''
  void nextTick(resizeTextarea)
}

function openExplorer() {
  menuRef.value?.close()
  app.dbExplorerOpen = true
  tutorialSignal('db_explorer_opened')
}

function openFilters() {
  menuRef.value?.close()
  app.filterModalOpen = true
  emit('open-filters')
}

onMounted(() => {
  resizeTextarea()
})
</script>
