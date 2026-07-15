import { apiJson } from './client'
import type {
  AuthStatusResponse,
  LoginMetadataResponse,
  StatusResponse,
  UserProfile,
} from '@/types/api'

export function fetchAuthStatus() {
  return apiJson<AuthStatusResponse>('/api/auth/status')
}

export function fetchLoginMetadata() {
  return apiJson<LoginMetadataResponse>('/api/auth/login-metadata')
}

export function requestMagicLink(email: string, language: string) {
  return apiJson<{ ok: true; email: string; delivery_mode: string; magic_link: string | null }>(
    '/api/auth/request-link',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, language }),
    },
  )
}

export function verifyMagicLink(token: string) {
  return apiJson<{ ok: true; authenticated: true; user: { user_id: string; email: string }; csrf_token: string }>(
    '/api/auth/verify-link',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    },
  )
}

export function logout() {
  return apiJson<{ ok: true }>('/api/auth/logout', { method: 'POST' })
}

export function updateProfile(payload: Partial<UserProfile> & { avatar_base64?: string; avatar_mime_type?: string; clear_avatar?: boolean }) {
  return apiJson<{ ok: true; profile: UserProfile }>('/api/auth/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchStatus() {
  return apiJson<StatusResponse>('/api/status')
}

export function profileAvatarUrl(cacheBust?: string | number) {
  const suffix = cacheBust ? `?v=${encodeURIComponent(String(cacheBust))}` : ''
  return `/api/auth/profile/avatar${suffix}`
}
