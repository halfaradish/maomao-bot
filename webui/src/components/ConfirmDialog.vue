<template>
  <div v-if="confirmState.show" class="confirm-overlay" @click.self="confirmState.reject">
    <div class="confirm-box">
      <h3><WarningCircle :size="20" />{{ confirmState.title }}</h3>
      <p>{{ confirmState.message }}</p>
      <div class="confirm-actions">
        <button class="secondary" @click="confirmState.reject"><X :size="14" />取消</button>
        <button class="contrast" @click="confirmState.resolve"><Check :size="14" />确认</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useConfirm } from '../composables/useConfirm'
import { PhWarningCircle as WarningCircle, PhX as X, PhCheck as Check } from "@phosphor-icons/vue"

const { confirmState } = useConfirm()
</script>
