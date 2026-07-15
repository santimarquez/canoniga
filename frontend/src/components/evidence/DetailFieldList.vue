<template>
  <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs" :class="columnsClass">
    <div v-for="field in fields" :key="field.label">
      <dt class="text-slate-500">
        <UiFieldHelp v-if="field.helpKey" :text="t(`app.${field.helpKey}`)">{{ field.label }}</UiFieldHelp>
        <span v-else>{{ field.label }}</span>
      </dt>
      <dd class="font-medium text-slate-900">
        <a
          v-if="field.href"
          :href="field.href"
          class="text-brand-primary hover:underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ field.value }}
        </a>
        <span v-else>{{ field.value }}</span>
      </dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import UiFieldHelp from '@/components/ui/UiFieldHelp.vue'

export type DetailField = {
  label: string
  value: string
  href?: string
  helpKey?: string
}

const props = withDefaults(
  defineProps<{
    fields: DetailField[]
    columns?: 'two' | 'three'
  }>(),
  {
    columns: 'three',
  },
)

const { t } = useI18n()

const columnsClass = computed(() => (props.columns === 'two' ? 'sm:grid-cols-2' : 'sm:grid-cols-3'))
</script>
