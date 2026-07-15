<template>
  <div class="flex items-center gap-1 text-sm text-slate-600" :aria-label="t('common.lang.label')">
    <button
      type="button"
      class="transition-colors"
      :class="locale === 'en' ? 'font-semibold text-brand-primary' : 'hover:text-brand-primary'"
      @click="setLocale('en')"
    >
      {{ t('common.lang.en') }}
    </button>
    <span aria-hidden="true">|</span>
    <button
      type="button"
      class="transition-colors"
      :class="locale === 'es' ? 'font-semibold text-brand-primary' : 'hover:text-brand-primary'"
      @click="setLocale('es')"
    >
      {{ t('common.lang.es') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { setAppLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'

const { t, locale: i18nLocale } = useI18n()
const app = useAppStore()

const locale = computed(() => (i18nLocale.value === 'es' ? 'es' : 'en'))

function setLocale(next: 'en' | 'es') {
  app.language = next
  setAppLocale(next)
}
</script>
