<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-800">Товары</h2>
      <Button label="Добавить товар" icon="pi pi-plus" size="small" @click="openCreateDialog" />
    </div>

    <!-- Таблица товаров -->
    <div class="bg-white rounded-xl border border-gray-100 shadow-sm">
      <DataTable
        :value="products"
        :loading="loading"
        paginator
        :rows="20"
        row-hover
        class="text-sm"
      >
        <template #header>
          <div class="flex gap-3 p-1">
            <ToggleButton
              v-model="showAll"
              on-label="Все товары"
              off-label="Только в наличии"
              on-icon="pi pi-eye"
              off-icon="pi pi-eye-slash"
              @change="loadProducts"
            />
          </div>
        </template>
        <template #empty>
          <div class="text-center py-8 text-gray-400">Товаров нет</div>
        </template>

        <Column field="name" header="Название" sortable />
        <Column field="category" header="Категория" sortable>
          <template #body="{ data }">{{ data.category || '—' }}</template>
        </Column>
        <Column field="price" header="Цена" sortable>
          <template #body="{ data }">{{ formatMoney(data.price) }}</template>
        </Column>
        <Column field="weight" header="Вес, г">
          <template #body="{ data }">{{ data.weight ? `${data.weight} г` : '—' }}</template>
        </Column>
        <Column field="in_stock" header="В наличии" style="width:110px">
          <template #body="{ data }">
            <Tag
              :value="data.in_stock ? 'Да' : 'Нет'"
              :severity="data.in_stock ? 'success' : 'danger'"
            />
          </template>
        </Column>
        <Column header="" style="width:100px">
          <template #body="{ data }">
            <div class="flex gap-1">
              <Button
                icon="pi pi-pencil"
                severity="secondary"
                text
                size="small"
                @click.stop="openEditDialog(data)"
              />
              <Button
                icon="pi pi-trash"
                severity="danger"
                text
                size="small"
                @click.stop="confirmDelete(data)"
              />
            </div>
          </template>
        </Column>
      </DataTable>
    </div>

    <!-- Диалог создания/редактирования -->
    <Dialog
      v-model:visible="dialogVisible"
      :header="editingProduct ? 'Редактировать товар' : 'Новый товар'"
      :style="{ width: '460px' }"
      modal
    >
      <form @submit.prevent="handleSaveProduct" class="space-y-4 mt-2">
        <div>
          <label class="block text-sm text-gray-600 mb-1">Название <span class="text-red-400">*</span></label>
          <InputText v-model="productForm.name" class="w-full" required />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm text-gray-600 mb-1">Категория</label>
            <Select
              v-model="productForm.category"
              :options="categories"
              placeholder="Выберите"
              class="w-full"
              show-clear
            />
          </div>
          <div>
            <label class="block text-sm text-gray-600 mb-1">Цена, ₽</label>
            <InputNumber v-model="productForm.price" :min="0" class="w-full" />
          </div>
          <div>
            <label class="block text-sm text-gray-600 mb-1">Вес, г</label>
            <InputNumber v-model="productForm.weight" :min="0" class="w-full" />
          </div>
          <div>
            <label class="block text-sm text-gray-600 mb-1">Артикул UDS</label>
            <InputText v-model="productForm.sku_uds" class="w-full" />
          </div>
        </div>
        <div>
          <label class="block text-sm text-gray-600 mb-1">Описание</label>
          <Textarea v-model="productForm.description" class="w-full" rows="3" auto-resize />
        </div>
        <div class="flex items-center gap-2">
          <Checkbox v-model="productForm.in_stock" binary input-id="inStockCheck" />
          <label for="inStockCheck" class="text-sm text-gray-600">В наличии</label>
        </div>

        <div class="flex gap-3 justify-end pt-2">
          <Button label="Отмена" severity="secondary" type="button" @click="dialogVisible = false" />
          <Button
            :label="editingProduct ? 'Сохранить' : 'Создать'"
            type="submit"
            :loading="savingProduct"
          />
        </div>
      </form>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import Checkbox from 'primevue/checkbox'
import ToggleButton from 'primevue/togglebutton'
import Tag from 'primevue/tag'
import { getProducts, createProduct, updateProduct, deleteProduct } from '../api.js'
import { formatMoney } from '../utils.js'

const toast = useToast()
const confirm = useConfirm()
const loading = ref(true)
const products = ref([])
const showAll = ref(true)

// Диалог
const dialogVisible = ref(false)
const editingProduct = ref(null)
const savingProduct = ref(false)
const productForm = ref(emptyForm())
const categories = ['Продукты пчеловодства', 'Настойки', 'Программы здоровья']

function emptyForm() {
  return { name: '', category: null, price: null, weight: null, description: '', in_stock: true, sku_uds: '' }
}

onMounted(() => loadProducts())

async function loadProducts() {
  loading.value = true
  try {
    products.value = await getProducts(!showAll.value)
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingProduct.value = null
  productForm.value = emptyForm()
  dialogVisible.value = true
}

function openEditDialog(product) {
  editingProduct.value = product
  productForm.value = {
    name: product.name,
    category: product.category,
    price: product.price,
    weight: product.weight,
    description: product.description || '',
    in_stock: product.in_stock !== false,
    sku_uds: product.sku_uds || ''
  }
  dialogVisible.value = true
}

async function handleSaveProduct() {
  savingProduct.value = true
  try {
    if (editingProduct.value) {
      await updateProduct(editingProduct.value.id, productForm.value)
      toast.add({ severity: 'success', summary: 'Сохранено', detail: 'Товар обновлён', life: 3000 })
    } else {
      await createProduct(productForm.value)
      toast.add({ severity: 'success', summary: 'Создан', detail: 'Товар добавлен в каталог', life: 3000 })
    }
    dialogVisible.value = false
    await loadProducts()
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось сохранить товар', life: 3000 })
  } finally {
    savingProduct.value = false
  }
}

function confirmDelete(product) {
  confirm.require({
    message: `Снять с продажи «${product.name}»?`,
    header: 'Подтверждение',
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: 'Снять',
    rejectLabel: 'Отмена',
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        await deleteProduct(product.id)
        toast.add({ severity: 'success', summary: 'Готово', detail: 'Товар снят с продажи', life: 3000 })
        await loadProducts()
      } catch {
        toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось снять товар', life: 3000 })
      }
    }
  })
}
</script>
