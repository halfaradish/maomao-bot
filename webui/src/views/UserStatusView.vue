<template>
  <div class="page-container">
    <h3 class="page-title"><MagnifyingGlass :size="22" />用户权限状态</h3>

    <form @submit.prevent="doQuery" class="inline-form">
      <input
        type="text"
        v-model="queryQQ"
        placeholder="输入 QQ 号"
        required
        autofocus
        style="min-width:200px"
      />
      <button type="submit" :aria-busy="loading"><MagnifyingGlass :size="16" />查询</button>
    </form>

    <div v-if="status" class="status-results">
      <!-- 基本信息 -->
      <h4 class="section-title"><UserCircle :size="16" />基本信息</h4>
      <article>
        <p><strong>用户 ID：</strong>{{ status.user_id }}</p>
        <p>
          <strong>超级管理员：</strong>
          <span v-if="status.is_superuser" class="tag-yes"><Check :size="12" />是</span>
          <span v-else class="tag-no"><X :size="12" />否</span>
        </p>
      </article>

      <!-- 黑名单状态 -->
      <h4 class="section-title"><Prohibit :size="16" />黑名单状态</h4>
      <article v-if="status.blacklisted" style="border-color: var(--pico-danger-border)">
        <p><strong>原因：</strong>{{ status.blacklisted.reason }}</p>
        <p><strong>拉黑者：</strong>{{ status.blacklisted.created_by }}</p>
        <p><strong>时间：</strong>{{ fmt(status.blacklisted.created_at) }}</p>
      </article>
      <article v-else>
        <p style="color: var(--pico-muted-color)">未拉黑</p>
      </article>

      <!-- 白名单状态 -->
      <h4 class="section-title"><CheckCircle :size="16" />白名单状态</h4>
      <article v-if="status.whitelisted" style="border-color: #238636">
        <p><strong>原因：</strong>{{ status.whitelisted.reason }}</p>
        <p><strong>加白者：</strong>{{ status.whitelisted.created_by }}</p>
        <p><strong>时间：</strong>{{ fmt(status.whitelisted.created_at) }}</p>
      </article>
      <article v-else>
        <p style="color: var(--pico-muted-color)">未加白</p>
      </article>

      <!-- 所属权限组 -->
      <h4 class="section-title"><ShieldCheck :size="16" />所属权限组 ({{ status.permission_groups.length }})</h4>
      <template v-if="status.permission_groups.length">
        <article v-for="g in status.permission_groups" :key="g.id">
          <h5>{{ g.display_name || g.name }}</h5>
          <p v-if="g.description">{{ g.description }}</p>
          <div class="perms-list">
            <code v-for="perm in g.perms" :key="perm">{{ perm }}</code>
          </div>
        </article>
      </template>
      <div v-else class="empty-state">未加入任何权限组</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { apiGet } from '../api/client'
import { useToast } from '../composables/useToast'
import Pagination from '../components/Pagination.vue'
import { PhMagnifyingGlass as MagnifyingGlass, PhUserCircle as UserCircle, PhCheck as Check, PhX as X, PhProhibit as Prohibit, PhCheckCircle as CheckCircle, PhShieldCheck as ShieldCheck } from "@phosphor-icons/vue"

const { showToast } = useToast()
const PAGE_SIZE = 10

const queryQQ = ref('')
const status = ref(null)
const loading = ref(false)

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleString('zh-CN') } catch { return String(ts) }
}

async function doQuery() {
  if (!queryQQ.value) return
  loading.value = true
  status.value = null
  try {
    const res = await apiGet(`/permissions/users/${queryQQ.value}/status`)
    status.value = res.data
  } catch (e) {
    showToast('查询用户状态失败', 'error')
  } finally {
    loading.value = false
  }
}
</script>
