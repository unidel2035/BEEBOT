<template>
  <div class="max-w-2xl">
    <div class="flex items-center gap-3 mb-6">
      <Button icon="pi pi-arrow-left" severity="secondary" text @click="$router.back()" />
      <h2 class="text-2xl font-bold text-gray-800">Новый заказ</h2>
    </div>

    <form @submit.prevent="handleSubmit" class="space-y-4">
      <!-- Данные клиента -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Клиент</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm text-gray-600 mb-1">ФИО <span class="text-red-400">*</span></label>
            <InputText v-model="form.client_name" class="w-full" required />
          </div>
          <div>
            <label class="block text-sm text-gray-600 mb-1">Телефон</label>
            <InputText v-model="form.phone" class="w-full" placeholder="+7 (___) ___-__-__" />
          </div>
        </div>
      </div>

      <!-- Доставка -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h3 class="font-semibold text-gray-700 mb-4">Доставка</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm text-gray-600 mb-1">Способ доставки</label>
            <Select
              v-model="form.delivery_method"
              :options="deliveryOptions"
              placeholder="Выберите способ"
              class="w-full"
              show-clear
            />
          </div>
          <div>
            <label class="block text-sm text-gray-600 mb-1">Стоимость доставки</label>
            <InputNumber
              v-model="form.delivery_cost"
              class="w-full"
              :min="0"
              mode="currency"
              currency="RUB"
              locale="ru-RU"
            />
          </div>
          <div class="sm:col-span-2">
            <label class="block text-sm text-gray-600 mb-1">Адрес доставки</label>
            <Textarea v-model="form.delivery_address" class="w-full" rows="2" auto-resize />
          </div>
        </div>
      </div>

      <!-- Позиции заказа -->
      <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold text-gray-700">Позиции заказа</h3>
          <Button
            label="Добавить"
            icon="pi pi-plus"
            size="small"
            severity="secondary"
            @click="addItem"
          />
        </div>

        <div v-if="form.items.length === 0" class="text-center py-6 text-gray-400 text-sm">
          Добавьте товары в заказ
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="(item, idx) in form.items"
            :key="idx"
            class="flex gap-3 items-end border-b border-gray-50 pb-3 last:border-0 last:pb-0"
          >
            <div class="flex-1">
              <label class="block text-xs text-gray-500 mb-1">Товар</label>
              <Select
                v-model="item.product_id"
                :options="products"
                option-label="name"
                option-value="id"
                placeholder="Выберите товар"
                class="w-full"
                @change="(e) => fillPrice(idx, e.value)"
              />
            </div>
            <div class="w-24">
              <label class="block text-xs text-gray-500 mb-1">Кол-во</label>
              <InputNumber v-model="item.quantity" :min="1" class="w-full" />
            </div>
            <div class="w-32">
              <label class="block text-xs text-gray-500 mb-1">Цена, ₽</label>
              <InputNumber v-model="item.unit_price" :min="0" class="w-full" />
            </div>
            <Button
              icon="pi pi-trash"
              severity="danger"
              text
              size="small"
              @click="removeItem(idx)"
            />
          </div>
        </div>

        <!-- Итого -->
        <div v-if="form.items.length > 0" class="mt-4 pt-3 border-t border-gray-100 flex justify-end gap-6 text-sm">
          <span class="text-gray-500">Товары: <strong>{{ formatMoney(itemsTotal) }}</strong></span>
          <span class="text-gray-500">Доставка: <strong>{{ formatMoney(form.delivery_cost || 0) }}</strong></span>
          <span class="text-gray-700 font-semibold">Итого: {{ formatMoney(grandTotal) }}</span>
        </div>
      </div>

      <!-- Кнопки -->
      <div class="flex gap-3 justify-end">
        <Button label="Отмена" severity="secondary" @click="$router.back()" />
        <Button
          type="submit"
          label="Создать заказ"
          icon="pi pi-check"
          :loading="loading"
          :disabled="form.items.length === 0 || !form.client_name"
        />
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import { getProducts, getReference, createOrder } from '../api.js'
import { formatMoney } from '../utils.js'

const router = useRouter()
const toast = useToast()
const loading = ref(false)
const products = ref([])
const deliveryOptions = ref([])

const form = ref({
  client_name: '',
  phone: '',
  delivery_method: null,
  delivery_address: '',
  delivery_cost: null,
  items: []
})

onMounted(async () => {
  const [prods, refData] = await Promise.all([getProducts(), getReference()])
  products.value = prods.map((p) => ({ id: p.id, name: p.name, price: p.price }))
  deliveryOptions.value = refData.delivery_methods
})

const itemsTotal = computed(() =>
  form.value.items.reduce((sum, i) => sum + (i.quantity || 0) * (i.unit_price || 0), 0)
)
const grandTotal = computed(() => itemsTotal.value + (form.value.delivery_cost || 0))

function addItem() {
  form.value.items.push({ product_id: null, quantity: 1, unit_price: 0 })
}

function removeItem(idx) {
  form.value.items.splice(idx, 1)
}

function fillPrice(idx, productId) {
  const prod = products.value.find((p) => p.id === productId)
  if (prod?.price) form.value.items[idx].unit_price = prod.price
}

async function handleSubmit() {
  loading.value = true
  try {
    const payload = {
      client_name: form.value.client_name,
      phone: form.value.phone || undefined,
      delivery_method: form.value.delivery_method || undefined,
      delivery_address: form.value.delivery_address || undefined,
      delivery_cost: form.value.delivery_cost || undefined,
      items: form.value.items
        .filter((i) => i.product_id)
        .map((i) => ({
          product_id: i.product_id,
          quantity: i.quantity,
          unit_price: i.unit_price
        }))
    }
    const order = await createOrder(payload)
    toast.add({ severity: 'success', summary: 'Заказ создан', detail: `Номер: ${order.number}`, life: 4000 })
    router.push(`/orders/${order.id}`)
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось создать заказ', life: 3000 })
  } finally {
    loading.value = false
  }
}
</script>
