<template>
  <section id="governance" class="scroll-mt-24 bg-slate-50 py-16">
    <div class="mx-auto max-w-container-max px-4 md:px-8">
      <h2 class="text-3xl font-semibold text-slate-900">{{ t('landing.governance.title') }}</h2>
      <p class="mt-3 max-w-3xl text-slate-600">{{ t('landing.governance.body1') }}</p>
      <p class="mt-3 max-w-3xl text-slate-600">{{ t('landing.governance.body2') }}</p>
      <div class="mt-6 flex flex-wrap gap-4 text-sm">
        <RouterLink class="text-brand-primary hover:underline" to="/docs/MISSION.md">{{ t('legal.mission') }}</RouterLink>
        <RouterLink class="text-brand-primary hover:underline" to="/docs/ETHICS_AND_OVERSIGHT.md">{{ t('legal.ethics') }}</RouterLink>
        <RouterLink class="text-brand-primary hover:underline" to="/docs/HUMAN_OVERSIGHT.md">{{ t('legal.human_oversight') }}</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>
