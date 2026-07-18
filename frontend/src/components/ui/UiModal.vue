<template>
  <Teleport to="body">
    <Transition name="overlay-fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <button
          class="absolute inset-0 bg-black/40 backdrop-blur-sm"
          type="button"
          aria-label="Close"
          @click="$emit('close')"
        />
        <div
          class="ui-modal-panel relative z-10 flex max-h-[calc(100vh-2rem)] w-full flex-col overflow-hidden rounded-xl bg-white shadow-xl"
          :class="panelClass"
        >
          <header
            v-if="title || $slots.header"
            class="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-4"
          >
            <slot name="header">
              <h2 class="text-lg font-semibold text-slate-900">{{ title }}</h2>
            </slot>
            <UiIconButton @click="$emit('close')">close</UiIconButton>
          </header>
          <div class="flex min-h-0 flex-1 flex-col overflow-hidden px-5 py-4" :class="bodyClass">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="border-t border-slate-200 px-5 py-4">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import UiIconButton from './UiIconButton.vue'

defineProps<{ open: boolean; title?: string; panelClass?: string; bodyClass?: string }>()
defineEmits<{ close: [] }>()
</script>
