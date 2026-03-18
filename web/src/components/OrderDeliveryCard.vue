<template>
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
    <h3 class="font-semibold text-gray-700 mb-4">Доставка</h3>
    <dl class="space-y-3 text-sm">
      <!-- Способ доставки -->
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
            <Button icon="pi pi-check" size="small" @click="saveField('delivery_method', methodInput, () => editMethod = false)" :loading="saving" />
            <Button icon="pi pi-times" size="small" severity="secondary" @click="editMethod = false" />
          </div>
        </dd>
      </div>

      <!-- Адрес -->
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
            <Button icon="pi pi-check" size="small" @click="saveField('delivery_address', addressInput, () => editAddress = false)" :loading="saving" />
            <Button icon="pi pi-times" size="small" severity="secondary" @click="editAddress = false" />
          </div>
        </dd>
      </div>

      <!-- Трек-номер -->
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
            <Button icon="pi pi-check" size="small" @click="$emit('save-tracking', trackingInput)" :loading="savingTracking" />
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
          <Button icon="pi pi-check" size="small" @click="saveField('comment', commentInput, () => editComment = false)" :loading="saving" />
          <Button icon="pi pi-times" size="small" severity="secondary" @click="editComment = false" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'

const props = defineProps({
  order: { type: Object, required: true },
  deliveryMethods: { type: Array, default: () => [] },
  savingTracking: { type: Boolean, default: false }
})

const emit = defineEmits(['update-field', 'save-tracking'])

const saving = ref(false)

const editMethod = ref(false)
const methodInput = ref('')

const editAddress = ref(false)
const addressInput = ref('')

const editTracking = ref(false)
const trackingInput = ref(props.order.tracking_number || '')

const editComment = ref(false)
const commentInput = ref('')

function startEditAddress() {
  addressInput.value = props.order.delivery_address || ''
  editAddress.value = true
}

function startEditComment() {
  commentInput.value = props.order.comment || ''
  editComment.value = true
}

async function saveField(field, value, onSuccess) {
  saving.value = true
  try {
    await emit('update-field', { [field]: value })
    if (onSuccess) onSuccess()
  } finally {
    saving.value = false
  }
}
</script>
