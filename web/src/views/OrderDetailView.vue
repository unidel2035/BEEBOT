<template>
  <div>
    <!-- Заголовок -->
    <div class="flex items-center gap-3 mb-6">
      <Button icon="pi pi-arrow-left" severity="secondary" text @click="$router.back()" />
      <h2 class="text-2xl font-bold text-gray-800">
        Заказ {{ order?.number || '#' + orderId }}
      </h2>
      <StatusBadge v-if="order" :status="order.status" class="ml-1" />
      <span v-if="order && order.editable" class="text-xs text-green-600 bg-green-50 px-2 py-1 rounded-full">
        можно редактировать
      </span>
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
              <dd class="font-medium">
                <span v-if="!editDeliveryCost">
                  {{ formatMoney(order.delivery_cost) }}
                  <button v-if="order.editable" @click="startEditDeliveryCost" class="ml-2 text-gray-400 hover:text-gray-600">
                    <i class="pi pi-pencil text-xs" />
                  </button>
                </span>
                <div v-else class="flex gap-2 items-center">
                  <InputNumber v-model="deliveryCostInput" size="small" class="w-28" suffix=" ₽" :min="0" />
                  <Button icon="pi pi-check" size="small" @click="saveDeliveryCost" :loading="savingOrder" />
                  <Button icon="pi pi-times" size="small" severity="secondary" @click="editDeliveryCost = false" />
                </div>
              </dd>
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
            <div class="flex justify-between items-center">
              <dt class="text-gray-500">Способ</dt>
              <dd class="font-medium">
                <span v-if="!editMethod">
                  {{ order.delivery_method || '—' }}
                  <button v-if="order.editable" @click="editMethod = true" class="ml-2 text-gray-400 hover:text-gray-600">
                    <i class="pi pi-pencil text-xs" />
                  </button>
                </span>
                <div v-else class="flex gap-2 items-center">
                  <Select v-model="methodInput" :options="deliveryMethods" size="small" class="w-40" />
                  <Button icon="pi pi-check" size="small" @click="saveMethod" :loading="savingOrder" />
                  <Button icon="pi pi-times" size="small" severity="secondary" @click="editMethod = false" />
                </div>
              </dd>
            </div>
            <div class="flex justify-between items-start">
              <dt class="text-gray-500">Адрес</dt>
              <dd class="font-medium text-right max-w-xs">
                <span v-if="!editAddress">
                  {{ order.delivery_address || '—' }}
                  <button v-if="order.editable" @click="startEditAddress" class="ml-2 text-gray-400 hover:text-gray-600">
                    <i class="pi pi-pencil text-xs" />
                  </button>
                </span>
                <div v-else class="flex gap-2 items-center">
                  <InputText v-model="addressInput" size="small" class="w-56" />
                  <Button icon="pi pi-check" size="small" @click="saveAddress" :loading="savingOrder" />
                  <Button icon="pi pi-times" size="small" severity="secondary" @click="editAddress = false" />
                </div>
              </dd>
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

          <!-- Комментарий -->
          <div class="mt-4 pt-3 border-t">
            <div class="flex justify-between items-center mb-2">
              <span class="text-gray-500 text-sm">Комментарий</span>
              <button v-if="order.editable && !editComment" @click="startEditComment" class="text-gray-400 hover:text-gray-600">
                <i class="pi pi-pencil text-xs" />
              </button>
            </div>
            <div v-if="!editComment" class="text-sm text-gray-700">{{ order.comment || '—' }}</div>
            <div v-else class="flex gap-2 items-start">
              <Textarea v-model="commentInput" rows="2" class="w-full text-sm" />
              <div class="flex flex-col gap-1">
                <Button icon="pi pi-check" size="small" @click="saveComment" :loading="savingOrder" />
                <Button icon="pi pi-times" size="small" severity="secondary" @click="editComment = false" />
              </div>
            </div>
          </div>
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
        <div class="flex justify-between items-center mb-4">
          <h3 class="font-semibold text-gray-700">Позиции заказа</h3>
          <Button
            v-if="order.editable"
            icon="pi pi-plus"
            label="Добавить"
            size="small"
            severity="success"
            outlined
            @click="showAddItem = true"
          />
        </div>

        <DataTable :value="order.items" class="text-sm">
          <template #empty>
            <div class="text-center py-4 text-gray-400">Позиций нет</div>
          </template>
          <Column field="product_name" header="Товар">
            <template #body="{ data }">{{ data.product_name || `Товар #${data.product_id}` }}</template>
          </Column>
          <Column field="quantity" header="Кол-во" style="width:100px">
            <template #body="{ data }">
              <span v-if="editingItem !== data.id">{{ data.quantity }}</span>
              <InputNumber v-else v-model="editItemQty" size="small" class="w-16" :min="1" />
            </template>
          </Column>
          <Column field="unit_price" header="Цена" style="width:120px">
            <template #body="{ data }">
              <span v-if="editingItem !== data.id">{{ formatMoney(data.unit_price) }}</span>
              <InputNumber v-else v-model="editItemPrice" size="small" class="w-24" suffix=" ₽" :min="0" />
            </template>
          </Column>
          <Column field="total" header="Сумма" style="width:100px">
            <template #body="{ data }">{{ formatMoney(data.total) }}</template>
          </Column>
          <Column v-if="order.editable" header="" style="width:80px">
            <template #body="{ data }">
              <div class="flex gap-1">
                <template v-if="editingItem !== data.id">
                  <Button icon="pi pi-pencil" size="small" text severity="secondary" @click="startEditItem(data)" />
                  <Button icon="pi pi-trash" size="small" text severity="danger" @click="removeItem(data)" :loading="deletingItem === data.id" />
                </template>
                <template v-else>
                  <Button icon="pi pi-check" size="small" text severity="success" @click="saveItem(data)" :loading="savingItem" />
                  <Button icon="pi pi-times" size="small" text severity="secondary" @click="editingItem = null" />
                </template>
              </div>
            </template>
          </Column>
        </DataTable>
      </div>

      <!-- Диалог добавления позиции -->
      <Dialog v-model:visible="showAddItem" header="Добавить товар" modal class="w-96">
        <div class="space-y-3">
          <div>
            <label class="text-sm text-gray-500 mb-1 block">Товар</label>
            <Select
              v-model="newItem.product"
              :options="products"
              optionLabel="name"
              placeholder="Выберите товар"
              filter
              class="w-full"
            />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-sm text-gray-500 mb-1 block">Количество</label>
              <InputNumber v-model="newItem.quantity" :min="1" class="w-full" />
            </div>
            <div>
              <label class="text-sm text-gray-500 mb-1 block">Цена</label>
              <InputNumber v-model="newItem.price" suffix=" ₽" :min="0" class="w-full" />
            </div>
          </div>
        </div>
        <template #footer>
          <Button label="Отмена" severity="secondary" text @click="showAddItem = false" />
          <Button label="Добавить" @click="addItem" :loading="addingItem" :disabled="!newItem.product" />
        </template>
      </Dialog>
    </div>

    <div v-else class="text-center py-16 text-gray-400">
      <i class="pi pi-exclamation-triangle text-4xl mb-3 block" />
      Заказ не найден
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import Dialog from 'primevue/dialog'
import Skeleton from 'primevue/skeleton'
import {
  getOrder, updateOrderStatus, updateOrderTracking, updateOrder,
  addOrderItem, updateOrderItem, deleteOrderItem,
  getReference, getProducts
} from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import { formatDate, formatMoney } from '../utils.js'

const route = useRoute()
const toast = useToast()
const orderId = route.params.id

const loading = ref(true)
const order = ref(null)
const statusOptions = ref([])
const deliveryMethods = ref([])
const products = ref([])
const changingStatus = ref('')
const savingOrder = ref(false)

// Tracking
const editTracking = ref(false)
const trackingInput = ref('')
const savingTracking = ref(false)

// Address
const editAddress = ref(false)
const addressInput = ref('')

// Delivery method
const editMethod = ref(false)
const methodInput = ref('')

// Delivery cost
const editDeliveryCost = ref(false)
const deliveryCostInput = ref(0)

// Comment
const editComment = ref(false)
const commentInput = ref('')

// Items editing
const editingItem = ref(null)
const editItemQty = ref(1)
const editItemPrice = ref(0)
const savingItem = ref(false)
const deletingItem = ref(null)

// Add item dialog
const showAddItem = ref(false)
const addingItem = ref(false)
const newItem = ref({ product: null, quantity: 1, price: 0 })

// Auto-fill price when product is selected
watch(() => newItem.value.product, (p) => {
  if (p && p.price) newItem.value.price = p.price
})

onMounted(async () => {
  const [orderData, refData, productsData] = await Promise.all([
    getOrder(orderId),
    getReference(),
    getProducts()
  ])
  order.value = orderData
  trackingInput.value = orderData.tracking_number || ''
  statusOptions.value = refData.order_statuses
  deliveryMethods.value = refData.delivery_methods
  products.value = productsData
  loading.value = false
})

async function reloadOrder() {
  order.value = await getOrder(orderId)
}

async function changeStatus(newStatus) {
  if (newStatus === order.value.status) return
  changingStatus.value = newStatus
  try {
    await updateOrderStatus(orderId, newStatus)
    order.value.status = newStatus
    order.value.editable = ['Новый', 'Подтверждён', 'В сборке'].includes(newStatus)
    toast.add({ severity: 'success', summary: 'Готово', detail: `Статус изменён на "${newStatus}"`, life: 3000 })
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
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось сохранить', life: 3000 })
  } finally {
    savingTracking.value = false
  }
}

// --- Order field editing ---

function startEditAddress() {
  addressInput.value = order.value.delivery_address || ''
  editAddress.value = true
}

async function saveAddress() {
  savingOrder.value = true
  try {
    await updateOrder(orderId, { delivery_address: addressInput.value })
    order.value.delivery_address = addressInput.value
    editAddress.value = false
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Адрес обновлён', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e.response?.data?.detail || 'Не удалось сохранить', life: 3000 })
  } finally {
    savingOrder.value = false
  }
}

async function saveMethod() {
  savingOrder.value = true
  try {
    await updateOrder(orderId, { delivery_method: methodInput.value })
    order.value.delivery_method = methodInput.value
    editMethod.value = false
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Способ доставки обновлён', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e.response?.data?.detail || 'Не удалось сохранить', life: 3000 })
  } finally {
    savingOrder.value = false
  }
}

function startEditDeliveryCost() {
  deliveryCostInput.value = order.value.delivery_cost || 0
  editDeliveryCost.value = true
}

async function saveDeliveryCost() {
  savingOrder.value = true
  try {
    await updateOrder(orderId, { delivery_cost: deliveryCostInput.value })
    await reloadOrder()
    editDeliveryCost.value = false
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Стоимость доставки обновлена', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e.response?.data?.detail || 'Не удалось сохранить', life: 3000 })
  } finally {
    savingOrder.value = false
  }
}

function startEditComment() {
  commentInput.value = order.value.comment || ''
  editComment.value = true
}

async function saveComment() {
  savingOrder.value = true
  try {
    await updateOrder(orderId, { comment: commentInput.value })
    order.value.comment = commentInput.value
    editComment.value = false
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Комментарий обновлён', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e.response?.data?.detail || 'Не удалось сохранить', life: 3000 })
  } finally {
    savingOrder.value = false
  }
}

// --- Item editing ---

function startEditItem(item) {
  editingItem.value = item.id
  editItemQty.value = item.quantity
  editItemPrice.value = item.unit_price
}

async function saveItem(item) {
  savingItem.value = true
  try {
    await updateOrderItem(orderId, item.id, {
      quantity: editItemQty.value,
      unit_price: editItemPrice.value
    })
    editingItem.value = null
    await reloadOrder()
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Позиция обновлена', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e.response?.data?.detail || 'Не удалось сохранить', life: 3000 })
  } finally {
    savingItem.value = false
  }
}

async function removeItem(item) {
  if (!confirm(`Удалить "${item.product_name || 'позицию'}"?`)) return
  deletingItem.value = item.id
  try {
    await deleteOrderItem(orderId, item.id)
    await reloadOrder()
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Позиция удалена', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e.response?.data?.detail || 'Не удалось удалить', life: 3000 })
  } finally {
    deletingItem.value = null
  }
}

async function addItem() {
  if (!newItem.value.product) return
  addingItem.value = true
  try {
    await addOrderItem(orderId, {
      product_id: newItem.value.product.id,
      quantity: newItem.value.quantity,
      unit_price: newItem.value.price
    })
    showAddItem.value = false
    newItem.value = { product: null, quantity: 1, price: 0 }
    await reloadOrder()
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Товар добавлен', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e.response?.data?.detail || 'Не удалось добавить', life: 3000 })
  } finally {
    addingItem.value = false
  }
}
</script>
