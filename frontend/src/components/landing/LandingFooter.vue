<template>
  <footer class="border-t border-slate-200 bg-slate-100 py-10">
    <div class="mx-auto grid max-w-container-max gap-8 px-4 md:grid-cols-2 md:px-8">
      <div>
        <p class="font-semibold text-brand-dark">MTVL AI</p>
        <p class="mt-2 text-sm text-slate-600">© {{ year }} MTVL AI. {{ t('landing.footer.body') }}</p>
      </div>
      <div class="grid grid-cols-2 gap-6 text-sm">
        <div>
          <h6 class="font-semibold uppercase tracking-widest text-brand-primary">{{ t('landing.footer.resources') }}</h6>
          <ul class="mt-2 space-y-1 text-slate-600">
            <li><RouterLink to="/docs/MISSION.md">{{ t('landing.nav.documentation') }}</RouterLink></li>
            <li><a href="https://github.com/santimarquez/canoniga" target="_blank" rel="noopener noreferrer">GitHub</a></li>
          </ul>
        </div>
        <div>
          <h6 class="font-semibold uppercase tracking-widest text-brand-primary">{{ t('landing.footer.legal') }}</h6>
          <ul class="mt-2 space-y-1 text-slate-600">
            <li><RouterLink to="/privacy">{{ t('landing.footer.privacy') }}</RouterLink></li>
            <li><RouterLink to="/terms">{{ t('landing.footer.terms') }}</RouterLink></li>
          </ul>
        </div>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const year = new Date().getFullYear()
</script>
