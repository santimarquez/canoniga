<template>
  <div class="min-h-screen bg-slate-50">
    <LoginForm />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LoginForm from '@/components/auth/LoginForm.vue'
import { verifyMagicLink } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

onMounted(async () => {
  await auth.refresh()
  const token = typeof route.query.magic_token === 'string' ? route.query.magic_token : ''
  if (token) {
    const data = await verifyMagicLink(token)
    auth.applyVerify(data.user, data.csrf_token)
    const next = typeof route.query.next === 'string' ? route.query.next : '/app'
    await router.replace(next)
  }
})
</script>
