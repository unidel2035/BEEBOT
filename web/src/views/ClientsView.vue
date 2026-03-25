<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-800">Клиенты</h2>
      <Button
        v-if="duplicateCount > 0"
        :label="`Дубли (${duplicateCount})`"
        icon="pi pi-exclamation-triangle"
        severity="warn"
        size="small"
        @click="showDuplicates"
      />
    </div>

    <div class="bg-white rounded-xl border border-gray-100 shadow-sm">
      <DataTable
        :value="clients"
        :loading="loading"
        lazy
        paginator
        :rows="50"
        :total-records="totalRecords"
        row-hover
        class="text-sm"
        @page="onPage"
        @row-click="(e) => $router.push(`/clients/${e.data.id}`)"
      >
        <template #header>
          <div class="flex justify-between items-center p-1">
            <span class="text-base font-semibold text-gray-700">{{ totalRecords }} клиентов</span>
            <div class="flex gap-2 items-center">
              <IconField>
                <InputIcon class="pi pi-search" />
                <InputText
                  v-model="searchQuery"
                  placeholder="Поиск по имени, телефону, городу"
                  class="w-64"
                />
              </IconField>
              <Button
                label="CSV"
                icon="pi pi-download"
                severity="secondary"
                size="small"
                :loading="exporting"
                @click="doExport"
              />
            </div>
          </div>
        </template>
        <template #empty>
          <div class="text-center py-8 text-gray-400">Клиенты не найдены</div>
        </template>
        <Column field="name" header="ФИО" sortable />
        <Column field="phone" header="Телефон">
          <template #body="{ data }">{{ data.phone || '—' }}</template>
        </Column>
        <Column field="city" header="Город">
          <template #body="{ data }">{{ data.city || '—' }}</template>
        </Column>
        <Column field="telegram_username" header="Telegram">
          <template #body="{ data }">
            <span v-if="data.telegram_username" class="text-blue-500">
              @{{ data.telegram_username }}
            </span>
            <span v-else class="text-gray-300">—</span>
          </template>
        </Column>
        <Column field="source" header="Источник">
          <template #body="{ data }">
            <Tag :value="data.source || 'Неизвестно'" severity="secondary" />
          </template>
        </Column>
      </DataTable>
    </div>

    <!-- Диалог дублей -->
    <Dialog
      v-model:visible="dupDialogVisible"
      header="Дубли клиентов"
      :style="{ width: '620px' }"
      modal
    >
      <div v-if="dupGroups.length === 0" class="text-center py-8 text-gray-400">
        Дублей не найдено
      </div>
      <div v-else class="space-y-4">
        <div
          v-for="group in dupGroups"
          :key="group.phone"
          class="border border-gray-100 rounded-lg p-4"
        >
          <div class="text-sm font-semibold text-gray-600 mb-2">
            <i class="pi pi-phone mr-1" />{{ group.phone }}
          </div>
          <div class="space-y-2">
            <div
              v-for="client in group.clients"
              :key="client.id"
              class="flex items-center justify-between text-sm bg-gray-50 rounded px-3 py-2"
            >
              <div>
                <span class="font-medium text-gray-800">{{ client.name }}</span>
                <span class="text-gray-400 ml-2 text-xs">#{{ client.id }}</span>
                <span v-if="client.telegram_username" class="text-blue-400 ml-2 text-xs">@{{ client.telegram_username }}</span>
              </div>
              <Button
                label="Оставить"
                size="small"
                severity="secondary"
                :outlined="mergePrimary?.id !== client.id"
                :severity="mergePrimary?.id === client.id ? 'success' : 'secondary'"
                @click="selectPrimary(group, client)"
              />
            </div>
          </div>
          <div v-if="mergePrimary && mergePrimary._phone === group.phone" class="mt-3 flex justify-end">
            <Button
              label="Объединить"
              icon="pi pi-check"
              size="small"
              :loading="merging"
              @click="doMerge(group)"
            />
          </div>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Tag from 'primevue/tag'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { getClients, exportClients } from '../api.js'

const toast = useToast()
const confirm = useConfirm()
const loading = ref(true)
const exporting = ref(false)
const clients = ref([])
const totalRecords = ref(0)
const currentPage = ref(1)
const searchQuery = ref('')
const duplicateCount = ref(0)

// Дубли
const dupDialogVisible = ref(false)
const dupGroups = ref([])
const dupLoading = ref(false)
const mergePrimary = ref(null)
const merging = ref(false)

let searchTimer = null

async function loadClients(page = 1) {
  loading.value = true
  currentPage.value = page
  try {
    const params = { page }
    if (searchQuery.value) params.search = searchQuery.value
    const result = await getClients(params)
    clients.value = result.items ?? result
    totalRecords.value = result.total ?? clients.value.length
  } finally {
    loading.value = false
  }
}

function onPage(event) {
  loadClients(event.page + 1)
}

watch(searchQuery, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadClients(1), 400)
})

onMounted(async () => {
  await loadClients()
  // Загружаем кол-во дублей в фоне
  try {
    const resp = await fetch('/api/clients/duplicates', {
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
    })
    if (resp.ok) {
      const result = await resp.json()
      duplicateCount.value = result.total ?? 0
    }
  } catch (_) {}
})

async function showDuplicates() {
  dupDialogVisible.value = true
  dupLoading.value = true
  mergePrimary.value = null
  try {
    const resp = await fetch('/api/clients/duplicates', {
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
    })
    const result = await resp.json()
    dupGroups.value = result.groups ?? []
  } finally {
    dupLoading.value = false
  }
}

function selectPrimary(group, client) {
  mergePrimary.value = { ...client, _phone: group.phone }
}

async function doMerge(group) {
  if (!mergePrimary.value) return
  const duplicate = group.clients.find(c => c.id !== mergePrimary.value.id)
  if (!duplicate) return

  confirm.require({
    message: `Объединить «${duplicate.name}» → «${mergePrimary.value.name}»?\nЗаказы дубля будут перенесены, дубль будет удалён.`,
    header: 'Подтверждение объединения',
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: 'Объединить',
    rejectLabel: 'Отмена',
    acceptClass: 'p-button-danger',
    accept: async () => {
      merging.value = true
      try {
        const resp = await fetch('/api/clients/merge', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('token')}`
          },
          body: JSON.stringify({ primary_id: mergePrimary.value.id, duplicate_id: duplicate.id })
        })
        if (!resp.ok) throw new Error(await resp.text())
        const result = await resp.json()
        toast.add({
          severity: 'success',
          summary: 'Объединено',
          detail: `Перенесено заказов: ${result.orders_moved}`,
          life: 3000
        })
        // Обновить список
        dupGroups.value = dupGroups.value.filter(g => g.phone !== group.phone)
        duplicateCount.value = dupGroups.value.length
        mergePrimary.value = null
        await loadClients(currentPage.value)
      } catch (e) {
        toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось объединить', life: 3000 })
      } finally {
        merging.value = false
      }
    }
  })
}

async function doExport() {
  exporting.value = true
  try {
    await exportClients()
  } finally {
    exporting.value = false
  }
}
</script>
