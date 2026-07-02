<template>
  <ToastItem />
  <ConfirmDialog />

  <div v-if="route.name !== 'login'" class="app-layout">
    <aside class="app-sidebar">
      <div class="sidebar-header">
        <router-link to="/" class="app-brand">
          <span class="brand-dot"></span>
          谛听 · 权限管理
        </router-link>
      </div>

      <nav class="app-nav">
        <router-link to="/"><Gauge :size="18" />仪表盘</router-link>
        <router-link to="/groups"><ShieldCheck :size="18" />权限组</router-link>
        <router-link to="/bindings"><Link :size="18" />群绑定</router-link>
        <router-link to="/blacklist"><Prohibit :size="18" />黑名单</router-link>
        <router-link to="/whitelist"><CheckCircle :size="18" />白名单</router-link>
        <router-link to="/points"><Key :size="18" />权限点</router-link>
        <router-link to="/user-status"><MagnifyingGlass :size="18" />用户状态</router-link>
      </nav>

      <div class="sidebar-footer">
        <span class="user-tag"><UserCircle :size="14" />QQ {{ user?.qq_number || '—' }}</span>
        <a href="#" @click.prevent="doLogout" class="logout-link"><SignOut :size="14" />退出登录</a>
      </div>
    </aside>

    <main class="app-main">
      <router-view v-slot="{ Component, route }">
        <transition name="fade-page">
          <component :is="Component" :key="route.path" />
        </transition>
      </router-view>
    </main>
  </div>

  <router-view v-else />
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