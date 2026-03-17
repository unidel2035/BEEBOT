import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, getMe } from '../api.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || null)
  const role = ref(localStorage.getItem('role') || null)
  const displayName = ref(localStorage.getItem('displayName') || null)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => role.value === 'admin')
  const isWarehouse = computed(() => role.value === 'warehouse')

  async function login(username, password) {
    const data = await apiLogin(username, password)
    token.value = data.access_token
    localStorage.setItem('token', data.access_token)

    // Получить роль с сервера
    try {
      const me = await getMe()
      role.value = me.role
      displayName.value = me.display_name || me.username
      localStorage.setItem('role', me.role)
      localStorage.setItem('displayName', me.display_name || me.username)
    } catch {
      // Фоллбэк: если /auth/me недоступен, считать admin
      role.value = 'admin'
      displayName.value = username
      localStorage.setItem('role', 'admin')
      localStorage.setItem('displayName', username)
    }
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const me = await getMe()
      role.value = me.role
      displayName.value = me.display_name || me.username
      localStorage.setItem('role', me.role)
      localStorage.setItem('displayName', me.display_name || me.username)
    } catch {
      // Токен невалиден — разлогинить
      logout()
    }
  }

  function logout() {
    token.value = null
    role.value = null
    displayName.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    localStorage.removeItem('displayName')
  }

  return { token, role, displayName, isAuthenticated, isAdmin, isWarehouse, login, logout, fetchMe }
})
