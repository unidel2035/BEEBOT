<template>
  <div>
    <h2 class="text-2xl font-bold text-gray-800 mb-6">Дашборд</h2>

    <!-- Карточки статистики -->
    <div v-if="loading" class="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
      <Skeleton v-for="i in 6" :key="i" height="100px" class="rounded-xl" />
    </div>

    <div v-else class="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
      <StatCard
        icon="pi-list"
        icon-color="text-amber-600"
        bg-color="bg-amber-50"
        label="Всего заказов"
        :value="stats.total_orders"
      />
      <StatCard
        icon="pi-users"
        icon-color="text-blue-600"
        bg-color="bg-blue-50"
        label="Клиентов"
        :value="stats.total_clients"
      />
      <StatCard
        icon="pi-wallet"
        icon-color="text-green-600"
        bg-color="bg-green-50"
        label="Общая выручка"
        :value="formatMoney(stats.total_revenue)"
      />
      <StatCard
        icon="pi-chart-line"
        icon-color="text-purple-600"
        bg-color="bg-purple-50"
        label="Средний чек"
        :value="formatMoney(stats.avg_order)"
      />
      <StatCard
        icon="pi-shopping-cart"
        icon-color="text-orange-600"
        bg-color="bg-orange-50"
        label="Новых заказов"
        :value="stats.new_orders"
      />
      <StatCard
        icon="pi-truck"
        icon-color="text-teal-600"
        bg-color="bg-teal-50"
        label="Доставленных"
        :value="stats.delivered_orders"
      />
    </div>

    <!-- Последние заказы -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold text-gray-700">Последние заказы</h3>
        <RouterLink to="/orders" class="text-sm text-amber-600 hover:text-amber-700 font-medium">
          Все заказы →
        </RouterLink>
      </div>

      <DataTable
        :value="recentOrders"
        :loading="ordersLoading"
        row-hover
        class="text-sm"
        @row-click="(e) => $router.push(`/orders/${e.data.id}`)"
      >
        <Column field="number" header="Номер" style="width:120px" />
        <Column field="client_name" header="Клиент">
          <template #body="{ data }">{{ data.client_name || `Клиент #${data.client_id}` }}</template>
        </Column>
        <Column field="date" header="Дата">
          <template #body="{ data }">{{ formatDate(data.date) }}</template>
        </Column>
        <Column field="status" header="Статус">
          <template #body="{ data }">
            <StatusBadge :status="data.status" />
          </template>
        </Column>
        <Column field="total" header="Сумма">
          <template #body="{ data }">{{ formatMoney(data.total) }}</template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Skeleton from 'primevue/skeleton'
import { getDashboard, getOrders } from '../api.js'
import StatCard from '../components/StatCard.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { formatDate, formatMoney } from '../utils.js'

const loading = ref(true)
const ordersLoading = ref(true)
const stats = ref({
  total_orders: 0,
  total_clients: 0,
  total_revenue: 0,
  avg_order: 0,
  new_orders: 0,
  delivered_orders: 0
})
const recentOrders = ref([])

onMounted(async () => {
  try {
    const [dashData, ordersData] = await Promise.all([
      getDashboard(),
      getOrders()
    ])
    stats.value = dashData
    recentOrders.value = ordersData.slice(0, 10)
  } finally {
    loading.value = false
    ordersLoading.value = false
  }
})
</script>
