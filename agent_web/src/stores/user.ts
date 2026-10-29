import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface UserInfo {
  id: string
  username: string
  role: string
  email?: string
  avatar?: string
  isActive?: boolean
  featurePermissions?: string[]
}

const TOKEN_KEY = 'agent_web_token'
const USER_KEY = 'agent_web_user'

function loadUser(): UserInfo | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) ?? '')
  const user = ref<UserInfo | null>(loadUser())

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function setAuth(t: string, u: UserInfo) {
    token.value = t
    user.value = u
    localStorage.setItem(TOKEN_KEY, t)
    localStorage.setItem(USER_KEY, JSON.stringify(u))
  }

  function updateUser(u: Partial<UserInfo>) {
    if (user.value) {
      user.value = { ...user.value, ...u }
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { token, user, isLoggedIn, isAdmin, setAuth, updateUser, logout }
})
