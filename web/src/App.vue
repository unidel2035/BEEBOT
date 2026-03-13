<template>
  <Toast />
  <ConfirmDialog />
  <RouterView />
</template>

<script setup>
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
import { RouterView } from 'vue-router'
</script>
