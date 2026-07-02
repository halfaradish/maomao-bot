<template>
  <div class="pagination" v-if="total > pageSize">
    <button class="secondary" :disabled="!hasPrev" @click="$emit('update:page', page - 1)">
      <CaretLeft :size="14" />上一页
    </button>
    <template v-for="p in pageNumbers" :key="p">
      <button v-if="p === '...'" class="secondary" disabled>...</button>
      <button
        v-else
        :class="p === page ? '' : 'secondary'"
        @click="$emit('update:page', p)"
      >
        {{ p }}
      </button>
    </template>
    <button class="secondary" :disabled="!hasNext" @click="$emit('update:page', page + 1)">
      下一页<CaretRight :size="14" />
    </button>
    <span class="page-info"><ListDashes :size="14" />共 {{ total }} 条，第 {{ page }}/{{ totalPages }} 页</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { PhCaretLeft as CaretLeft, PhCaretRight as CaretRight, PhListDashes as ListDashes } from "@phosphor-icons/vue"

const props = defineProps({
  page: { type: Number, required: true },
  total: { type: Number, required: true },
  pageSize: { type: Number, default: 10 },
})

defineEmits(['update:page'])

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const hasPrev = computed(() => props.page > 1)
const hasNext = computed(() => props.page < totalPages.value)

const pageNumbers = computed(() => {
  const tp = totalPages.value
  const p = props.page
  const pages = []

  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
    return pages
  }

  pages.push(1)
  if (p > 3) pages.push('...')

  for (let i = Math.max(2, p - 1); i <= Math.min(tp - 1, p + 1); i++) {
    pages.push(i)
  }

  if (p < tp - 2) pages.push('...')
  pages.push(tp)

  return pages
})
</script>
