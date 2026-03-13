<template>
  <div class="flex h-screen bg-gray-50">
    <!-- Боковое меню -->
    <aside class="w-64 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col shadow-sm">
      <!-- Логотип -->
      <div class="px-6 py-5 border-b border-gray-100">
        <div class="flex items-center gap-3">
          <span class="text-3xl">🐝</span>
          <div>
            <h1 class="text-base font-bold text-gray-800 leading-tight">Усадьба Дмитровых</h1>
            <p class="text-xs text-gray-400">Панель управления</p>
          </div>
        </div>
      </div>

      <!-- Навигация -->
      <nav class="flex-1 px-3 py-4 space-y-1">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors"
          :class="isActive(item.to)
            ? 'bg-amber-50 text-amber-700'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-800'"
        >
          <i :class="['pi', item.icon, 'text-base']" />
          <span>{{ item.label }}</span>
          <span
            v-if="item.badge"
            class="ml-auto bg-amber-100 text-amber-700 text-xs font-semibold px-2 py-0.5 rounded-full"
          >{{ item.badge }}</span>
        </RouterLink>
      </nav>

      <!-- Выход -->
      <div class="px-3 py-4 border-t border-gray-100">
        <button
          @click="handleLogout"
          class="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-gray-500 hover:bg-gray-50 hover:text-gray-700 transition-colors"
        >
          <i class="pi pi-sign-out text-base" />
          <span>Выйти</span>
        </button>
      </div>
    </aside>

    <!-- Основной контент -->
    <main class="flex-1 overflow-auto">
      <div class="p-6">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<script setup>
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const navItems = [
  { to: '/dashboard', icon: 'pi-chart-bar', label: 'Дашборд' },
  { to: '/orders', icon: 'pi-shopping-cart', label: 'Заказы' },
  { to: '/clients', icon: 'pi-users', label: 'Клиенты' },
  { to: '/products', icon: 'pi-box', label: 'Товары' },
  { to: '/orders/new', icon: 'pi-plus-circle', label: 'Новый заказ' }
]

function isActive(path) {
  if (path === '/dashboard') return route.path === '/dashboard'
  return route.path.startsWith(path)
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>
