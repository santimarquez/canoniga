<template>
  <UiDrawer :open="open" :title="t('app.evidence_nodes')" side="right" @close="$emit('close')">
    <EvidenceSidebar embedded />
  </UiDrawer>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import EvidenceSidebar from '@/components/evidence/EvidenceSidebar.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'

defineProps<{ open: boolean }>()
defineEmits<{ close: [] }>()

const { t } = useI18n()
</script>
