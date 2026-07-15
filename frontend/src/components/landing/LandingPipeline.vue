<template>
  <section id="pipeline" class="mx-auto max-w-container-max scroll-mt-24 px-4 py-16 md:px-8">
    <h2 class="text-3xl font-semibold text-slate-900">{{ t('landing.pipeline.title') }}</h2>
    <div class="mt-8 grid gap-4 md:grid-cols-4">
      <article v-for="step in steps" :key="step.title" class="rounded-xl border border-slate-200 p-4">
        <h3 class="font-semibold text-brand-primary">{{ step.title }}</h3>
        <p class="mt-2 text-sm text-slate-600">{{ step.body }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const steps = computed(() => [
  { title: t('landing.pipeline.ingest'), body: t('landing.pipeline.ingest_body') },
  { title: t('landing.pipeline.structure'), body: t('landing.pipeline.structure_body') },
  { title: t('landing.pipeline.investigate'), body: t('landing.pipeline.investigate_body') },
  { title: t('landing.pipeline.validate'), body: t('landing.pipeline.validate_body') },
])
</script>
