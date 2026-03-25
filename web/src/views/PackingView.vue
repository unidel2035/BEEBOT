<template>
  <div class="packing-terminal">
    <!-- Оффлайн-баннер -->
    <div v-if="offline" class="bg-amber-100 text-amber-800 px-4 py-2 rounded-lg mb-4 flex items-center gap-2 text-sm">
      <i class="pi pi-wifi-off" />
      <span>Нет связи — работаем с кэшем</span>
      <span v-if="queueCount > 0" class="ml-auto font-semibold">{{ queueCount }} в очереди</span>
    </div>

    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xl font-bold text-gray-800">
        <i class="pi pi-box mr-2" />Сборка заказов
      </h2>
      <div class="flex gap-2">
        <Button
          :icon="autoRefresh ? 'pi pi-pause' : 'pi pi-play'"
          :label="autoRefresh ? 'Пауза' : 'Авто'"
          :severity="autoRefresh ? 'warn' : 'secondary'"
          size="small"
          @click="toggleAutoRefresh"
        />
        <Button icon="pi pi-refresh" label="Обновить" size="small" @click="loadOrders" :loading="loading" />
      </div>
    </div>

    <!-- Карточки заказов на сборку -->
    <div v-if="loading && !orders.length" class="space-y-4">
      <Skeleton v-for="i in 3" :key="i" height="180px" class="rounded-xl" />
    </div>

    <div v-else-if="orders.length === 0" class="text-center py-16 text-gray-400">
      <i class="pi pi-check-circle text-5xl mb-4 block text-green-300" />
      <p class="text-lg">Все заказы собраны!</p>
    </div>

    <div v-else class="space-y-4">
      <div
        v-for="order in orders"
        :key="order.id"
        class="bg-white rounded-xl border shadow-sm overflow-hidden"
        :class="order._expanded ? 'border-amber-300' : 'border-gray-100'"
      >
        <!-- Заголовок заказа -->
        <div
          class="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-gray-50 transition-colors"
          @click="toggleOrder(order)"
        >
          <i :class="['pi', order._expanded ? 'pi-chevron-down' : 'pi-chevron-right', 'text-gray-400']" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-bold text-gray-800">{{ order.number || `#${order.id}` }}</span>
              <Tag :value="order.status" :severity="statusSeverity(order.status)" />
            </div>
            <div class="text-sm text-gray-500 truncate mt-0.5">
              {{ order.client_name || 'Клиент' }} — {{ order.delivery_method || 'Доставка' }}
            </div>
          </div>
          <div class="text-right flex-shrink-0">
            <div class="text-sm font-semibold">{{ order.items?.length || '?' }} поз.</div>
            <div class="text-xs text-gray-400">{{ order.delivery_address?.split(',')[0] || '' }}</div>
          </div>
        </div>

        <!-- Развёрнутая карточка -->
        <div v-if="order._expanded" class="border-t border-gray-100">
          <!-- Адрес и комментарий -->
          <div class="px-4 py-2 bg-gray-50 text-sm space-y-1">
            <div v-if="order.delivery_address">
              <i class="pi pi-map-marker text-gray-400 mr-1" />
              {{ order.delivery_address }}
            </div>
            <div v-if="order.comment" class="text-amber-700">
              <i class="pi pi-info-circle mr-1" />
              {{ order.comment }}
            </div>
          </div>

          <!-- Чек-лист позиций -->
          <div class="divide-y divide-gray-50">
            <div
              v-for="item in order.items"
              :key="item.id"
              class="px-4 py-3 flex items-center gap-3"
              :class="item._packed ? 'bg-green-50' : ''"
            >
              <Checkbox
                v-model="item._packed"
                binary
                @change="onItemCheck(order)"
              />
              <div class="flex-1">
                <div class="font-medium" :class="item._packed ? 'text-green-700 line-through' : 'text-gray-800'">
                  {{ item.product_name }}
                </div>
                <div class="text-xs text-gray-400">
                  {{ item.unit_price }} ₽ x {{ item.quantity }}
                </div>
              </div>
              <div class="text-lg font-bold" :class="item._packed ? 'text-green-600' : 'text-gray-700'">
                x{{ item.quantity }}
              </div>
            </div>
          </div>

          <!-- Итого и кнопки -->
          <div class="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
            <div class="text-sm text-gray-500">
              Собрано: <strong>{{ packedCount(order) }}</strong> / {{ order.items?.length || 0 }}
            </div>
            <div class="flex gap-2">
              <Button
                v-if="order.status === 'В сборке'"
                label="Собран"
                icon="pi pi-check"
                size="small"
                :disabled="!allPacked(order)"
                @click="markPacked(order)"
                :loading="order._saving"
              />
              <Button
                v-if="order.status === 'Подтверждён'"
                label="Взять в сборку"
                icon="pi pi-arrow-right"
                size="small"
                severity="warn"
                @click="takeToAssembly(order)"
                :loading="order._saving"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Checkbox from 'primevue/checkbox'
import Skeleton from 'primevue/skeleton'
import { getOrders, getOrderItems, updateOrderStatus } from '../api.js'
import { fetchWithCache, enqueue, getQueue, syncQueue } from '../stores/offline.js'

const toast = useToast()
const loading = ref(false)
const offline = ref(false)
const orders = ref([])
const queueCount = ref(0)
const autoRefresh = ref(true)
let refreshTimer = null

onMounted(async () => {
  await loadOrders()
  startAutoRefresh()
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
})

onUnmounted(() => {
  stopAutoRefresh()
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
})

function onOnline() {
  offline.value = false
  trySyncQueue()
  loadOrders()
}

function onOffline() {
  offline.value = true
}

function startAutoRefresh() {
  stopAutoRefresh()
  if (autoRefresh.value) {
    refreshTimer = setInterval(loadOrders, 60000) // каждую минуту
  }
}

function stopAutoRefresh() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) startAutoRefresh()
  else stopAutoRefresh()
}

async function loadOrders() {
  loading.value = true
  try {
    // Загружаем заказы со статусами "Подтверждён" и "В сборке"
    const { data: confirmedRaw, offline: off1 } = await fetchWithCache(
      'packing-confirmed',
      () => getOrders({ status: 'Подтверждён', per_page: 200 })
    )
    const { data: assemblingRaw, offline: off2 } = await fetchWithCache(
      'packing-assembling',
      () => getOrders({ status: 'В сборке', per_page: 200 })
    )
    offline.value = off1 || off2

    const confirmed = confirmedRaw?.items ?? confirmedRaw
    const assembling = assemblingRaw?.items ?? assemblingRaw
    const allOrders = [...(assembling || []), ...(confirmed || [])]

    // Загрузить позиции для каждого заказа
    for (const order of allOrders) {
      try {
        const { data: items } = await fetchWithCache(
          `order-items-${order.id}`,
          () => getOrderItems(order.id)
        )
        order.items = (items || []).map(i => ({ ...i, _packed: false }))
      } catch {
        order.items = []
      }
      order._expanded = false
      order._saving = false
    }

    orders.value = allOrders
    await updateQueueCount()
  } finally {
    loading.value = false
  }
}

function toggleOrder(order) {
  order._expanded = !order._expanded
}

function packedCount(order) {
  return (order.items || []).filter(i => i._packed).length
}

function allPacked(order) {
  return order.items?.length > 0 && order.items.every(i => i._packed)
}

function onItemCheck(order) {
  // Автоматически разворачиваем если ещё нет
}

async function takeToAssembly(order) {
  order._saving = true
  try {
    if (navigator.onLine) {
      await updateOrderStatus(order.id, 'В сборке')
    } else {
      await enqueue({ type: 'status', orderId: order.id, status: 'В сборке' })
    }
    order.status = 'В сборке'
    toast.add({ severity: 'info', summary: 'В сборке', detail: `Заказ ${order.number} взят в работу`, life: 2000 })
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось изменить статус', life: 3000 })
  } finally {
    order._saving = false
  }
}

async function markPacked(order) {
  order._saving = true
  try {
    if (navigator.onLine) {
      await updateOrderStatus(order.id, 'Отправлен')
    } else {
      await enqueue({ type: 'status', orderId: order.id, status: 'Отправлен' })
    }
    toast.add({ severity: 'success', summary: 'Собран!', detail: `Заказ ${order.number} отмечен как собранный`, life: 2000 })
    // Убрать из списка
    orders.value = orders.value.filter(o => o.id !== order.id)
    await updateQueueCount()
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось обновить статус', life: 3000 })
  } finally {
    order._saving = false
  }
}

async function updateQueueCount() {
  const q = await getQueue()
  queueCount.value = q.length
}

async function trySyncQueue() {
  await syncQueue(async (item) => {
    if (item.type === 'status') {
      await updateOrderStatus(item.orderId, item.status)
    }
  })
  await updateQueueCount()
}

function statusSeverity(s) {
  const map = {
    'Подтверждён': 'warn',
    'В сборке': 'info',
  }
  return map[s] || 'secondary'
}
</script>

<style scoped>
.packing-terminal {
  max-width: 640px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .packing-terminal {
    margin: -1rem;
    padding: 1rem;
  }
}
</style>
