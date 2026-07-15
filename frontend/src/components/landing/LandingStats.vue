<template>
  <section class="border-y border-slate-200 bg-white py-12">
    <div class="mx-auto grid max-w-container-max grid-cols-2 gap-6 px-4 md:grid-cols-4 md:px-8">
      <div v-for="item in items" :key="item.label" class="text-center">
        <p class="text-3xl font-semibold text-brand-primary">{{ item.value }}</p>
        <p class="mt-1 text-sm text-slate-600">{{ item.label }}</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const items = computed(() => [
  { value: '15', label: t('landing.stats.sources') },
  { value: '10k+', label: t('landing.stats.records') },
  { value: 'CI', label: t('landing.stats.quality') },
  { value: '100%', label: t('landing.stats.fidelity') },
])
</script>
