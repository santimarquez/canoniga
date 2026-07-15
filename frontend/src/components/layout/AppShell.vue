<template>
  <div class="min-h-screen bg-surface text-on-surface">
    <TopBar />
    <main class="mx-auto max-w-[1600px] px-4 pb-6 pt-4">
      <div class="grid gap-4" :class="gridClass">
        <FilterPanel v-if="showAssistantPanels" class="hidden lg:block" />
        <section class="min-w-0">
          <RouterView />
        </section>
        <EvidenceSidebar v-if="showAssistantPanels" class="hidden xl:block" />
      </div>
    </main>
    <SettingsDrawer />
    <ProfileDrawer />
    <ClaimDrawer />
    <DbExplorerModal />
    <TutorialOverlay />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import ClaimDrawer from '@/components/evidence/ClaimDrawer.vue'
import EvidenceSidebar from '@/components/evidence/EvidenceSidebar.vue'
import FilterPanel from '@/components/evidence/FilterPanel.vue'
import DbExplorerModal from '@/components/db/DbExplorerModal.vue'
import ProfileDrawer from '@/components/auth/ProfileDrawer.vue'
import SettingsDrawer from '@/components/auth/SettingsDrawer.vue'
import TopBar from '@/components/layout/TopBar.vue'
import TutorialOverlay from '@/components/tutorial/TutorialOverlay.vue'
import { useAuthRefresh } from '@/composables/useAuthRefresh'
import { useManualSync } from '@/composables/useManualSync'
import { useAppStore } from '@/stores/app'
import { useStatusStore } from '@/stores/status'
import type { AppView } from '@/types/api'

const route = useRoute()
const router = useRouter()
const app = useAppStore()
const status = useStatusStore()

useAuthRefresh()
useManualSync()

const showAssistantPanels = computed(() => route.name === 'assistant')

const gridClass = computed(() =>
  showAssistantPanels.value
    ? 'lg:grid-cols-[280px_minmax(0,1fr)_320px]'
    : 'grid-cols-1',
)

onMounted(async () => {
  await status.refresh()
})

watch(
  () => route.name,
  (name) => {
    if (!name) return
    const map: Record<string, AppView> = {
      assistant: 'assistant',
      sessions: 'sessions',
      hypothesis: 'hypothesis',
      review: 'review',
    }
    if (name in map) app.switchView(map[name as string])
  },
  { immediate: true },
)

watch(
  () => app.activeView,
  (view) => {
    const target = view
    if (route.name !== target) {
      void router.push({ name: target })
    }
  },
)
</script>
