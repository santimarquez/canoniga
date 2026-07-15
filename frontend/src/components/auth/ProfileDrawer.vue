<template>
  <UiDrawer :open="app.profileOpen" :title="t('app.profile_drawer_title')" @close="app.profileOpen = false">
    <form class="space-y-4" @submit.prevent="save">
      <div class="flex items-center gap-3">
        <img v-if="auth.avatarUrl" :src="auth.avatarUrl" alt="" class="h-14 w-14 rounded-full object-cover" />
        <div v-else class="flex h-14 w-14 items-center justify-center rounded-full bg-brand-primary/10 text-brand-primary">
          {{ auth.userProfile?.initials || 'U' }}
        </div>
        <div>
          <p class="font-medium text-slate-900">{{ auth.displayName }}</p>
          <p class="text-sm text-slate-500">{{ auth.currentUser?.email }}</p>
        </div>
      </div>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.profile_display_name') }}</span>
        <input v-model="form.display_name" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.profile_title') }}</span>
        <input v-model="form.title" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">{{ t('app.profile_institution') }}</span>
        <input v-model="form.institution" class="w-full rounded-lg border border-slate-300 px-3 py-2" />
      </label>
      <UiNotice v-if="error" type="error" :message="error" />
      <UiButton class="w-full" type="submit" :loading="saving">{{ t('app.profile_save') }}</UiButton>
    </form>
  </UiDrawer>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { updateProfile } from '@/api/auth'
import UiButton from '@/components/ui/UiButton.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiNotice from '@/components/ui/UiNotice.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const app = useAppStore()
const auth = useAuthStore()
const saving = ref(false)
const error = ref('')

const form = reactive({
  display_name: '',
  title: '',
  institution: '',
})

watch(
  () => app.profileOpen,
  (open) => {
    if (!open) return
    form.display_name = auth.userProfile?.display_name ?? ''
    form.title = auth.userProfile?.title ?? ''
    form.institution = auth.userProfile?.institution ?? ''
    error.value = ''
  },
  { immediate: true },
)

async function save() {
  saving.value = true
  error.value = ''
  try {
    const data = await updateProfile(form)
    auth.setProfile(data.profile)
    app.profileOpen = false
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>
