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
          <DbStatusPopover />
        </div>
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-2">
        <nav class="hidden items-center gap-1 md:flex">
          <RouterLink
            v-for="item in navItems"
            :key="item.name"
            :to="{ name: item.name }"
            :data-tutorial="item.tutorial"
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

        <UiPopover ref="profileMenuRef" align="right" panel-class="w-56 p-2">
          <template #trigger="{ toggle }">
            <UiButton variant="ghost" size="sm" @click="toggle">
              <span class="material-symbols-outlined text-[18px]">account_circle</span>
              <span class="hidden sm:inline">{{ auth.displayName }}</span>
            </UiButton>
          </template>

          <button class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-slate-100" type="button" @click="openProfile">
            <span class="material-symbols-outlined text-[18px] text-slate-500">manage_accounts</span>
            {{ t('app.profile_menu_edit') }}
          </button>
          <button class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-slate-100" type="button" @click="openSettings">
            <span class="material-symbols-outlined text-[18px] text-slate-500">settings</span>
            {{ t('app.settings') }}
          </button>
          <button
            v-if="auth.authEnabled"
            class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50"
            type="button"
            @click="signOut"
          >
            <span class="material-symbols-outlined text-[18px]">logout</span>
            {{ t('app.profile_menu_logout') }}
          </button>
        </UiPopover>
      </div>
    </div>

    <nav class="flex justify-end gap-1 overflow-x-auto border-t border-slate-100 px-4 py-2 md:hidden">
      <RouterLink
        v-for="item in navItems"
        :key="`mobile-${item.name}`"
        :to="{ name: item.name }"
        :data-tutorial="item.tutorial"
        class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium"
        :class="route.name === item.name ? 'bg-brand-primary text-white' : 'bg-slate-100 text-slate-700'"
      >
        {{ t(`app.${item.label}`) }}
      </RouterLink>
    </nav>
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import DbStatusPopover from '@/components/db/DbStatusPopover.vue'
import { LOGO_ALT, LOGO_URL } from '@/brand'
import UiButton from '@/components/ui/UiButton.vue'
import UiPopover from '@/components/ui/UiPopover.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const app = useAppStore()
const router = useRouter()
const route = useRoute()
const profileMenuRef = ref<InstanceType<typeof UiPopover> | null>(null)

const navItems = [
  { name: 'assistant', label: 'nav_assistant', tutorial: 'assistant_nav' },
  { name: 'sessions', label: 'nav_sessions', tutorial: 'sessions_nav' },
  { name: 'hypothesis', label: 'nav_hypothesis', tutorial: 'hypothesis_nav' },
  { name: 'review', label: 'nav_review', tutorial: 'review_nav' },
] as const

function closeProfileMenu() {
  profileMenuRef.value?.close()
}

function openProfile() {
  closeProfileMenu()
  app.profileOpen = true
}

function openSettings() {
  closeProfileMenu()
  app.settingsOpen = true
}

async function signOut() {
  closeProfileMenu()
  await auth.signOut()
  await router.push('/login')
}
</script>
