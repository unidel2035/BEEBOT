<template>
  <div class="stock-terminal">
    <!-- Оффлайн-баннер -->
    <div v-if="offline" class="bg-amber-100 text-amber-800 px-4 py-2 rounded-lg mb-4 flex items-center gap-2 text-sm">
      <i class="pi pi-wifi-off" />
      <span>Нет связи — работаем с кэшем</span>
      <span v-if="queueCount > 0" class="ml-auto font-semibold">{{ queueCount }} в очереди</span>
    </div>

    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xl font-bold text-gray-800">
        <i class="pi pi-warehouse mr-2" />Склад
      </h2>
      <div class="flex gap-2">
        <ToggleButton
          v-model="showLowOnly"
          on-label="Мало"
          off-label="Все"
          on-icon="pi pi-exclamation-triangle"
          off-icon="pi pi-list"
          @change="filterProducts"
        />
        <Button icon="pi pi-refresh" size="small" @click="loadProducts" :loading="loading" />
      </div>
    </div>

    <!-- Поиск -->
    <div class="mb-4">
      <InputText
        v-model="searchQuery"
        placeholder="Поиск по названию или артикулу..."
        class="w-full"
        @input="filterProducts"
      />
    </div>

    <!-- Категории -->
    <div class="flex gap-2 flex-wrap mb-4">
      <Button
        v-for="cat in categories"
        :key="cat"
        :label="cat"
        size="small"
        :severity="selectedCategory === cat ? 'primary' : 'secondary'"
        :outlined="selectedCategory !== cat"
        @click="selectCategory(cat)"
      />
    </div>

    <!-- Загрузка -->
    <div v-if="loading && !products.length" class="space-y-2">
      <Skeleton v-for="i in 8" :key="i" height="56px" class="rounded-lg" />
    </div>

    <!-- Список товаров -->
    <div v-else class="space-y-1">
      <div
        v-for="product in filteredProducts"
        :key="product.id"
        class="bg-white rounded-lg border px-4 py-3 flex items-center gap-3"
        :class="stockClass(product)"
      >
        <!-- Артикул -->
        <div class="w-14 text-xs font-mono text-gray-400 flex-shrink-0">
          {{ product.short_name || '—' }}
        </div>

        <!-- Название -->
        <div class="flex-1 min-w-0">
          <div class="font-medium text-sm truncate" :class="product.stock === 0 ? 'text-gray-400' : 'text-gray-800'">
            {{ product.name }}
          </div>
          <div class="text-xs text-gray-400">{{ product.category || '' }}</div>
        </div>

        <!-- Остаток с кнопками +/- -->
        <div class="flex items-center gap-1 flex-shrink-0">
          <button
            class="w-8 h-8 rounded-lg bg-gray-100 hover:bg-red-100 text-gray-600 hover:text-red-600 flex items-center justify-center transition-colors"
            @click="adjustStock(product, -1)"
            :disabled="product.stock <= 0 || product._saving"
          >
            <i class="pi pi-minus text-xs" />
          </button>

          <div
            class="w-14 h-8 rounded-lg flex items-center justify-center font-bold text-sm cursor-pointer"
            :class="stockBadgeClass(product)"
            @click="openStockEdit(product)"
          >
            {{ product._saving ? '...' : (product.stock ?? '—') }}
          </div>

          <button
            class="w-8 h-8 rounded-lg bg-gray-100 hover:bg-green-100 text-gray-600 hover:text-green-600 flex items-center justify-center transition-colors"
            @click="adjustStock(product, 1)"
            :disabled="product._saving"
          >
            <i class="pi pi-plus text-xs" />
          </button>
        </div>
      </div>

      <div v-if="filteredProducts.length === 0" class="text-center py-8 text-gray-400">
        Ничего не найдено
      </div>
    </div>

    <!-- Итого -->
    <div v-if="products.length" class="mt-4 text-sm text-gray-400 text-center">
      Всего: {{ filteredProducts.length }} товаров
      <span v-if="lowStockCount > 0" class="text-amber-600 ml-2">
        <i class="pi pi-exclamation-triangle" /> {{ lowStockCount }} заканчиваются
      </span>
      <span v-if="outOfStockCount > 0" class="text-red-500 ml-2">
        <i class="pi pi-times-circle" /> {{ outOfStockCount }} нет в наличии
      </span>
    </div>

    <!-- Диалог ручного ввода остатка -->
    <Dialog
      v-model:visible="editDialogVisible"
      header="Изменить остаток"
      :style="{ width: '320px' }"
      modal
    >
      <div v-if="editingProduct" class="space-y-4">
        <div class="text-sm text-gray-600">{{ editingProduct.name }}</div>
        <div>
          <label class="block text-sm text-gray-500 mb-1">Новый остаток</label>
          <InputNumber v-model="newStockValue" :min="0" class="w-full" autofocus />
        </div>
        <div class="flex gap-3 justify-end">
          <Button label="Отмена" severity="secondary" size="small" @click="editDialogVisible = false" />
          <Button label="Сохранить" size="small" @click="saveStockEdit" :loading="editSaving" />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import ToggleButton from 'primevue/togglebutton'
import Skeleton from 'primevue/skeleton'
import Dialog from 'primevue/dialog'
import { getProducts, updateStock } from '../api.js'
import { fetchWithCache, enqueue, getQueue, syncQueue } from '../stores/offline.js'

const LOW_STOCK_THRESHOLD = 5

const toast = useToast()
const loading = ref(false)
const offline = ref(false)
const products = ref([])
const filteredProducts = ref([])
const searchQuery = ref('')
const showLowOnly = ref(false)
const selectedCategory = ref(null)
const queueCount = ref(0)

// Ручной ввод
const editDialogVisible = ref(false)
const editingProduct = ref(null)
const newStockValue = ref(0)
const editSaving = ref(false)

const categories = ['Все', 'Мёд', 'Наборы', 'Настойки', 'Свечи', 'Чаи и травы', 'Упаковка', 'Продукты пчеловодства']

const lowStockCount = computed(() =>
  products.value.filter(p => p.stock !== null && p.stock > 0 && p.stock <= LOW_STOCK_THRESHOLD).length
)
const outOfStockCount = computed(() =>
  products.value.filter(p => p.stock !== null && p.stock === 0).length
)

onMounted(async () => {
  await loadProducts()
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
})

onUnmounted(() => {
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
})

function onOnline() {
  offline.value = false
  trySyncQueue()
  loadProducts()
}

function onOffline() {
  offline.value = true
}

async function loadProducts() {
  loading.value = true
  try {
    const { data, offline: off } = await fetchWithCache('stock-products', () => getProducts())
    offline.value = off
    products.value = (data || []).map(p => ({
      ...p,
      stock: p.stock ?? null,
      _saving: false
    }))
    filterProducts()
    await updateQueueCount()
  } finally {
    loading.value = false
  }
}

function selectCategory(cat) {
  selectedCategory.value = (selectedCategory.value === cat || cat === 'Все') ? null : cat
  filterProducts()
}

function filterProducts() {
  let list = products.value
  const q = searchQuery.value.toLowerCase().trim()
  if (q) {
    list = list.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.short_name || '').toLowerCase().includes(q)
    )
  }
  if (selectedCategory.value) {
    list = list.filter(p => p.category === selectedCategory.value)
  }
  if (showLowOnly.value) {
    list = list.filter(p => p.stock !== null && p.stock <= LOW_STOCK_THRESHOLD)
  }
  filteredProducts.value = list
}

async function adjustStock(product, delta) {
  const newVal = Math.max(0, (product.stock || 0) + delta)
  await setStock(product, newVal)
}

function openStockEdit(product) {
  editingProduct.value = product
  newStockValue.value = product.stock || 0
  editDialogVisible.value = true
}

async function saveStockEdit() {
  if (!editingProduct.value) return
  editSaving.value = true
  try {
    await setStock(editingProduct.value, newStockValue.value)
    editDialogVisible.value = false
  } finally {
    editSaving.value = false
  }
}

async function setStock(product, newVal) {
  product._saving = true
  try {
    if (navigator.onLine) {
      await updateStock(product.id, newVal)
    } else {
      await enqueue({ type: 'stock', productId: product.id, stock: newVal })
    }
    product.stock = newVal
    filterProducts()
    toast.add({
      severity: 'success',
      summary: product.short_name || product.name,
      detail: `Остаток: ${newVal}`,
      life: 1500
    })
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось обновить остаток', life: 3000 })
  } finally {
    product._saving = false
  }
  await updateQueueCount()
}

async function updateQueueCount() {
  const q = await getQueue()
  queueCount.value = q.length
}

async function trySyncQueue() {
  await syncQueue(async (item) => {
    if (item.type === 'stock') {
      await updateStock(item.productId, item.stock)
    }
  })
  await updateQueueCount()
}

function stockClass(product) {
  if (product.stock === null) return 'border-gray-100'
  if (product.stock === 0) return 'border-red-200 bg-red-50/50'
  if (product.stock <= LOW_STOCK_THRESHOLD) return 'border-amber-200 bg-amber-50/50'
  return 'border-gray-100'
}

function stockBadgeClass(product) {
  if (product.stock === null) return 'bg-gray-100 text-gray-400'
  if (product.stock === 0) return 'bg-red-100 text-red-700'
  if (product.stock <= LOW_STOCK_THRESHOLD) return 'bg-amber-100 text-amber-700'
  return 'bg-green-100 text-green-700'
}
</script>

<style scoped>
.stock-terminal {
  max-width: 640px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .stock-terminal {
    margin: -1rem;
    padding: 1rem;
  }
}
</style>
