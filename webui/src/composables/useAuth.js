import { ref, computed } from 'vue'
import { api } from '../api/client'

const STORAGE_KEY = 'diting_jwt'

const token = ref(localStorage.getItem(STORAGE_KEY) || '')
const user = ref(null)
const loading = ref(false)

const isLoggedIn = computed(() => !!token.value)

function saveToken(t) {
  token.value = t
  localStorage.setItem(STORAGE_KEY, t)
}

function clearToken() {
  token.value = ''
  user.value = null
  localStorage.removeItem(STORAGE_KEY)
}

async function login(qqNumber, tempPassword) {
  loading.value = true
  try {
    const res = await api('POST', '/auth/login', {
      qq_number: qqNumber,
      temp_password: tempPassword,
    })
    saveToken(res.data.token)
    user.value = { qq_number: qqNumber }
    return res
  } finally {
    loading.value = false
  }
}

async function logout() {
  try {
    await api('POST', '/auth/logout', {})
  } catch {
    // Ignore logout API errors — clear token locally regardless
  }
  clearToken()
}

// Restore user from token payload (base64 decode the JWT payload)
function initFromToken() {
  const t = token.value
  if (!t) return
  try {
    const payload = JSON.parse(atob(t.split('.')[1]))
    if (payload.sub) {
      user.value = { qq_number: payload.sub }
    }
  } catch {
    // Invalid token format — clear it on next API call
  }
}
initFromToken()

export function useAuth() {
  return { token, user, loading, isLoggedIn, login, logout, clearToken }
}
