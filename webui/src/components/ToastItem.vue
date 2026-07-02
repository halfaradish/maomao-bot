<template>
  <div v-if="toastState.show" :class="['toast', toastState.type]">
    {{ toastState.message }}
  </div>
</template>

<script setup>
import { useToast } from '../composables/useToast'

const { toastState } = useToast()
</script>
