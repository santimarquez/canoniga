import { defineStore } from 'pinia'
import { fetchAuthStatus, logout as apiLogout } from '@/api/auth'
import type { AuthUser, UserProfile } from '@/types/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    authEnabled: true,
    isAuthenticated: false,
    currentUser: null as AuthUser | null,
    userProfile: null as UserProfile | null,
    csrfToken: '',
    profileAvatarVersion: 0,
    profileMenuOpen: false,
    loading: false,
  }),
  getters: {
    displayName(state) {
      return state.userProfile?.display_name || state.currentUser?.email || ''
    },
    avatarUrl(state) {
      if (!state.userProfile?.has_avatar) return ''
      return `/api/auth/profile/avatar?v=${state.profileAvatarVersion}`
    },
  },
  actions: {
    async refresh() {
      this.loading = true
      try {
        const data = await fetchAuthStatus()
        this.authEnabled = data.auth_enabled
        if (!data.auth_enabled) {
          this.isAuthenticated = true
          this.currentUser = { user_id: 'anonymous', email: 'anonymous@local' }
          this.userProfile = {
            display_name: 'Local user',
            title: '',
            institution: '',
            has_avatar: false,
            initials: 'LU',
          }
          this.csrfToken = ''
          return data
        }
        this.isAuthenticated = data.authenticated
        this.currentUser = data.user
        this.userProfile = data.profile
        this.csrfToken = data.csrf_token ?? ''
        return data
      } finally {
        this.loading = false
      }
    },
    applyVerify(user: AuthUser, csrfToken: string) {
      this.isAuthenticated = true
      this.currentUser = user
      this.csrfToken = csrfToken
    },
    setProfile(profile: UserProfile) {
      this.userProfile = profile
      this.profileAvatarVersion += 1
    },
    async signOut() {
      if (this.authEnabled) {
        await apiLogout()
      }
      this.isAuthenticated = false
      this.currentUser = null
      this.userProfile = null
      this.csrfToken = ''
    },
  },
})
