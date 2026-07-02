<template>
  <h3 class="page-title"><ShieldCheck :size="22" />权限组</h3>

  <button class="secondary" @click="showCreate = !showCreate">
    <template v-if="showCreate"><X :size="16" />取消</template>
    <template v-else><Plus :size="16" />创建权限组</template>
  </button>

  <div v-if="showCreate" class="inline-form">
    <input v-model="form.name" placeholder="名称（英文标识）" />
    <input v-model="form.display_name" placeholder="显示名" />
    <input v-model="form.description" placeholder="描述" />
    <button :disabled="creating" @click="doCreate"><Check :size="16" />提交</button>
    <button class="secondary" @click="resetForm"><X :size="16" />取消</button>
  </div>

  <div class="table-wrap">
    <table v-if="groups.length">
      <thead>
        <tr>
          <th>ID</th>
          <th>名称</th>
          <th>显示名</th>
          <th>描述</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="g in groups" :key="g.id">
          <td>{{ g.id }}</td>
          <td><code>{{ g.name }}</code></td>
          <td>{{ g.display_name || '—' }}</td>
          <td>{{ g.description || '—' }}</td>
          <td>{{ fmt(g.created_at) }}</td>
            <td>
            <router-link :to="`/groups/${g.id}`"><CaretRight :size="14" />详情</router-link>
            <button class="secondary" style="margin-left:0.5rem" @click="doDelete(g.id, g.name)"><Trash :size="14" />删除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="!groups.length && !loading" class="empty-state">暂无权限组</div>

  <Pagination v-model:page="page" :total="total" :pageSize="PAGE_SIZE" />
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { apiGet, apiPost, apiDelete } from '../api/client'
import { useConfirm } from '../composables/useConfirm'
import { useToast } from '../composables/useToast'
import Pagination from '../components/Pagination.vue'
import { PhShieldCheck as ShieldCheck, PhPlus as Plus, PhX as X, PhCheck as Check, PhCaretRight as CaretRight, PhTrash as Trash } from "@phosphor-icons/vue"

const PAGE_SIZE = 10

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleString('zh-CN') } catch { return String(ts) }
}

const { showConfirm } = useConfirm()
const { showToast } = useToast()

const groups = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

const showCreate = ref(false)
const creating = ref(false)
const form = reactive({ name: '', display_name: '', description: '' })

function resetForm() {
  form.name = ''
  form.display_name = ''
  form.description = ''
  showCreate.value = false
}

async function load() {
  loading.value = true
  try {
    const res = await apiGet(`/permissions/groups?page=${page.value}&size=${PAGE_SIZE}`)
    groups.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    showToast(e.message || '加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function doCreate() {
  if (!form.name.trim()) {
    showToast('请输入权限组名称', 'error')
    return
  }
  creating.value = true
  try {
    await apiPost('/permissions/groups', {
      name: form.name.trim(),
      display_name: form.display_name.trim(),
      description: form.description.trim(),
    })
    showToast('创建成功')
    resetForm()
    load()
  } catch (e) {
    showToast(e.message || '创建失败', 'error')
  } finally {
    creating.value = false
  }
}

async function doDelete(id, name) {
  try {
    await showConfirm('删除权限组', `确定删除权限组「${name}」吗？此操作不可撤销。`)
  } catch {
    return
  }
  try {
    await apiDelete(`/permissions/groups/${id}`)
    showToast('已删除')
    load()
  } catch (e) {
    showToast(e.message || '删除失败', 'error')
  }
}

watch(page, () => {
  load()
})

onMounted(load)
</script>
