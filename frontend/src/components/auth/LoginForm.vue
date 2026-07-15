<template>
  <div class="flex min-h-screen flex-col justify-between">
    <div class="flex grow flex-col items-center justify-center p-4">
      <main class="flex w-full max-w-[420px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div class="w-1 rounded-l-lg bg-brand-primary" />
        <div class="relative flex flex-1 flex-col gap-6 p-6">
          <div class="absolute right-4 top-4 flex items-center gap-1 text-xs">
            <button type="button" class="hover:underline" @click="setLocale('en')">EN</button>
            <span>|</span>
            <button type="button" class="hover:underline" @click="setLocale('es')">ES</button>
          </div>
          <RouterLink to="/" class="absolute left-4 top-4 text-sm text-brand-primary hover:underline">{{ t('login.back_home') }}</RouterLink>
          <div class="mt-8 flex flex-col items-center gap-2 text-center">
            <img :src="LOGO_URL" :alt="LOGO_ALT" class="h-10 w-10" />
            <p class="text-xs font-semibold uppercase tracking-widest text-brand-primary">{{ t('login.tagline') }}</p>
          </div>
          <div v-if="panel === 'request'" class="flex flex-col gap-4">
            <div class="text-center">
              <h2 class="text-2xl font-semibold text-slate-900">{{ t('login.sign_in') }}</h2>
              <p class="px-4 text-sm text-slate-600">{{ t('login.intro') }}</p>
            </div>
            <form class="flex flex-col gap-4" @submit.prevent="submit">
              <label class="text-xs font-medium text-slate-600" for="loginEmail">{{ t('login.email_label') }}</label>
              <input
                id="loginEmail"
                v-model="email"
                type="email"
                required
                class="rounded-lg border border-slate-300 px-4 py-2.5 text-sm"
                :placeholder="t('login.email_placeholder')"
              />
              <UiButton type="submit" :loading="loading">{{ t('login.send_magic_link') }}</UiButton>
              <p class="text-center text-xs" :class="statusError ? 'text-red-700' : 'text-slate-500'">{{ statusText }}</p>
            </form>
          </div>
          <div v-else class="flex flex-col gap-4 text-center">
            <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-brand-primary">
              <span class="material-symbols-outlined text-[28px]">mark_email_read</span>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-slate-900">{{ resultTitle }}</h3>
              <p class="px-2 text-sm text-slate-600">{{ resultMessage }}</p>
            </div>
            <a v-if="devLink" :href="devLink" class="text-xs text-brand-primary underline" target="_blank" rel="noopener noreferrer">
              {{ t('login.dev_link') }}
            </a>
            <button type="button" class="text-sm font-medium text-brand-primary hover:underline" @click="panel = 'request'">
              {{ t('login.try_again') }}
            </button>
          </div>
        </div>
      </main>
      <LoginMetadataStats class="mt-4 w-full max-w-[420px]" />
    </div>
    <footer class="mx-auto flex w-full max-w-[1440px] flex-col items-center justify-between gap-4 border-t border-slate-200 bg-slate-100 px-4 py-6 md:flex-row">
      <span class="text-xs text-slate-600">© {{ year }} MTVL AI. {{ t('login.footer') }}</span>
      <div class="flex gap-6">
        <RouterLink class="text-xs text-slate-600 hover:text-brand-primary hover:underline" to="/privacy">{{ t('login.privacy') }}</RouterLink>
        <RouterLink class="text-xs text-slate-600 hover:text-brand-primary hover:underline" to="/terms">{{ t('login.terms') }}</RouterLink>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import LoginMetadataStats from '@/components/auth/LoginMetadataStats.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { setAppLocale } from '@/i18n'
import { requestMagicLink } from '@/api/auth'
import { LOGO_ALT, LOGO_URL } from '@/brand'
import { useAppStore } from '@/stores/app'

const { t } = useI18n()
const app = useAppStore()
const email = ref('')
const loading = ref(false)
const panel = ref<'request' | 'result'>('request')
const statusText = ref('')
const statusError = ref(false)
const resultTitle = ref('')
const resultMessage = ref('')
const devLink = ref('')
const year = new Date().getFullYear()

function setLocale(locale: 'en' | 'es') {
  app.language = locale
  setAppLocale(locale)
}

async function submit() {
  loading.value = true
  statusError.value = false
  try {
    const data = await requestMagicLink(email.value.trim(), app.language)
    panel.value = 'result'
    resultTitle.value = t('login.check_email')
    resultMessage.value = t('login.sent_smtp', { email: data.email })
    devLink.value = data.magic_link || ''
  } catch (err) {
    statusError.value = true
    statusText.value = err instanceof Error ? err.message : t('login.error')
  } finally {
    loading.value = false
  }
}
</script>
