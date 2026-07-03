import { useAuth } from '../composables/useAuth'
import { useToast } from '../composables/useToast'
import router from '../router'

const API_BASE = '/api/v1'

export async function api(method, path, body = null) {
  const { token, clearToken } = useAuth()
  const { showToast } = useToast()

  const headers = { 'Content-Type': 'application/json' }
  if (token.value) {
    headers['Authorization'] = `Bearer ${token.value}`
  }

  let res
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (err) {
    showToast('网络错误，请检查连接', 'error')
    throw err
  }

  if (res.status === 401) {
    clearToken()
    showToast('登录已过期，请重新登录', 'error')
    router.push('/login')
    throw new Error('登录已过期')
  }

  let json
  try {
    json = await res.json()
  } catch {
    throw new Error(`Invalid response (${res.status})`)
  }

  if (json.status === 'error') {
    throw new Error(json.message || '请求失败')
  }

  return json
}

export function apiGet(path) {
  return api('GET', path)
}

export function apiPost(path, body) {
  return api('POST', path, body)
}

export function apiDelete(path) {
  return api('DELETE', path)
}
