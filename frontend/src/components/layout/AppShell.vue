<template>
  <div
    class="flex flex-col bg-surface text-on-surface"
    :class="layoutAssistant ? 'h-dvh overflow-hidden' : 'min-h-screen'"
  >
    <TopBar />
    <main
      class="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 flex-col px-4 pt-4"
      :class="[mainClass, layoutAssistant ? 'overflow-hidden' : 'overflow-y-auto']"
    >
      <div class="grid min-h-0 flex-1 gap-4 overflow-hidden" :class="gridClass">
        <section class="min-h-0 min-w-0" :class="sectionClass">
          <RouterView v-slot="{ Component, route: viewRoute }">
            <Transition name="page-fade" mode="out-in" @after-leave="onPageAfterLeave">
              <component :is="Component" :key="viewRoute.path" class="h-full min-h-0 w-full" />
            </Transition>
          </RouterView>
        </section>
        <EvidenceSidebar
          v-if="showEvidenceSidebar"
          class="hidden min-h-0 overflow-y-auto lg:block"
        />
      </div>
    </main>
    <SettingsDrawer />
    <ProfileDrawer />
    <ClaimDrawer />
    <DbExplorerModal />
    <CompareModal />
    <TutorialOverlay />
    <ToastHost />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import ClaimDrawer from '@/components/evidence/ClaimDrawer.vue'
import CompareModal from '@/components/evidence/CompareModal.vue'
import EvidenceSidebar from '@/components/evidence/EvidenceSidebar.vue'
import DbExplorerModal from '@/components/db/DbExplorerModal.vue'
import ProfileDrawer from '@/components/auth/ProfileDrawer.vue'
import SettingsDrawer from '@/components/auth/SettingsDrawer.vue'
import TopBar from '@/components/layout/TopBar.vue'
import ToastHost from '@/components/ui/ToastHost.vue'
import TutorialOverlay from '@/components/tutorial/TutorialOverlay.vue'
import { useAuthRefresh } from '@/composables/useAuthRefresh'
import { useManualSync } from '@/composables/useManualSync'
import { tutorialSignal, useTutorial } from '@/composables/useTutorial'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useStatusStore } from '@/stores/status'
import type { AppView } from '@/types/api'

const route = useRoute()
const router = useRouter()
const app = useAppStore()
const auth = useAuthStore()
const status = useStatusStore()
const tutorial = useTutorial()

useAuthRefresh()
useManualSync()

/**
 * Keep assistant shell chrome until the outgoing page leave finishes.
 * Drop the evidence column as soon as the route leaves assistant so it cannot
 * reflow to full width under grid-cols-1 during the fade.
 */
const layoutAssistant = ref(route.name === 'assistant')
const onAssistantRoute = computed(() => route.name === 'assistant')
const showEvidenceSidebar = computed(
  () => onAssistantRoute.value && layoutAssistant.value && !app.evidenceCollapsed,
)

const mainClass = computed(() => (layoutAssistant.value ? 'pb-0' : 'pb-6'))

const gridClass = computed(() => {
  if (!layoutAssistant.value) return 'grid-cols-1'
  if (!onAssistantRoute.value || app.evidenceCollapsed) {
    return 'grid-cols-1 grid-rows-[minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)]'
  }
  return 'grid-cols-1 grid-rows-[minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_320px]'
})

const sectionClass = computed(() =>
  layoutAssistant.value
    ? 'flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white'
    : '',
)

function onPageAfterLeave() {
  layoutAssistant.value = route.name === 'assistant'
}

onMounted(async () => {
  await status.refresh()
  await auth.refresh()
  if (auth.isAuthenticated && tutorial.shouldAutoStartTutorial()) {
    tutorial.start('short', false)
  }
})

watch(
  () => route.name,
  (name) => {
    if (!name) return
    // Entering assistant: expand shell immediately so the sidebar is ready.
    if (name === 'assistant') {
      layoutAssistant.value = true
    }
    const map: Record<string, AppView> = {
      assistant: 'assistant',
      sessions: 'sessions',
      hypothesis: 'hypothesis',
      review: 'review',
    }
    if (name in map) app.switchView(map[name as string])
    if (name === 'sessions') tutorialSignal('sessions_view_opened')
    if (name === 'hypothesis') tutorialSignal('hypothesis_queue_opened')
    if (name === 'review') tutorialSignal('review_queue_opened')
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

watch(
  () => app.dbExplorerOpen,
  (open) => {
    if (open) tutorialSignal('db_explorer_opened')
  },
)
</script>
