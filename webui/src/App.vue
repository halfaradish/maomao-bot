<template>
  <ToastItem />
  <ConfirmDialog />

  <header v-if="route.name !== 'login'" class="app-header">
    <div class="container">
      <router-link to="/" class="app-brand">谛听 · 权限管理</router-link>
      <nav class="app-nav">
        <router-link to="/"><Gauge :size="16" />仪表盘</router-link>
        <router-link to="/groups"><ShieldCheck :size="16" />权限组</router-link>
        <router-link to="/bindings"><Link :size="16" />群绑定</router-link>
        <router-link to="/blacklist"><Prohibit :size="16" />黑名单</router-link>
        <router-link to="/whitelist"><CheckCircle :size="16" />白名单</router-link>
        <router-link to="/points"><Key :size="16" />权限点</router-link>
        <router-link to="/user-status"><MagnifyingGlass :size="16" />用户状态</router-link>
        <span class="user-tag"><UserCircle :size="14" />QQ {{ user?.qq_number || '—' }}</span>
        <a href="#" @click.prevent="doLogout" class="logout-link"><SignOut :size="14" />退出</a>
      </nav>
    </div>
  </header>

  <main class="app-main">
    <div class="container">
      <router-view v-slot="{ Component }">
        <transition name="fade-page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
  </main>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from './composables/useAuth'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ToastItem from './components/ToastItem.vue'
import { PhGauge as Gauge, PhShieldCheck as ShieldCheck, PhLink as Link, PhProhibit as Prohibit, PhCheckCircle as CheckCircle, PhKey as Key, PhMagnifyingGlass as MagnifyingGlass, PhUserCircle as UserCircle, PhSignOut as SignOut } from "@phosphor-icons/vue"

const route = useRoute()
const router = useRouter()
const { user, logout } = useAuth()

async function doLogout() {
  await logout()
  router.push('/login')
}
</script>
