<template>
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
    <h3 class="font-semibold text-gray-700 mb-4">Статус заказа</h3>
    <div class="flex gap-2 flex-wrap">
      <Button
        v-for="s in statusOptions"
        :key="s"
        :label="s"
        :severity="currentStatus === s ? 'warning' : 'secondary'"
        size="small"
        :outlined="currentStatus !== s"
        :loading="changingStatus === s"
        @click="changeStatus(s)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'

const props = defineProps({
  currentStatus: { type: String, required: true },
  statusOptions: { type: Array, default: () => [] }
})

const emit = defineEmits(['change-status'])

const changingStatus = ref('')

async function changeStatus(newStatus) {
  if (newStatus === props.currentStatus) return
  changingStatus.value = newStatus
  try {
    await emit('change-status', newStatus)
  } finally {
    changingStatus.value = ''
  }
}
</script>
