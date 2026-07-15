<template>
  <div class="rounded-lg border border-slate-200 p-3">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="truncate text-sm font-medium text-slate-900">{{ source.display_name || source.source }}</p>
        <p class="text-xs text-slate-500">{{ updatedLabel }}</p>
      </div>
      <UiButton size="sm" variant="secondary" :disabled="!source.can_trigger" :loading="loading" @click="$emit('trigger', source.source)">
        {{ buttonLabel }}
      </UiButton>
    </div>
    <p v-if="source.sync_status === 'failed'" class="mt-2 text-xs text-red-700">{{ failedLabel }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import UiButton from '@/components/ui/UiButton.vue'
import { formatRelativeTime } from '@/i18n/time'
import type { ManualSyncSource } from '@/types/api'

const props = defineProps<{ source: ManualSyncSource }>()
defineEmits<{ trigger: [source: string] }>()

const { t } = useI18n()
const loading = ref(false)

const onCooldown = computed(() => props.source.cooldown_remaining_seconds > 0)

const updatedLabel = computed(() => {
  const stamp = props.source.last_successful_at || props.source.last_attempt_at
  if (!stamp) return t('app.sync_never')
  return t('app.sync_last_success', { time: formatRelativeTime(stamp) })
})

const buttonLabel = computed(() => {
  if (onCooldown.value) {
    return t('app.sync_cooldown')
  }
  return t('app.sync_update_source')
})

const failedLabel = computed(() => {
  const failedTime = formatRelativeTime(props.source.last_attempt_at)
  const okTime = formatRelativeTime(props.source.last_successful_at)
  if (props.source.last_successful_at) {
    return t('app.sync_last_failed_with_ok', { failed_time: failedTime, ok_time: okTime })
  }
  return t('app.sync_last_failed', { time: failedTime })
})
</script>
