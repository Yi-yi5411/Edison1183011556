/** Web 登录态：后端 HttpOnly Cookie 为唯一凭证，这里只缓存用户信息。 */

export interface AuthUser {
  id: number
  username: string
  real_name: string
  department: string
  role: string
}

interface Envelope<T> {
  ok: boolean
  data: T
  message?: string
}

let cached: AuthUser | null | undefined

async function readEnvelope<T>(response: Response): Promise<Envelope<T>> {
  try {
    return (await response.json()) as Envelope<T>
  } catch {
    return { ok: false, data: null as unknown as T, message: '服务无响应' }
  }
}

export async function ensureAuth(): Promise<AuthUser | null> {
  if (cached !== undefined) return cached
  try {
    const response = await fetch('/api/auth/me', { credentials: 'same-origin' })
    if (!response.ok) {
      cached = null
      return null
    }
    const body = await readEnvelope<AuthUser>(response)
    cached = body.ok ? body.data : null
    return cached
  } catch {
    cached = null
    return null
  }
}

export async function login(loginId: string, password: string): Promise<AuthUser> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ login_id: loginId, password }),
  })
  const body = await readEnvelope<AuthUser>(response)
  if (!response.ok || !body.ok) throw new Error(body.message || '登录失败')
  cached = body.data
  return body.data
}

/** 清除本地登录态缓存（后端会话过期/401 时调用，下次路由跳转会重新校验）。 */
export function resetAuth(): void {
  cached = null
}

export async function logout(): Promise<void> {
  cached = null
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
  } catch {
    /* 本地退出失败也清空前端态 */
  }
}

export function currentUser(): AuthUser | null {
  return cached ?? null
}
