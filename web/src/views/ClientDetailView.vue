<template>
  <div>
    <div class="flex items-center gap-3 mb-6">
      <Button icon="pi pi-arrow-left" severity="secondary" text @click="$router.back()" />
      <h2 class="text-2xl font-bold text-gray-800">{{ client?.full_name || 'Клиент' }}</h2>
    </div>

    <div v-if="loading" class="space-y-4">
      <Skeleton height="180px" class="rounded-xl" />
      <Skeleton height="200px" class="rounded-xl" />
    </div>

    <div v-else-if="client" class="space-y-4">
      <!-- Карточка клиента -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Данные клиента</h3>
        <dl class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt class="text-gray-400 text-xs">ФИО</dt>
            <dd class="font-medium mt-0.5">{{ client.full_name }}</dd>
          </div>
          <div>
            <dt class="text-gray-400 text-xs">Телефон</dt>
            <dd class="font-medium mt-0.5">{{ client.phone || '—' }}</dd>
          </div>
          <div>
            <dt class="text-gray-400 text-xs">Город</dt>
            <dd class="font-medium mt-0.5">{{ client.city || '—' }}</dd>
          </div>
          <div>
            <dt class="text-gray-400 text-xs">Telegram</dt>
            <dd class="font-medium mt-0.5">
              <span v-if="client.telegram_username" class="text-blue-500">
                @{{ client.telegram_username }}
              </span>
              <span v-else-if="client.telegram_id">ID: {{ client.telegram_id }}</span>
              <span v-else>—</span>
            </dd>
          </div>
          <div class="col-span-2">
            <dt class="text-gray-400 text-xs">Адрес</dt>
            <dd class="font-medium mt-0.5">{{ client.address || '—' }}</dd>
          </div>
          <div>
            <dt class="text-gray-400 text-xs">Источник</dt>
            <dd class="mt-0.5"><Tag :value="client.source || 'Неизвестно'" severity="secondary" /></dd>
          </div>
        </dl>
      </div>

      <!-- История заказов -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h3 class="font-semibold text-gray-700 mb-4">
          История заказов
          <span class="ml-2 text-gray-400 font-normal text-sm">({{ orders.length }})</span>
        </h3>
        <DataTable
          :value="orders"
          v-model:expandedRows="expandedRows"
          row-hover
          class="text-sm"
          @row-click="(e) => $router.push(`/orders/${e.data.id}`)"
        >
          <template #empty>
            <div class="text-center py-6 text-gray-400">Заказов нет</div>
          </template>
          <Column expander style="width:3rem" />
          <Column field="number" header="Номер" style="width:120px" />
          <Column field="date" header="Дата">
            <template #body="{ data }">{{ formatDate(data.date) }}</template>
          </Column>
          <Column field="status" header="Статус">
            <template #body="{ data }"><StatusBadge :status="data.status" /></template>
          </Column>
          <Column field="total" header="Сумма">
            <template #body="{ data }">{{ formatMoney(data.total) }}</template>
          </Column>
          <template #expansion="{ data }">
            <div class="px-4 py-2">
              <div v-if="!data.items" class="text-sm text-gray-400">Загрузка состава...</div>
              <div v-else-if="data.items.length === 0" class="text-sm text-gray-400">Позиции не найдены в CRM</div>
              <table v-else class="text-sm w-full">
                <thead>
                  <tr class="text-gray-500 text-xs">
                    <th class="text-left pb-1 font-medium">Товар</th>
                    <th class="text-right pb-1 font-medium w-16">Кол-во</th>
                    <th class="text-right pb-1 font-medium w-24">Цена</th>
                    <th class="text-right pb-1 font-medium w-24">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in data.items" :key="item.id" class="border-t border-gray-100">
                    <td class="py-1 text-gray-700">{{ item.product_name || `Товар #${item.product_id}` }}</td>
                    <td class="py-1 text-right text-gray-600">{{ item.quantity }} шт</td>
                    <td class="py-1 text-right text-gray-600">{{ formatMoney(item.unit_price) }}</td>
                    <td class="py-1 text-right font-medium">{{ formatMoney(item.total) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </DataTable>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Skeleton from 'primevue/skeleton'
import Tag from 'primevue/tag'
import { getClient, getOrderItems } from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import { formatDate, formatMoney } from '../utils.js'

const route = useRoute()
const clientId = route.params.id
const loading = ref(true)
const client = ref(null)
const orders = ref([])
const expandedRows = ref({})

watch(expandedRows, async (val) => {
  for (const orderId of Object.keys(val)) {
    const order = orders.value.find(o => String(o.id) === orderId)
    if (order && order.items === undefined) {
      order.items = null
      try {
        const items = await getOrderItems(Number(orderId))
        order.items = Array.isArray(items) ? items : (items.items ?? [])
      } catch {
        order.items = []
      }
    }
  }
})

onMounted(async () => {
  try {
    const data = await getClient(clientId)
    orders.value = data.orders || []
    client.value = data
  } finally {
    loading.value = false
  }
})
</script>
