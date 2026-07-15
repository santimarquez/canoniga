<template>
  <UiDrawer :open="app.claimDrawerOpen" :title="title" side="right" @close="close">
    <ClaimLineagePanel v-if="app.claimDrawerClaimId" :claim-id="app.claimDrawerClaimId" />
  </UiDrawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ClaimLineagePanel from '@/components/evidence/ClaimLineagePanel.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()

const title = computed(() => app.claimDrawerClaimId || t('app.lineage_claim_details'))

function close() {
  app.claimDrawerOpen = false
}
</script>
