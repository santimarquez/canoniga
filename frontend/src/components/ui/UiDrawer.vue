<template>
  <Teleport to="body">
    <Transition name="overlay-fade">
      <div v-if="open" class="fixed inset-0 z-50">
        <button
          class="absolute inset-0 bg-black/30 backdrop-blur-sm"
          type="button"
          aria-label="Close"
          @click="$emit('close')"
        />
        <aside
          class="ui-drawer-panel absolute top-0 flex h-full w-full max-w-md flex-col bg-white shadow-2xl"
          :class="[
            side === 'right' ? 'right-0 ui-drawer-panel-right' : 'left-0 ui-drawer-panel-left',
          ]"
        >
          <header class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <h2 class="text-lg font-semibold text-slate-900">{{ title }}</h2>
            <UiIconButton @click="$emit('close')">close</UiIconButton>
          </header>
          <div class="flex-1 overflow-y-auto px-5 py-4">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="border-t border-slate-200 px-5 py-4">
            <slot name="footer" />
          </footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import UiIconButton from './UiIconButton.vue'

withDefaults(defineProps<{ open: boolean; title: string; side?: 'left' | 'right' }>(), {
  side: 'right',
})
defineEmits<{ close: [] }>()
</script>
