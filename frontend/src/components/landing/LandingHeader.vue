<template>
  <header class="sticky top-0 z-20 border-b border-outline-variant/40 bg-white/80 backdrop-blur">
    <div class="mx-auto flex max-w-container-max items-center justify-between px-4 py-4 md:px-8">
      <RouterLink to="/" class="flex items-center gap-2 text-brand-dark">
        <img :src="LOGO_URL" :alt="LOGO_ALT" class="h-8 w-8" />
        <span class="font-semibold">MTVL AI</span>
      </RouterLink>
      <nav class="hidden items-center gap-6 text-sm text-slate-600 md:flex">
        <RouterLink
          v-for="item in navItems"
          :key="item.hash"
          :to="{ path: '/', hash: item.hash }"
          class="hover:text-brand-primary"
        >
          {{ t(item.label) }}
        </RouterLink>
      </nav>
      <div class="flex items-center gap-3">
        <LangToggle />
        <UiButton tag="a" :href="ctaHref">{{ ctaLabel }}</UiButton>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import LangToggle from '@/components/ui/LangToggle.vue'
import { LOGO_ALT, LOGO_URL } from '@/brand'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()

const navItems = [
  { hash: '#database', label: 'landing.nav.database' },
  { hash: '#features', label: 'landing.nav.features' },
  { hash: '#pipeline', label: 'landing.nav.how_it_works' },
  { hash: '#governance', label: 'landing.nav.governance' },
] as const

onMounted(() => {
  void auth.refresh()
})

const ctaHref = computed(() => {
  if (!auth.authEnabled || auth.isAuthenticated) return '/app'
  return '/login'
})

const ctaLabel = computed(() => {
  if (!auth.authEnabled || auth.isAuthenticated) return t('landing.cta.open_investigator')
  return t('landing.cta.get_started')
})
</script>
