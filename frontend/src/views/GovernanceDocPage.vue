<template>
  <article class="mx-auto max-w-3xl px-4 py-12">
    <RouterLink to="/" class="text-sm text-brand-primary hover:underline">{{ t('legal.back_home') }}</RouterLink>
    <nav class="mt-4 flex flex-wrap gap-3 text-sm">
      <RouterLink to="/docs/MISSION.md">{{ t('legal.mission') }}</RouterLink>
      <RouterLink to="/docs/ETHICS_AND_OVERSIGHT.md">{{ t('legal.ethics') }}</RouterLink>
      <RouterLink to="/docs/HUMAN_OVERSIGHT.md">{{ t('legal.human_oversight') }}</RouterLink>
    </nav>
    <h1 class="mt-6 text-3xl font-semibold text-slate-900">{{ title }}</h1>
    <div v-if="loading" class="mt-6"><UiSpinner /></div>
    <div v-else class="prose prose-sm mt-6 max-w-none text-slate-700" v-html="bodyHtml" />
  </article>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { apiJson } from '@/api/client'
import UiSpinner from '@/components/ui/UiSpinner.vue'

const { t } = useI18n()
const route = useRoute()
const loading = ref(true)
const title = ref('')
const bodyHtml = ref('')

async function load() {
  loading.value = true
  const docName = String(route.params.docName || '')
  const data = await apiJson<{ title: string; body_html: string }>(`/api/governance/${encodeURIComponent(docName)}`)
  title.value = data.title
  bodyHtml.value = data.body_html
  loading.value = false
}

onMounted(() => {
  void load()
})

watch(() => route.params.docName, () => {
  void load()
})
</script>
