<template>
  <Teleport to="body">
    <div
      class="pointer-events-none fixed right-4 top-4 z-[80] flex w-[min(100vw-2rem,24rem)] flex-col gap-2"
      aria-live="polite"
      aria-relevant="additions"
    >
      <TransitionGroup name="toast">
        <div
          v-for="item in toast.items"
          :key="item.id"
          class="pointer-events-auto shadow-lg"
        >
          <UiNotice :type="item.type" :message="resolveMessage(item.message)" />
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import UiNotice from '@/components/ui/UiNotice.vue'
import { useToastStore } from '@/stores/toast'

const { t, te } = useI18n()
const toast = useToastStore()

function resolveMessage(message: string): string {
  if (!message) return ''
  return te(`app.${message}`) ? String(t(`app.${message}`)) : message
}
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}
.toast-move {
  transition: transform 0.2s ease;
}
</style>
