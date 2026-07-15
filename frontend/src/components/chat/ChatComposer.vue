<template>
  <form class="flex flex-col gap-3" @submit.prevent="submit">
    <label class="text-sm font-medium text-slate-700">{{ t('app.query_evidence') }}</label>
    <textarea
      v-model="question"
      class="min-h-[120px] rounded-xl border border-slate-300 px-4 py-3 text-sm"
      :placeholder="t('app.question_placeholder')"
      :disabled="app.streaming"
    />
    <div class="flex flex-wrap gap-2">
      <UiButton type="submit" :loading="app.streaming" :disabled="!question.trim()">
        <span class="material-symbols-outlined text-[18px]">send</span>
        {{ t('app.title_send') }}
      </UiButton>
      <UiButton variant="secondary" type="button" @click="app.dbExplorerOpen = true">
        {{ t('app.db_open_hint') }}
      </UiButton>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()
const question = ref('')

const emit = defineEmits<{ send: [question: string] }>()

function submit() {
  const value = question.value.trim()
  if (!value || app.streaming) return
  emit('send', value)
  question.value = ''
}
</script>
