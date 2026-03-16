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

    <!-- Графики -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      <!-- Выручка по месяцам -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Выручка по месяцам</h3>
        <Chart v-if="revenueChartData" type="bar" :data="revenueChartData" :options="revenueOptions" class="h-64" />
        <Skeleton v-else height="256px" class="rounded-lg" />
      </div>

      <!-- Воронка статусов -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Заказы по статусам</h3>
        <Chart v-if="funnelChartData" type="bar" :data="funnelChartData" :options="funnelOptions" class="h-64" />
        <Skeleton v-else height="256px" class="rounded-lg" />
      </div>

      <!-- Заказы по месяцам (линия) -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Количество заказов</h3>
        <Chart v-if="countChartData" type="line" :data="countChartData" :options="countOptions" class="h-64" />
        <Skeleton v-else height="256px" class="rounded-lg" />
      </div>

      <!-- Способы доставки (пончик) -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Способы доставки</h3>
        <div class="flex justify-center">
          <Chart v-if="deliveryChartData" type="doughnut" :data="deliveryChartData" :options="doughnutOptions" style="max-height: 256px; max-width: 320px;" />
          <Skeleton v-else height="256px" width="320px" class="rounded-lg" />
        </div>
      </div>
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
import Chart from 'primevue/chart'
import { getDashboard, getDashboardCharts, getOrders } from '../api.js'
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

// Chart data
const revenueChartData = ref(null)
const countChartData = ref(null)
const funnelChartData = ref(null)
const deliveryChartData = ref(null)

// Chart options
const revenueOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx) => `${ctx.parsed.y.toLocaleString('ru-RU')} \u20BD`
      }
    }
  },
  scales: {
    y: {
      beginAtZero: true,
      ticks: {
        callback: (v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v
      }
    }
  }
}

const countOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    y: { beginAtZero: true, ticks: { stepSize: 1 } }
  }
}

const funnelOptions = {
  indexAxis: 'y',
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { beginAtZero: true, ticks: { stepSize: 1 } }
  }
}

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom', labels: { padding: 16 } }
  }
}

const STATUS_COLORS = {
  'Новый': '#3b82f6',
  'Подтверждён': '#f59e0b',
  'В сборке': '#8b5cf6',
  'Отправлен': '#06b6d4',
  'Доставлен': '#10b981',
  'Отменён': '#ef4444',
}

const DELIVERY_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444']

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

  // Load charts data (non-blocking)
  try {
    const charts = await getDashboardCharts()

    // Revenue bar chart
    revenueChartData.value = {
      labels: charts.monthly.labels,
      datasets: [{
        label: 'Выручка',
        data: charts.monthly.revenue,
        backgroundColor: '#f59e0b',
        borderRadius: 6,
        borderSkipped: false,
      }]
    }

    // Orders count line chart
    countChartData.value = {
      labels: charts.monthly.labels,
      datasets: [{
        label: 'Заказов',
        data: charts.monthly.count,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: '#3b82f6',
      }]
    }

    // Status funnel (horizontal bar)
    funnelChartData.value = {
      labels: charts.funnel.labels,
      datasets: [{
        data: charts.funnel.data,
        backgroundColor: charts.funnel.labels.map(s => STATUS_COLORS[s] || '#9ca3af'),
        borderRadius: 6,
        borderSkipped: false,
      }]
    }

    // Delivery doughnut
    deliveryChartData.value = {
      labels: charts.delivery.labels,
      datasets: [{
        data: charts.delivery.data,
        backgroundColor: DELIVERY_COLORS.slice(0, charts.delivery.labels.length),
        hoverOffset: 8,
      }]
    }
  } catch (e) {
    console.error('Charts load error:', e)
  }
})
</script>
