<template>
  <ToastItem />
  <ConfirmDialog />

  <header v-if="route.name !== 'login'" class="app-header">
    <div class="container">
      <router-link to="/" class="app-brand">谛听 · 权限管理</router-link>
      <nav class="app-nav">
        <router-link to="/">仪表盘</router-link>
        <router-link to="/groups">权限组</router-link>
        <router-link to="/bindings">群绑定</router-link>
        <router-link to="/blacklist">黑名单</router-link>
        <router-link to="/whitelist">白名单</router-link>
        <router-link to="/points">权限点</router-link>
        <router-link to="/user-status">用户状态</router-link>
        <span class="user-tag">QQ {{ user?.qq_number || '—' }}</span>
        <a href="#" @click.prevent="doLogout">退出</a>
      </nav>
    </div>
  </header>

  <main class="app-main">
    <div class="container">
      <router-view />
    </div>
  </main>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from './composables/useAuth'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ToastItem from './components/ToastItem.vue'

const route = useRoute()
const router = useRouter()
const { user, logout } = useAuth()

async function doLogout() {
  await logout()
  router.push('/login')
}
</script>
