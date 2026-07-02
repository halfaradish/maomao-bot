<template>
  <div v-if="confirmState.show" class="confirm-overlay" @click.self="confirmState.reject">
    <div class="confirm-box">
      <h3>{{ confirmState.title }}</h3>
      <p>{{ confirmState.message }}</p>
      <div class="confirm-actions">
        <button class="secondary" @click="confirmState.reject">取消</button>
        <button class="contrast" @click="confirmState.resolve">确认删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useConfirm } from '../composables/useConfirm'

const { confirmState } = useConfirm()
</script>
