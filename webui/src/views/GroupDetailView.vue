<template>
  <div class="breadcrumb">
    <CaretLeft :size="14" /><router-link to="/groups">权限组列表</router-link>
    <span style="color:var(--pico-muted-color)">/</span>
    <span>{{ group?.name }}</span>
  </div>

  <div v-if="group" class="status-card">
    <h3 style="display:flex;align-items:center;gap:0.5rem"><ShieldCheck :size="20" />{{ group.display_name || group.name }}</h3>
    <p v-if="group.name"><code>{{ group.name }}</code></p>
    <p v-if="group.description" style="color:var(--pico-muted-color)">{{ group.description }}</p>
  </div>

  <!-- Members -->
  <h4 class="section-title"><UsersThree :size="16" />成员</h4>
  <div class="inline-form">
    <input v-model="newMemberIds" placeholder="QQ号（多个用逗号分隔）" />
    <button :disabled="addingMember" @click="addMembers"><Plus :size="16" />添加</button>
  </div>
  <div class="table-wrap">
    <table v-if="members.length">
      <thead>
        <tr>
          <th>QQ号</th>
          <th>添加时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in members" :key="m.user_id">
          <td>{{ m.user_id }}</td>
          <td>{{ fmt(m.created_at) }}</td>
          <td>
            <button class="secondary" @click="removeMember(m.user_id)"><X :size="14" />移除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <div v-if="!members.length" class="empty-state">暂无成员</div>

  <!-- Perms -->
  <h4 class="section-title"><Lock :size="16" />权限点</h4>
  <div class="inline-form">
    <input v-model="newPermKeys" placeholder="插件名:操作" />
    <button :disabled="addingPerm" @click="addPerms"><Plus :size="16" />添加</button>
  </div>
  <p style="font-size:0.78rem;color:var(--pico-muted-color);margin:-0.5rem 0 1rem 0">格式: <code>插件名:操作</code>，如 <code>permission_manager:manage</code>（多个用逗号分隔）</p>
  <div class="table-wrap">
    <table v-if="perms.length">
      <thead>
        <tr>
          <th>权限标识</th>
          <th>添加时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in perms" :key="p.perm_key">
          <td><code>{{ p.perm_key }}</code></td>
          <td>{{ fmt(p.created_at) }}</td>
          <td>
            <button class="secondary" @click="removePerm(p.perm_key)"><X :size="14" />移除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <div v-if="!perms.length" class="empty-state">暂无权限点</div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { apiGet, apiPost, apiDelete } from '../api/client'
import { useConfirm } from '../composables/useConfirm'
import { useToast } from '../composables/useToast'
import { PhShieldCheck as ShieldCheck, PhCaretLeft as CaretLeft, PhUsersThree as UsersThree, PhLock as Lock, PhPlus as Plus, PhX as X } from "@phosphor-icons/vue"

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleString('zh-CN') } catch { return String(ts) }
}

const { showConfirm } = useConfirm()
const { showToast } = useToast()
const route = useRoute()

const group = ref(null)
const members = ref([])
const perms = ref([])

const newMemberIds = ref('')
const newPermKeys = ref('')
const addingMember = ref(false)
const addingPerm = ref(false)

async function load() {
  try {
    const res = await apiGet(`/permissions/groups/${route.params.id}`)
    group.value = res.data
    members.value = res.data.members || []
    perms.value = res.data.permissions || []
  } catch (e) {
    showToast(e.message || '加载失败', 'error')
  }
}

async function addMembers() {
  const raw = newMemberIds.value
  const parts = raw.split(/[,，]/).map(s => s.trim()).filter(Boolean)
  const ids = parts.map(Number).filter(n => !isNaN(n) && n > 0)
  const skipped = parts.length - ids.length

  if (!ids.length) {
    showToast('请输入有效的QQ号', 'error')
    return
  }

  addingMember.value = true
  try {
    await apiPost(`/permissions/groups/${route.params.id}/members`, { user_ids: ids })
    const msg = `已添加 ${ids.length} 名成员`
    showToast(skipped ? `${msg}（${skipped} 个无效号码已跳过）` : msg)
    newMemberIds.value = ''
    load()
  } catch (e) {
    showToast(e.message || '添加失败', 'error')
  } finally {
    addingMember.value = false
  }
}

async function removeMember(userId) {
  try {
    await showConfirm('移除成员', `确定将 QQ ${userId} 移出该权限组吗？`)
  } catch {
    return
  }
  try {
    await apiDelete(`/permissions/groups/${route.params.id}/members/${userId}`)
    showToast('已移除')
    load()
  } catch (e) {
    showToast(e.message || '移除失败', 'error')
  }
}

async function addPerms() {
  const raw = newPermKeys.value
  const keys = raw.split(/[,，]/).map(s => s.trim()).filter(Boolean)

  if (!keys.length) {
    showToast('请输入权限标识', 'error')
    return
  }

  addingPerm.value = true
  try {
    await apiPost(`/permissions/groups/${route.params.id}/perms`, { perm_keys: keys })
    showToast(`已添加 ${keys.length} 个权限点`)
    newPermKeys.value = ''
    load()
  } catch (e) {
    showToast(e.message || '添加失败', 'error')
  } finally {
    addingPerm.value = false
  }
}

async function removePerm(permKey) {
  try {
    await showConfirm('移除权限点', `确定移除权限点「${permKey}」吗？`)
  } catch {
    return
  }
  try {
    await apiDelete(`/permissions/groups/${route.params.id}/perms/${encodeURIComponent(permKey)}`)
    showToast('已移除')
    load()
  } catch (e) {
    showToast(e.message || '移除失败', 'error')
  }
}

onMounted(load)
</script>
