<template>
  <div v-if="toastState.show" :class="['toast', toastState.type]">
    <CheckCircle v-if="!toastState.type" :size="16" weight="fill" />
    <WarningCircle v-else :size="16" weight="fill" />
    {{ toastState.message }}
  </div>
</template>

<script setup>
import { useToast } from '../composables/useToast'
import { PhCheckCircle as CheckCircle, PhWarningCircle as WarningCircle } from "@phosphor-icons/vue"

const { toastState } = useToast()
</script>
