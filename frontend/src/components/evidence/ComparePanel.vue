<template>
  <div class="space-y-2" data-tutorial="compare">
    <input
      v-model="app.compareClaimA"
      class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      :placeholder="t('app.claim_a')"
    />
    <input
      v-model="app.compareClaimB"
      class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      :placeholder="t('app.claim_b')"
    />
    <UiButton size="sm" :loading="app.compareLoading" @click="run">{{ t('app.run_compare') }}</UiButton>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()

async function run() {
  await app.runCompare({ openModal: true })
}
</script>
