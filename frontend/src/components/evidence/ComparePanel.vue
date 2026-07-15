<template>
  <div class="space-y-2">
    <input v-model="claimA" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" :placeholder="t('app.claim_a')" />
    <input v-model="claimB" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" :placeholder="t('app.claim_b')" />
    <UiButton size="sm" :loading="loading" @click="run">{{ t('app.run_compare') }}</UiButton>
    <div v-if="result" class="rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
      <p>{{ t('app.shared_supporting', { count: result.shared_supporting_count }) }}</p>
      <p>{{ t('app.shared_contradicting', { count: result.shared_contradicting_count }) }}</p>
      <p class="mt-2">{{ result.follow_up_suggestion }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { compareEvidence } from '@/api/chat'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'
import type { CompareResponse } from '@/types/api'

const { t } = useI18n()
const app = useAppStore()
const claimA = ref('')
const claimB = ref('')
const loading = ref(false)
const result = ref<CompareResponse | null>(null)

async function run() {
  if (!claimA.value || !claimB.value) return
  loading.value = true
  try {
    result.value = await compareEvidence(claimA.value, claimB.value)
    app.currentCompare = result.value
  } finally {
    loading.value = false
  }
}
</script>
