import { useAuthStore } from '@/stores/auth'

export class ApiRequestError extends Error {
  status: number
  payload: unknown

  constructor(message: string, status: number, payload: unknown) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.payload = payload
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const auth = useAuthStore()
  if (auth.authEnabled && auth.csrfToken && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', auth.csrfToken)
  }
  return fetch(path, {
    ...init,
    headers,
    credentials: 'same-origin',
  })
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message =
      typeof payload === 'object' && payload && 'error' in payload
        ? String((payload as { error: string }).error)
        : `Request failed (${response.status})`
    throw new ApiRequestError(message, response.status, payload)
  }
  return payload as T
}

export async function* readNdjsonStream<T extends { type: string }>(
  response: Response,
  onEvent?: (event: T) => 'stop' | void,
): AsyncGenerator<T> {
  if (!response.body) throw new Error('Missing response body')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue
        try {
          const parsed = JSON.parse(trimmed) as T
          if (onEvent?.(parsed) === 'stop') {
            await reader.cancel()
            return
          }
          yield parsed
        } catch {
          // ignore malformed lines
        }
      }
    }
    const trailing = buffer.trim()
    if (trailing) {
      const parsed = JSON.parse(trailing) as T
      if (onEvent?.(parsed) !== 'stop') yield parsed
    }
  } finally {
    reader.releaseLock()
  }
}
