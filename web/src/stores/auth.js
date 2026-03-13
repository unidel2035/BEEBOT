import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin } from '../api.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || null)

  const isAuthenticated = computed(() => !!token.value)

  async function login(username, password) {
    const data = await apiLogin(username, password)
    token.value = data.access_token
    localStorage.setItem('token', data.access_token)
  }

  function logout() {
    token.value = null
    localStorage.removeItem('token')
  }

  return { token, isAuthenticated, login, logout }
})
