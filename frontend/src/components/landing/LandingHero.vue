<template>
  <section class="mx-auto grid max-w-container-max gap-8 px-4 py-16 md:grid-cols-2 md:px-8">
    <div class="space-y-6">
      <p class="text-xs font-semibold uppercase tracking-widest text-brand-primary">{{ t('landing.hero.badge') }}</p>
      <h1 class="text-4xl font-semibold leading-tight text-slate-900 md:text-5xl">{{ t('landing.hero.title') }}</h1>
      <p class="text-base text-slate-600">{{ t('landing.hero.body') }}</p>
      <div class="flex flex-wrap gap-3">
        <UiButton tag="a" :href="ctaHref">{{ ctaLabel }}</UiButton>
        <UiButton tag="a" variant="secondary" href="https://github.com/santimarquez/canoniga" target="_blank">
          {{ t('landing.hero.github') }}
        </UiButton>
      </div>
      <p class="text-sm text-slate-500">{{ t('landing.hero.trust') }}</p>
    </div>
    <img
      :src="LANDING_DASHBOARD_URL"
      :alt="t('landing.hero.mockup_alt')"
      class="rounded-xl border border-slate-200 shadow-lg"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LANDING_DASHBOARD_URL } from '@/brand'
import UiButton from '@/components/ui/UiButton.vue'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()

const ctaHref = computed(() => (!auth.authEnabled || auth.isAuthenticated ? '/app' : '/login'))
const ctaLabel = computed(() =>
  !auth.authEnabled || auth.isAuthenticated
    ? t('landing.cta.continue_investigating')
    : t('landing.cta.sign_in_investigate'),
)
</script>
