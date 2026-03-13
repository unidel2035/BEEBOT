<template>
  <div>
    <!-- Заголовок -->
    <div class="flex items-center gap-3 mb-6">
      <Button icon="pi pi-arrow-left" severity="secondary" text @click="$router.back()" />
      <h2 class="text-2xl font-bold text-gray-800">
        Заказ {{ order?.number || '#' + orderId }}
      </h2>
      <StatusBadge v-if="order" :status="order.status" class="ml-1" />
    </div>

    <div v-if="loading" class="space-y-4">
      <Skeleton height="200px" class="rounded-xl" />
      <Skeleton height="150px" class="rounded-xl" />
    </div>

    <div v-else-if="order" class="space-y-4">
      <!-- Основная информация -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Детали заказа -->
        <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <h3 class="font-semibold text-gray-700 mb-4">Детали заказа</h3>
          <dl class="space-y-3 text-sm">
            <div class="flex justify-between">
              <dt class="text-gray-500">Дата</dt>
              <dd class="font-medium">{{ formatDate(order.date) }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Клиент</dt>
              <dd class="font-medium">
                <RouterLink
                  :to="`/clients/${order.client_id}`"
                  class="text-amber-600 hover:text-amber-700"
                >
                  {{ order.client_name || `#${order.client_id}` }}
                </RouterLink>
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Источник</dt>
              <dd class="font-medium">{{ order.source || '—' }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Сумма товаров</dt>
              <dd class="font-medium">{{ formatMoney(order.items_total) }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Доставка</dt>
              <dd class="font-medium">{{ formatMoney(order.delivery_cost) }}</dd>
            </div>
            <div class="flex justify-between border-t pt-2 mt-2">
              <dt class="text-gray-700 font-semibold">Итого</dt>
              <dd class="font-bold text-lg">{{ formatMoney(order.total) }}</dd>
            </div>
          </dl>
        </div>

        <!-- Доставка -->
        <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <h3 class="font-semibold text-gray-700 mb-4">Доставка</h3>
          <dl class="space-y-3 text-sm">
            <div class="flex justify-between">
              <dt class="text-gray-500">Способ</dt>
              <dd class="font-medium">{{ order.delivery_method || '—' }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500">Адрес</dt>
              <dd class="font-medium text-right max-w-xs">{{ order.delivery_address || '—' }}</dd>
            </div>
            <div class="flex justify-between items-center">
              <dt class="text-gray-500">Трек-номер</dt>
              <dd>
                <span v-if="!editTracking" class="font-mono text-sm text-blue-600">
                  {{ order.tracking_number || '—' }}
                  <button @click="editTracking = true" class="ml-2 text-gray-400 hover:text-gray-600">
                    <i class="pi pi-pencil text-xs" />
                  </button>
                </span>
                <div v-else class="flex gap-2 items-center">
                  <InputText v-model="trackingInput" size="small" class="w-36 font-mono" />
                  <Button icon="pi pi-check" size="small" @click="saveTracking" :loading="savingTracking" />
                  <Button icon="pi pi-times" size="small" severity="secondary" @click="editTracking = false" />
                </div>
              </dd>
            </div>
          </dl>
        </div>
      </div>

      <!-- Смена статуса -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Статус заказа</h3>
        <div class="flex gap-2 flex-wrap">
          <Button
            v-for="s in statusOptions"
            :key="s"
            :label="s"
            :severity="order.status === s ? 'warning' : 'secondary'"
            size="small"
            :outlined="order.status !== s"
            :loading="changingStatus === s"
            @click="changeStatus(s)"
          />
        </div>
      </div>

      <!-- Позиции заказа -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Позиции заказа</h3>
        <DataTable :value="order.items" class="text-sm">
          <template #empty>
            <div class="text-center py-4 text-gray-400">Позиций нет</div>
          </template>
          <Column field="product_name" header="Товар">
            <template #body="{ data }">{{ data.product_name || `Товар #${data.product_id}` }}</template>
          </Column>
          <Column field="quantity" header="Кол-во" style="width:80px" />
          <Column field="unit_price" header="Цена за шт.">
            <template #body="{ data }">{{ formatMoney(data.unit_price) }}</template>
          </Column>
          <Column field="total" header="Сумма">
            <template #body="{ data }">{{ formatMoney(data.total) }}</template>
          </Column>
        </DataTable>
      </div>
    </div>

    <div v-else class="text-center py-16 text-gray-400">
      <i class="pi pi-exclamation-triangle text-4xl mb-3 block" />
      Заказ не найден
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Skeleton from 'primevue/skeleton'
import { getOrder, updateOrderStatus, updateOrderTracking, getReference } from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import { formatDate, formatMoney } from '../utils.js'

const route = useRoute()
const toast = useToast()
const orderId = route.params.id

const loading = ref(true)
const order = ref(null)
const statusOptions = ref([])
const changingStatus = ref('')
const editTracking = ref(false)
const trackingInput = ref('')
const savingTracking = ref(false)

onMounted(async () => {
  const [orderData, refData] = await Promise.all([
    getOrder(orderId),
    getReference()
  ])
  order.value = orderData
  trackingInput.value = orderData.tracking_number || ''
  statusOptions.value = refData.order_statuses
  loading.value = false
})

async function changeStatus(newStatus) {
  if (newStatus === order.value.status) return
  changingStatus.value = newStatus
  try {
    await updateOrderStatus(orderId, newStatus)
    order.value.status = newStatus
    toast.add({ severity: 'success', summary: 'Готово', detail: `Статус изменён на «${newStatus}»`, life: 3000 })
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось изменить статус', life: 3000 })
  } finally {
    changingStatus.value = ''
  }
}

async function saveTracking() {
  savingTracking.value = true
  try {
    await updateOrderTracking(orderId, trackingInput.value)
    order.value.tracking_number = trackingInput.value
    editTracking.value = false
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Трек-номер обновлён', life: 3000 })
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось сохранить трек-номер', life: 3000 })
  } finally {
    savingTracking.value = false
  }
}
</script>
