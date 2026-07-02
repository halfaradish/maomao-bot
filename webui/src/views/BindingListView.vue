<template>
  <h3 class="page-title">群绑定</h3>

  <div class="inline-form">
    <input v-model="form.qq_group_id" type="number" placeholder="QQ群号" />
    <select v-model="form.permission_group_id">
      <option value="" disabled>选择权限组</option>
      <option v-for="g in groupOptions" :key="g.id" :value="g.id">
        {{ g.display_name || g.name }}
      </option>
    </select>
    <button :disabled="creating" @click="doCreate">绑定</button>
  </div>

  <div class="table-wrap">
    <table v-if="bindings.length">
      <thead>
        <tr>
          <th>ID</th>
          <th>QQ群号</th>
          <th>权限组</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in bindings" :key="b.id">
          <td>{{ b.id }}</td>
          <td>{{ b.qq_group_id }}</td>
          <td>{{ groupName(b.permission_group_id) }}</td>
          <td>{{ fmt(b.created_at) }}</td>
          <td>
            <button class="secondary" @click="doDelete(b.id)">解除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="!bindings.length && !loading" class="empty-state">暂无绑定</div>

  <Pagination v-model:page="page" :total="total" :pageSize="PAGE_SIZE" />
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { apiGet, apiPost, apiDelete } from '../api/client'
import { useConfirm } from '../composables/useConfirm'
import { useToast } from '../composables/useToast'
import Pagination from '../components/Pagination.vue'

const PAGE_SIZE = 10

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleString('zh-CN') } catch { return String(ts) }
}

const { showConfirm } = useConfirm()
const { showToast } = useToast()

const bindings = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

const groupOptions = ref([])
const groupMap = ref({})

const form = reactive({ qq_group_id: '', permission_group_id: '' })
const creating = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await apiGet(`/permissions/bindings?page=${page.value}&size=${PAGE_SIZE}`)
    if (Array.isArray(res.data)) {
      bindings.value = res.data
      total.value = res.data.length
    } else {
      bindings.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (e) {
    showToast(e.message || '加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function loadGroups() {
  try {
    const res = await apiGet('/permissions/groups?page=1&size=200')
    const items = res.data.items || []
    groupOptions.value = items
    const map = {}
    items.forEach(g => { map[g.id] = g.display_name || g.name })
    groupMap.value = map
  } catch (e) {
    showToast(e.message || '加载权限组列表失败', 'error')
  }
}

function groupName(pgId) {
  return groupMap.value[pgId] || `ID=${pgId}`
}

async function doCreate() {
  if (!form.qq_group_id || !form.permission_group_id) {
    showToast('请填写QQ群号并选择权限组', 'error')
    return
  }
  creating.value = true
  try {
    await apiPost('/permissions/bindings', {
      qq_group_id: parseInt(form.qq_group_id, 10),
      permission_group_id: parseInt(form.permission_group_id, 10),
    })
    showToast('绑定成功')
    form.qq_group_id = ''
    form.permission_group_id = ''
    load()
  } catch (e) {
    showToast(e.message || '绑定失败', 'error')
  } finally {
    creating.value = false
  }
}

async function doDelete(id) {
  try {
    await showConfirm('解除绑定', '确定解除该群绑定吗？')
  } catch {
    return
  }
  try {
    await apiDelete(`/permissions/bindings/${id}`)
    showToast('已解除')
    load()
  } catch (e) {
    showToast(e.message || '解除失败', 'error')
  }
}

watch(page, () => {
  load()
})

onMounted(() => {
  load()
  loadGroups()
})
</script>
