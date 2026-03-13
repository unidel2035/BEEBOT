<template>
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-4">
    <div :class="['w-11 h-11 rounded-lg flex items-center justify-center flex-shrink-0', bgColor]">
      <i :class="['pi', icon, 'text-xl', iconColor]" />
    </div>
    <div>
      <div class="text-2xl font-bold text-gray-800">{{ value }}</div>
      <div class="text-xs text-gray-500 mt-0.5">{{ label }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  icon: String,
  iconColor: String,
  bgColor: String,
  label: String,
  value: [String, Number]
})
</script>
