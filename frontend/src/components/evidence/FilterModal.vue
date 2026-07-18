<template>
  <UiModal
    :open="open"
    :title="t('app.filter_title')"
    panel-class="max-w-lg"
    @close="onClose"
  >
    <div data-tutorial="filters">
      <FilterPanel />
    </div>
    <template #footer>
      <UiButton class="w-full" @click="onApply">{{ t('app.apply') }}</UiButton>
    </template>
  </UiModal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FilterPanel from '@/components/evidence/FilterPanel.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiModal from '@/components/ui/UiModal.vue'
import { tutorialSignal } from '@/composables/useTutorial'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()

function onClose() {
  emit('close')
}

function onApply() {
  tutorialSignal('filters_applied')
  emit('close')
}
</script>
