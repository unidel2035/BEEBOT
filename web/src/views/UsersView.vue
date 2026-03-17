<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-bold text-gray-800">Пользователи</h2>
      <Button label="Добавить" icon="pi pi-plus" @click="openCreate" />
    </div>

    <DataTable :value="users" :loading="loading" stripedRows class="rounded-xl overflow-hidden shadow-sm">
      <Column field="username" header="Логин" sortable />
      <Column field="display_name" header="Имя" sortable />
      <Column field="role" header="Роль" sortable>
        <template #body="{ data }">
          <Tag :value="roleLabel(data.role)" :severity="data.role === 'admin' ? 'primary' : 'info'" />
        </template>
      </Column>
      <Column field="active" header="Статус">
        <template #body="{ data }">
          <Tag :value="data.active ? 'Активен' : 'Отключён'" :severity="data.active ? 'success' : 'danger'" />
        </template>
      </Column>
      <Column header="Действия" style="width: 180px">
        <template #body="{ data }">
          <div class="flex gap-2">
            <Button icon="pi pi-pencil" severity="secondary" size="small" @click="openEdit(data)" />
            <Button
              v-if="data.active"
              icon="pi pi-ban"
              severity="danger"
              size="small"
              @click="confirmDeactivate(data)"
            />
            <Button
              v-else
              icon="pi pi-check"
              severity="success"
              size="small"
              @click="activateUser(data)"
            />
          </div>
        </template>
      </Column>
    </DataTable>

    <!-- Диалог создания/редактирования -->
    <Dialog
      v-model:visible="dialogVisible"
      :header="editing ? 'Редактировать пользователя' : 'Новый пользователь'"
      :style="{ width: '420px' }"
      modal
    >
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Логин</label>
          <InputText v-model="form.username" class="w-full" :disabled="editing" placeholder="login" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Пароль {{ editing ? '(оставьте пустым)' : '' }}
          </label>
          <InputText v-model="form.password" type="password" class="w-full" placeholder="********" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Отображаемое имя</label>
          <InputText v-model="form.display_name" class="w-full" placeholder="Иван" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Роль</label>
          <Select v-model="form.role" :options="roleOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3 justify-end">
          <Button label="Отмена" severity="secondary" @click="dialogVisible = false" />
          <Button :label="editing ? 'Сохранить' : 'Создать'" @click="save" :loading="saving" />
        </div>
      </template>
    </Dialog>

    <!-- Подтверждение деактивации -->
    <Dialog v-model:visible="deactivateVisible" header="Подтверждение" :style="{ width: '360px' }" modal>
      <p>Деактивировать пользователя <strong>{{ deactivateTarget?.username }}</strong>?</p>
      <p class="text-sm text-gray-500 mt-1">Он не сможет входить в систему.</p>
      <template #footer>
        <div class="flex gap-3 justify-end">
          <Button label="Отмена" severity="secondary" @click="deactivateVisible = false" />
          <Button label="Деактивировать" severity="danger" @click="doDeactivate" :loading="saving" />
        </div>
      </template>
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
import Tag from 'primevue/tag'
import { getUsers, createUser, updateUser, deleteUser } from '../api.js'

const toast = useToast()
const loading = ref(false)
const saving = ref(false)
const users = ref([])

const dialogVisible = ref(false)
const editing = ref(false)
const editingId = ref(null)
const form = ref({ username: '', password: '', display_name: '', role: 'warehouse' })

const deactivateVisible = ref(false)
const deactivateTarget = ref(null)

const roleOptions = [
  { label: 'Администратор', value: 'admin' },
  { label: 'Склад', value: 'warehouse' },
]

onMounted(loadUsers)

async function loadUsers() {
  loading.value = true
  try {
    users.value = await getUsers()
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить пользователей', life: 3000 })
  } finally {
    loading.value = false
  }
}

function roleLabel(role) {
  return role === 'admin' ? 'Администратор' : role === 'warehouse' ? 'Склад' : role
}

function openCreate() {
  editing.value = false
  editingId.value = null
  form.value = { username: '', password: '', display_name: '', role: 'warehouse' }
  dialogVisible.value = true
}

function openEdit(user) {
  editing.value = true
  editingId.value = user.id
  form.value = {
    username: user.username,
    password: '',
    display_name: user.display_name,
    role: user.role,
  }
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      const body = {
        role: form.value.role,
        display_name: form.value.display_name,
      }
      if (form.value.password) body.password = form.value.password
      await updateUser(editingId.value, body)
      toast.add({ severity: 'success', summary: 'Сохранено', life: 2000 })
    } else {
      if (!form.value.username || !form.value.password) {
        toast.add({ severity: 'warn', summary: 'Заполните логин и пароль', life: 3000 })
        return
      }
      await createUser(form.value)
      toast.add({ severity: 'success', summary: 'Пользователь создан', life: 2000 })
    }
    dialogVisible.value = false
    await loadUsers()
  } catch (e) {
    const detail = e.response?.data?.detail || 'Ошибка сохранения'
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 3000 })
  } finally {
    saving.value = false
  }
}

function confirmDeactivate(user) {
  deactivateTarget.value = user
  deactivateVisible.value = true
}

async function doDeactivate() {
  if (!deactivateTarget.value) return
  saving.value = true
  try {
    await deleteUser(deactivateTarget.value.id)
    toast.add({ severity: 'info', summary: 'Пользователь деактивирован', life: 2000 })
    deactivateVisible.value = false
    await loadUsers()
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка деактивации', life: 3000 })
  } finally {
    saving.value = false
  }
}

async function activateUser(user) {
  saving.value = true
  try {
    await updateUser(user.id, { active: true })
    toast.add({ severity: 'success', summary: 'Пользователь активирован', life: 2000 })
    await loadUsers()
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка активации', life: 3000 })
  } finally {
    saving.value = false
  }
}
</script>
