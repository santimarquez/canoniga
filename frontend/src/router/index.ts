import { createRouter, createWebHistory } from 'vue-router'
import { setAppLocale } from '@/i18n'
import { normalizeLocale } from '@/i18n/locale'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'landing', component: () => import('@/views/LandingPage.vue') },
    { path: '/login', name: 'login', component: () => import('@/views/LoginPage.vue'), meta: { public: true } },
    { path: '/privacy', name: 'privacy', component: () => import('@/views/LegalPage.vue'), props: { doc: 'privacy' }, meta: { public: true } },
    { path: '/terms', name: 'terms', component: () => import('@/views/LegalPage.vue'), props: { doc: 'terms' }, meta: { public: true } },
    { path: '/docs/:docName', name: 'governance', component: () => import('@/views/GovernanceDocPage.vue'), meta: { public: true } },
    {
      path: '/app',
      component: () => import('@/components/layout/AppShell.vue'),
      children: [
        { path: '', redirect: { name: 'assistant' } },
        { path: 'assistant', name: 'assistant', component: () => import('@/views/AssistantView.vue') },
        { path: 'sessions', name: 'sessions', component: () => import('@/views/SessionsView.vue') },
        { path: 'hypothesis', name: 'hypothesis', component: () => import('@/views/HypothesisView.vue') },
        { path: 'review', name: 'review', component: () => import('@/views/ReviewView.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    if (to.hash) {
      return new Promise((resolve) => {
        requestAnimationFrame(() => {
          resolve({
            el: to.hash,
            behavior: 'smooth',
          })
        })
      })
    }
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const fromQuery = normalizeLocale(typeof to.query.lang === 'string' ? to.query.lang : null)
  if (fromQuery) {
    setAppLocale(fromQuery)
    useAppStore().language = fromQuery
  }

  const auth = useAuthStore()
  if (!auth.loading && !auth.currentUser && !to.meta.public) {
    await auth.refresh()
  }
  if (to.path.startsWith('/app') && auth.authEnabled && !auth.isAuthenticated) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    const next = typeof to.query.next === 'string' ? to.query.next : '/app'
    return next
  }
  return true
})

export default router
