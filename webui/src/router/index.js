import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
  },
  {
    path: '/',
    name: 'home',
    component: () => import('../views/DashboardView.vue'),
  },
  {
    path: '/groups',
    name: 'groups',
    component: () => import('../views/GroupListView.vue'),
  },
  {
    path: '/groups/:id',
    name: 'group-detail',
    component: () => import('../views/GroupDetailView.vue'),
  },
  {
    path: '/bindings',
    name: 'bindings',
    component: () => import('../views/BindingListView.vue'),
  },
  {
    path: '/blacklist',
    name: 'blacklist',
    component: () => import('../views/BlacklistView.vue'),
  },
  {
    path: '/whitelist',
    name: 'whitelist',
    component: () => import('../views/WhitelistView.vue'),
  },
  {
    path: '/points',
    name: 'points',
    component: () => import('../views/PointsView.vue'),
  },
  {
    path: '/user-status',
    name: 'user-status',
    component: () => import('../views/UserStatusView.vue'),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const { token } = useAuth()
  if (to.name !== 'login' && !token.value) {
    return { name: 'login' }
  }
})

export default router
