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
          row-hover
          class="text-sm"
          @row-click="(e) => $router.push(`/orders/${e.data.id}`)"
        >
          <template #empty>
            <div class="text-center py-6 text-gray-400">Заказов нет</div>
          </template>
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
        </DataTable>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Skeleton from 'primevue/skeleton'
import Tag from 'primevue/tag'
import { getClient } from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import { formatDate, formatMoney } from '../utils.js'

const route = useRoute()
const clientId = route.params.id
const loading = ref(true)
const client = ref(null)
const orders = ref([])

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
