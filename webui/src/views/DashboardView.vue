<template>
  <div>
    <h3 class="page-title"><Gauge :size="22" weight="fill" />权限管理</h3>
    <div class="dashboard-cards">
      <article @click="go('/groups')">
        <ShieldCheck :size="24" class="card-icon" />
        <h4>权限组</h4>
        <p>管理 RBAC 角色、成员和权限点分配</p>
      </article>
      <article @click="go('/bindings')">
        <Link :size="24" class="card-icon" />
        <h4>群绑定</h4>
        <p>关联 QQ 群与权限组</p>
      </article>
      <article @click="go('/blacklist')">
        <Prohibit :size="24" class="card-icon" />
        <h4>黑名单</h4>
        <p>管理用户和群的黑名单</p>
      </article>
      <article @click="go('/whitelist')">
        <CheckCircle :size="24" class="card-icon" />
        <h4>白名单</h4>
        <p>管理用户和群的白名单</p>
      </article>
      <article @click="go('/points')">
        <Key :size="24" class="card-icon" />
        <h4>权限点</h4>
        <p>查看已注册的权限点列表</p>
      </article>
      <article @click="go('/user-status')">
        <MagnifyingGlass :size="24" class="card-icon" />
        <h4>用户状态</h4>
        <p>查询指定用户的完整权限状态</p>
      </article>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { PhGauge as Gauge, PhShieldCheck as ShieldCheck, PhLink as Link, PhProhibit as Prohibit, PhCheckCircle as CheckCircle, PhKey as Key, PhMagnifyingGlass as MagnifyingGlass } from "@phosphor-icons/vue"

const router = useRouter()

function go(path) {
  router.push(path)
}
</script>
