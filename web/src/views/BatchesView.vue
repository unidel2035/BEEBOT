<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-800">Партии отправки</h2>
      <Button label="Создать партию" icon="pi pi-plus" size="small" @click="openCreate" />
    </div>

    <!-- Таблица партий -->
    <div class="bg-white rounded-xl border border-gray-100 shadow-sm">
      <DataTable
        :value="batches"
        :loading="loading"
        row-hover
        class="text-sm"
        @row-click="(e) => openBatch(e.data)"
      >
        <template #empty>
          <div class="text-center py-8 text-gray-400">Партий нет</div>
        </template>

        <Column field="date" header="Дата" style="width:120px">
          <template #body="{ data }">{{ formatDate(data.date) }}</template>
        </Column>
        <Column field="delivery_method" header="Способ доставки">
          <template #body="{ data }">{{ data.delivery_method || '—' }}</template>
        </Column>
        <Column field="order_count" header="Заказов" style="width:100px">
          <template #body="{ data }">
            <Tag :value="String(data.order_count || 0)" severity="info" />
          </template>
        </Column>
        <Column field="note" header="Примечание">
          <template #body="{ data }">{{ data.note || '—' }}</template>
        </Column>
        <Column header="" style="width:80px">
          <template #body="{ data }">
            <Button
              icon="pi pi-eye"
              severity="secondary"
              text
              size="small"
              @click.stop="openBatch(data)"
            />
          </template>
        </Column>
      </DataTable>
    </div>

    <!-- Диалог создания партии -->
    <Dialog
      v-model:visible="createDialogVisible"
      header="Новая партия отправки"
      :style="{ width: '400px' }"
      modal
    >
      <form @submit.prevent="handleCreate" class="space-y-4 mt-2">
        <div>
          <label class="block text-sm text-gray-600 mb-1">Дата отправки <span class="text-red-400">*</span></label>
          <DatePicker v-model="createForm.date" date-format="dd.mm.yy" class="w-full" required />
        </div>
        <div>
          <label class="block text-sm text-gray-600 mb-1">Способ доставки</label>
          <Select
            v-model="createForm.delivery_method"
            :options="deliveryOptions"
            placeholder="Все / не указан"
            class="w-full"
            show-clear
          />
        </div>
        <div>
          <label class="block text-sm text-gray-600 mb-1">Примечание</label>
          <InputText v-model="createForm.note" class="w-full" />
        </div>
        <div class="flex gap-3 justify-end pt-2">
          <Button label="Отмена" severity="secondary" type="button" @click="createDialogVisible = false" />
          <Button label="Создать" type="submit" :loading="creating" />
        </div>
      </form>
    </Dialog>

    <!-- Диалог заказов партии -->
    <Dialog
      v-model:visible="batchDialogVisible"
      :header="selectedBatch ? `Партия ${formatDate(selectedBatch.date)}` : ''"
      :style="{ width: '700px' }"
      modal
    >
      <div v-if="selectedBatch" class="space-y-3">
        <div class="flex gap-6 text-sm text-gray-500 pb-2 border-b border-gray-100">
          <span v-if="selectedBatch.delivery_method">
            <i class="pi pi-truck mr-1" />{{ selectedBatch.delivery_method }}
          </span>
          <span>
            <i class="pi pi-box mr-1" />{{ batchOrders.length }} заказов
          </span>
          <span v-if="selectedBatch.note">
            <i class="pi pi-info-circle mr-1" />{{ selectedBatch.note }}
          </span>
        </div>

        <DataTable :value="batchOrders" :loading="batchOrdersLoading" class="text-sm">
          <template #empty>
            <div class="text-center py-4 text-gray-400">Нет заказов в партии</div>
          </template>
          <Column field="number" header="Номер" style="width:120px" />
          <Column field="client_name" header="Клиент">
            <template #body="{ data }">{{ data.client_name || `Клиент #${data.client_id}` }}</template>
          </Column>
          <Column field="status" header="Статус">
            <template #body="{ data }"><StatusBadge :status="data.status" /></template>
          </Column>
          <Column field="total" header="Сумма">
            <template #body="{ data }">{{ formatMoney(data.total) }}</template>
          </Column>
          <Column field="tracking_number" header="Трек">
            <template #body="{ data }">{{ data.tracking_number || '—' }}</template>
          </Column>
        </DataTable>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import DatePicker from 'primevue/datepicker'
import Tag from 'primevue/tag'
import { getBatches, createBatch, getBatchOrders } from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import { formatDate, formatMoney } from '../utils.js'

const toast = useToast()
const loading = ref(true)
const batches = ref([])

const deliveryOptions = ['СДЭК', 'Почта России', 'Самовывоз']

// Создание
const createDialogVisible = ref(false)
const creating = ref(false)
const createForm = ref({ date: null, delivery_method: null, note: '' })

// Просмотр
const batchDialogVisible = ref(false)
const selectedBatch = ref(null)
const batchOrders = ref([])
const batchOrdersLoading = ref(false)

onMounted(() => loadBatches())

async function loadBatches() {
  loading.value = true
  try {
    const result = await getBatches()
    batches.value = result.items ?? result
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.value = { date: new Date(), delivery_method: null, note: '' }
  createDialogVisible.value = true
}

async function handleCreate() {
  if (!createForm.value.date) return
  creating.value = true
  try {
    const d = createForm.value.date
    const dateStr = `${String(d.getDate()).padStart(2,'0')}.${String(d.getMonth()+1).padStart(2,'0')}.${d.getFullYear()}`
    await createBatch({
      date: dateStr,
      delivery_method: createForm.value.delivery_method || '',
      note: createForm.value.note || ''
    })
    toast.add({ severity: 'success', summary: 'Партия создана', life: 2500 })
    createDialogVisible.value = false
    await loadBatches()
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось создать партию', life: 3000 })
  } finally {
    creating.value = false
  }
}

async function openBatch(batch) {
  selectedBatch.value = batch
  batchDialogVisible.value = true
  batchOrdersLoading.value = true
  try {
    const result = await getBatchOrders(batch.id)
    batchOrders.value = result.items ?? result
  } finally {
    batchOrdersLoading.value = false
  }
}
</script>
