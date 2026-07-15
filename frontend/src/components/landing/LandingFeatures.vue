<template>
  <section id="features" class="scroll-mt-24 bg-slate-50 py-16">
    <div class="mx-auto max-w-container-max px-4 md:px-8">
      <h2 class="text-3xl font-semibold text-slate-900">{{ t('landing.features.title') }}</h2>
      <p class="mt-2 text-slate-600">{{ t('landing.features.subtitle') }}</p>
      <div class="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <article v-for="card in cards" :key="card.title" class="rounded-xl border border-slate-200 bg-white p-5">
          <h3 class="font-semibold text-slate-900">{{ card.title }}</h3>
          <p class="mt-2 text-sm text-slate-600">{{ card.body }}</p>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const cards = computed(() => [
  { title: t('landing.features.sync_title'), body: t('landing.features.sync_body') },
  { title: t('landing.features.extract_title'), body: t('landing.features.extract_body') },
  { title: t('landing.features.chat_title'), body: t('landing.features.chat_body') },
  { title: t('landing.features.hypothesis_title'), body: t('landing.features.hypothesis_body') },
  { title: t('landing.features.atlas_title'), body: t('landing.features.atlas_body') },
  { title: t('landing.features.automation_title'), body: t('landing.features.automation_body') },
])
</script>
