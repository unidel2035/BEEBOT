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
        <OrderDetailsCard :order="order" @update-field="handleUpdateField" />
        <OrderDeliveryCard
          :order="order"
          :delivery-methods="deliveryMethods"
          :saving-tracking="savingTracking"
          @update-field="handleUpdateField"
          @save-tracking="handleSaveTracking"
        />
      </div>

      <OrderStatusBar
        :current-status="order.status"
        :status-options="statusOptions"
        @change-status="handleChangeStatus"
      />

      <OrderItemsTable
        :items="order.items"
        :products="products"
        :editable="order.editable"
        :deleting-item="deletingItem"
        @save-item="handleSaveItem"
        @remove-item="handleRemoveItem"
        @add-item="handleAddItem"
      />
    </div>

    <div v-else class="text-center py-16 text-gray-400">
      <i class="pi pi-exclamation-triangle text-4xl mb-3 block" />
      Заказ не найден
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Skeleton from 'primevue/skeleton'
import {
  getOrder, updateOrderStatus, updateOrderTracking, updateOrder,
  addOrderItem, updateOrderItem, deleteOrderItem,
  getReference, getProducts
} from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'
import OrderDetailsCard from '../components/OrderDetailsCard.vue'
import OrderDeliveryCard from '../components/OrderDeliveryCard.vue'
import OrderStatusBar from '../components/OrderStatusBar.vue'
import OrderItemsTable from '../components/OrderItemsTable.vue'

const route = useRoute()
const toast = useToast()
const orderId = route.params.id

const loading = ref(true)
const order = ref(null)
const statusOptions = ref([])
const deliveryMethods = ref([])
const products = ref([])
const savingTracking = ref(false)
const deletingItem = ref(null)

onMounted(async () => {
  const [orderData, refData, productsData] = await Promise.all([
    getOrder(orderId),
    getReference(),
    getProducts()
  ])
  order.value = orderData
  statusOptions.value = refData.order_statuses
  deliveryMethods.value = refData.delivery_methods
  products.value = productsData
  loading.value = false
})

async function reloadOrder() {
  order.value = await getOrder(orderId)
}

function showSuccess(msg) {
  toast.add({ severity: 'success', summary: 'Готово', detail: msg, life: 3000 })
}

function showError(e, fallback = 'Не удалось сохранить') {
  toast.add({ severity: 'error', summary: 'Ошибка', detail: e?.response?.data?.detail || fallback, life: 3000 })
}

async function handleChangeStatus(newStatus) {
  try {
    await updateOrderStatus(orderId, newStatus)
    order.value.status = newStatus
    order.value.editable = ['Новый', 'Подтверждён', 'В сборке'].includes(newStatus)
    showSuccess(`Статус изменён на "${newStatus}"`)
  } catch (e) {
    showError(e, 'Не удалось изменить статус')
  }
}

async function handleSaveTracking(trackingNumber) {
  savingTracking.value = true
  try {
    await updateOrderTracking(orderId, trackingNumber)
    order.value.tracking_number = trackingNumber
    showSuccess('Трек-номер обновлён')
  } catch (e) {
    showError(e)
  } finally {
    savingTracking.value = false
  }
}

async function handleUpdateField(fields) {
  try {
    await updateOrder(orderId, fields)
    await reloadOrder()
    const fieldName = Object.keys(fields)[0]
    const labels = {
      delivery_cost: 'Стоимость доставки обновлена',
      delivery_address: 'Адрес обновлён',
      delivery_method: 'Способ доставки обновлён',
      comment: 'Комментарий обновлён',
    }
    showSuccess(labels[fieldName] || 'Сохранено')
  } catch (e) {
    showError(e)
  }
}

async function handleSaveItem({ itemId, quantity, unit_price }) {
  try {
    await updateOrderItem(orderId, itemId, { quantity, unit_price })
    await reloadOrder()
    showSuccess('Позиция обновлена')
  } catch (e) {
    showError(e)
  }
}

async function handleRemoveItem(item) {
  if (!confirm(`Удалить "${item.product_name || 'позицию'}"?`)) return
  deletingItem.value = item.id
  try {
    await deleteOrderItem(orderId, item.id)
    await reloadOrder()
    showSuccess('Позиция удалена')
  } catch (e) {
    showError(e, 'Не удалось удалить')
  } finally {
    deletingItem.value = null
  }
}

async function handleAddItem(itemData) {
  try {
    await addOrderItem(orderId, itemData)
    await reloadOrder()
    showSuccess('Товар добавлен')
  } catch (e) {
    showError(e, 'Не удалось добавить')
  }
}
</script>
