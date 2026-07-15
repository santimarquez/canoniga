<template>
  <header class="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
    <div class="mx-auto flex max-w-[1600px] items-center gap-3 px-4 py-3">
      <div class="flex min-w-0 items-center gap-3">
        <RouterLink to="/" class="flex shrink-0 items-center gap-2 text-brand-primary">
          <img :src="LOGO_URL" :alt="LOGO_ALT" class="h-8 w-8" />
          <span class="hidden text-sm font-semibold lg:inline">MTVL AI</span>
        </RouterLink>

        <div class="hidden h-6 w-px bg-slate-200 sm:block" />

        <div class="flex items-center gap-2">
          <StatusBar />
          <DbStatusPopover />
        </div>
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-2">
        <nav class="hidden items-center gap-1 md:flex">
          <RouterLink
            v-for="item in navItems"
            :key="item.name"
            :to="{ name: item.name }"
            class="rounded-lg px-3 py-2 text-sm font-medium transition-colors"
            :class="
              route.name === item.name
                ? 'bg-brand-primary text-white'
                : 'text-slate-700 hover:bg-slate-100'
            "
          >
            {{ t(`app.${item.label}`) }}
          </RouterLink>
        </nav>

        <div class="relative">
          <UiButton variant="ghost" size="sm" @click="auth.profileMenuOpen = !auth.profileMenuOpen">
            <span class="material-symbols-outlined text-[18px]">account_circle</span>
            <span class="hidden sm:inline">{{ auth.displayName }}</span>
          </UiButton>
          <div
            v-if="auth.profileMenuOpen"
            class="absolute right-0 mt-2 w-56 rounded-lg border border-slate-200 bg-white p-2 shadow-lg"
          >
            <button class="block w-full rounded px-3 py-2 text-left text-sm hover:bg-slate-100" type="button" @click="openProfile">
              {{ t('app.profile_menu_edit') }}
            </button>
            <button class="block w-full rounded px-3 py-2 text-left text-sm hover:bg-slate-100" type="button" @click="openSettings">
              {{ t('app.settings') }}
            </button>
            <button
              v-if="auth.authEnabled"
              class="block w-full rounded px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50"
              type="button"
              @click="signOut"
            >
              {{ t('app.profile_menu_logout') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <nav class="flex justify-end gap-1 overflow-x-auto border-t border-slate-100 px-4 py-2 md:hidden">
      <RouterLink
        v-for="item in navItems"
        :key="`mobile-${item.name}`"
        :to="{ name: item.name }"
        class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium"
        :class="route.name === item.name ? 'bg-brand-primary text-white' : 'bg-slate-100 text-slate-700'"
      >
        {{ t(`app.${item.label}`) }}
      </RouterLink>
    </nav>
  </header>
</template>

<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import DbStatusPopover from '@/components/db/DbStatusPopover.vue'
import { LOGO_ALT, LOGO_URL } from '@/brand'
import UiButton from '@/components/ui/UiButton.vue'
import StatusBar from '@/components/layout/StatusBar.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const app = useAppStore()
const router = useRouter()
const route = useRoute()

const navItems = [
  { name: 'assistant', label: 'nav_assistant' },
  { name: 'sessions', label: 'nav_sessions' },
  { name: 'hypothesis', label: 'nav_hypothesis' },
  { name: 'review', label: 'nav_review' },
] as const

function openProfile() {
  auth.profileMenuOpen = false
  app.profileOpen = true
}

function openSettings() {
  auth.profileMenuOpen = false
  app.settingsOpen = true
}

async function signOut() {
  auth.profileMenuOpen = false
  await auth.signOut()
  await router.push('/login')
}
</script>
