<template>
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
            <Button icon="pi pi-check" size="small" @click="saveDeliveryCost" :loading="saving" />
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
</template>

<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import { formatDate, formatMoney } from '../utils.js'

const props = defineProps({
  order: { type: Object, required: true }
})

const emit = defineEmits(['update-field'])

const saving = ref(false)
const editDeliveryCost = ref(false)
const deliveryCostInput = ref(0)

function startEditDeliveryCost() {
  deliveryCostInput.value = props.order.delivery_cost || 0
  editDeliveryCost.value = true
}

async function saveDeliveryCost() {
  saving.value = true
  try {
    await emit('update-field', { delivery_cost: deliveryCostInput.value })
    editDeliveryCost.value = false
  } finally {
    saving.value = false
  }
}
</script>
