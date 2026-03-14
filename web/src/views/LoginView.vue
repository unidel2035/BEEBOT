<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-amber-50 to-orange-100">
    <div class="bg-white rounded-2xl shadow-lg p-8 w-full max-w-sm">
      <!-- Логотип -->
      <div class="text-center mb-8">
        <div class="text-6xl mb-3">🐝</div>
        <h1 class="text-xl font-bold text-gray-800">Усадьба Дмитровых</h1>
        <p class="text-sm text-gray-500 mt-1">Панель управления заказами</p>
      </div>

      <!-- Форма входа -->
      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Логин</label>
          <InputText
            v-model="username"
            placeholder="admin"
            class="w-full"
            :class="{ 'p-invalid': error }"
            autocomplete="username"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Пароль</label>
          <InputText
            v-model="password"
            type="password"
            placeholder="••••••••"
            class="w-full"
            :class="{ 'p-invalid': error }"
            autocomplete="current-password"
          />
        </div>

        <Message v-if="error" severity="error" class="text-sm">{{ error }}</Message>

        <Button
          type="submit"
          label="Войти"
          icon="pi pi-sign-in"
          class="w-full"
          :loading="loading"
        />
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import Message from 'primevue/message'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    const redirect = route.query.redirect || '/dashboard'
    router.push(redirect)
  } catch (e) {
    error.value = 'Неверный логин или пароль'
  } finally {
    loading.value = false
  }
}
</script>
