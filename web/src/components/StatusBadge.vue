<template>
  <span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', colorClass]">
    {{ status }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ status: String })

const STATUS_COLORS = {
  'Новый':       'bg-blue-100 text-blue-700',
  'Подтверждён': 'bg-amber-100 text-amber-700',
  'В сборке':    'bg-purple-100 text-purple-700',
  'Отправлен':   'bg-indigo-100 text-indigo-700',
  'Доставлен':   'bg-green-100 text-green-700',
  'Отменён':     'bg-red-100 text-red-600',
}

const colorClass = computed(
  () => STATUS_COLORS[props.status] || 'bg-gray-100 text-gray-600'
)
</script>
