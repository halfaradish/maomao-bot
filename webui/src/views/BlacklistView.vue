<template>
  <div>
    <h3 class="page-title">黑名单</h3>

    <!-- Tab bar -->
    <div class="tab-bar">
      <button :class="{ active: activeTab === 'users' }" @click="switchTab('users')">用户黑名单</button>
      <button :class="{ active: activeTab === 'groups' }" @click="switchTab('groups')">群黑名单</button>
    </div>

    <!-- Add form -->
    <div class="inline-form">
      <input
        v-model="form.id"
        type="number"
        :placeholder="activeTab === 'users' ? 'QQ号' : '群号'"
        style="min-width: 160px"
      >
      <input
        v-model="form.reason"
        type="text"
        placeholder="拉黑原因（可选）"
        style="min-width: 200px"
      >
      <button @click="doAdd" :aria-busy="adding">添加</button>
    </div>

    <!-- Table -->
    <div class="table-wrap">
      <table v-if="items.length">
        <thead>
          <tr>
            <th>ID</th>
            <th>{{ activeTab === 'users' ? 'QQ号' : '群号' }}</th>
            <th>原因</th>
            <th>操作者</th>
            <th>添加时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>{{ item.id }}</td>
            <td>{{ activeTab === 'users' ? item.user_id : item.group_id }}</td>
            <td>{{ item.reason || '—' }}</td>
            <td>{{ item.created_by || '—' }}</td>
            <td>{{ fmt(item.created_at) }}</td>
            <td>
              <button class="secondary" @click="doDelete(item)">移除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">暂无数据</div>
    </div>

    <Pagination v-model:page="page" :total="total" :pageSize="PAGE_SIZE" @update:page="load" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { apiGet, apiPost, apiDelete } from '../api/client'
import { useConfirm } from '../composables/useConfirm'
import { useToast } from '../composables/useToast'
import Pagination from '../components/Pagination.vue'

const { showConfirm } = useConfirm()
const { showToast } = useToast()
const PAGE_SIZE = 10

const activeTab = ref('users')
const items = ref([])
const total = ref(0)
const page = ref(1)
const adding = ref(false)
const form = reactive({ id: '', reason: '' })

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleString('zh-CN') } catch { return String(ts) }
}

async function load(pageNum) {
  if (pageNum) page.value = pageNum
  try {
    const endpoint = `/permissions/blacklist/${activeTab.value}?page=${page.value}&size=${PAGE_SIZE}`
    const res = await apiGet(endpoint)
    items.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    showToast(e.message, 'error')
  }
}

function switchTab(tab) {
  activeTab.value = tab
  form.id = ''
  form.reason = ''
  page.value = 1
  load(1)
}

async function doAdd() {
  const idVal = parseInt(form.id)
  if (!idVal) {
    showToast('请输入有效的' + (activeTab.value === 'users' ? 'QQ号' : '群号'), 'error')
    return
  }
  adding.value = true
  try {
    const body = activeTab.value === 'users'
      ? { user_id: idVal, reason: form.reason }
      : { group_id: idVal, reason: form.reason }
    await apiPost(`/permissions/blacklist/${activeTab.value}`, body)
    showToast('已添加')
    form.id = ''
    form.reason = ''
    await load()
  } catch (e) {
    showToast(e.message, 'error')
  } finally {
    adding.value = false
  }
}

async function doDelete(item) {
  const label = activeTab.value === 'users' ? '用户' : '群'
  const id = activeTab.value === 'users' ? item.user_id : item.group_id
  try {
    await showConfirm('移出黑名单', `确定将此${label}移出黑名单吗？`)
  } catch {
    return
  }
  try {
    await apiDelete(`/permissions/blacklist/${activeTab.value}/${id}`)
    showToast('已移出')
    await load()
  } catch (e) {
    showToast(e.message || '移出失败', 'error')
  }
}

onMounted(load)
</script>
