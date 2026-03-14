<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-800">Журнал заказов</h2>
      <div class="flex gap-2 items-center">
        <Button
          icon="pi pi-chevron-left"
          severity="secondary"
          size="small"
          @click="prevMonth"
        />
        <span class="text-lg font-semibold text-gray-700 min-w-[160px] text-center">
          {{ monthLabel }}
        </span>
        <Button
          icon="pi pi-chevron-right"
          severity="secondary"
          size="small"
          @click="nextMonth"
        />
      </div>
    </div>

    <!-- Сводка по месяцу -->
    <div v-if="!loading" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
      <div class="bg-white rounded-lg border border-gray-100 p-3 text-center">
        <div class="text-2xl font-bold text-amber-600">{{ monthOrders.length }}</div>
        <div class="text-xs text-gray-500">Заказов</div>
      </div>
      <div class="bg-white rounded-lg border border-gray-100 p-3 text-center">
        <div class="text-2xl font-bold text-green-600">{{ formatMoney(monthTotal) }}</div>
        <div class="text-xs text-gray-500">Сумма</div>
      </div>
      <div class="bg-white rounded-lg border border-gray-100 p-3 text-center">
        <div class="text-2xl font-bold text-blue-600">{{ uniqueClients }}</div>
        <div class="text-xs text-gray-500">Клиентов</div>
      </div>
      <div class="bg-white rounded-lg border border-gray-100 p-3 text-center">
        <div class="text-2xl font-bold text-purple-600">{{ formatMoney(avgCheck) }}</div>
        <div class="text-xs text-gray-500">Средний чек</div>
      </div>
    </div>

    <!-- Таблица заказов -->
    <div class="bg-white rounded-xl border border-gray-100 shadow-sm">
      <DataTable
        :value="monthOrders"
        :loading="loading"
        paginator
        :rows="50"
        row-hover
        class="text-sm"
        scrollable
        scroll-height="70vh"
        :sort-field="'number'"
        :sort-order="-1"
      >
        <template #empty>
          <div class="text-center py-8 text-gray-400">Заказов за {{ monthLabel }} нет</div>
        </template>
        <Column header="№" style="width:50px">
          <template #body="{ index }">{{ index + 1 }}</template>
        </Column>
        <Column field="number" header="Номер заказа" sortable style="width:130px" />
        <Column field="source" header="Источник" sortable style="width:100px">
          <template #body="{ data }">
            <Tag :value="data.source || '—'" :severity="sourceSeverity(data.source)" />
          </template>
        </Column>
        <Column field="client_name" header="Клиент" sortable style="min-width:160px">
          <template #body="{ data }">
            <div class="font-medium">{{ data.client_name || '—' }}</div>
          </template>
        </Column>
        <Column field="messenger" header="Мессенджер" style="width:100px">
          <template #body="{ data }">{{ data.messenger || '—' }}</template>
        </Column>
        <Column field="delivery_address" header="Адрес доставки" style="min-width:200px">
          <template #body="{ data }">
            <div class="text-xs leading-tight max-w-xs" :title="data.delivery_address">
              {{ truncate(data.delivery_address, 80) || '—' }}
            </div>
          </template>
        </Column>
        <Column field="comment" header="Состав / Комментарий" style="min-width:220px">
          <template #body="{ data }">
            <div class="text-xs leading-tight max-w-sm whitespace-pre-line" :title="data.comment">
              {{ truncate(data.comment, 120) || '—' }}
            </div>
          </template>
        </Column>
        <Column field="total" header="Сумма" sortable style="width:100px">
          <template #body="{ data }">
            <span class="font-medium">{{ formatMoney(data.total) }}</span>
          </template>
        </Column>
        <Column field="status" header="Статус" sortable style="width:110px">
          <template #body="{ data }">
            <StatusBadge :status="data.status" />
          </template>
        </Column>
        <Column field="tracking_number" header="Трек-номер" style="width:120px">
          <template #body="{ data }">
            <span v-if="data.tracking_number" class="font-mono text-xs text-blue-600">
              {{ data.tracking_number }}
            </span>
            <span v-else class="text-gray-300">—</span>
          </template>
        </Column>
        <Column field="date" header="Дата" sortable style="width:100px">
          <template #body="{ data }">{{ formatDate(data.date) }}</template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import { getOrders } from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import { formatDate, formatMoney } from '../utils.js'

const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

const loading = ref(true)
const allOrders = ref([])
const now = new Date()
const currentMonth = ref(now.getMonth()) // 0-11
const currentYear = ref(now.getFullYear())

const monthLabel = computed(() => `${MONTH_NAMES[currentMonth.value]} ${currentYear.value}`)

const monthOrders = computed(() => {
  const m = currentMonth.value + 1 // 1-12
  const y = currentYear.value
  const key = `${String(m).padStart(2, '0')}.${y}` // "03.2026"
  return allOrders.value.filter(o => o.month === key)
})

const monthTotal = computed(() =>
  monthOrders.value.reduce((sum, o) => sum + (o.total || 0), 0)
)

const uniqueClients = computed(() =>
  new Set(monthOrders.value.map(o => o.client_name).filter(Boolean)).size
)

const avgCheck = computed(() =>
  monthOrders.value.length ? monthTotal.value / monthOrders.value.length : 0
)

function prevMonth() {
  if (currentMonth.value === 0) {
    currentMonth.value = 11
    currentYear.value--
  } else {
    currentMonth.value--
  }
}

function nextMonth() {
  if (currentMonth.value === 11) {
    currentMonth.value = 0
    currentYear.value++
  } else {
    currentMonth.value++
  }
}

function truncate(str, len) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

function sourceSeverity(source) {
  const map = {
    'ВК': 'info',
    'Instagram': 'warn',
    'Telegram': 'success',
    'WhatsApp': 'success',
    'UDS': 'secondary',
  }
  return map[source] || 'secondary'
}

onMounted(async () => {
  try {
    allOrders.value = await getOrders()
  } finally {
    loading.value = false
  }
})
</script>
