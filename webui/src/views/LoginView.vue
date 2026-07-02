<template>
  <div class="login-box">
    <article>
      <header><SignIn :size="20" />权限管理登录</header>
      <form @submit.prevent="doLogin">
        <label for="qq">
          QQ号
          <input id="qq" v-model="qq" type="text" placeholder="请输入 QQ 号" required />
        </label>
        <label for="pwd">
          临时密码
          <input id="pwd" v-model="pwd" type="password" placeholder="6 位临时密码" maxlength="6" required />
        </label>
        <button :aria-busy="busy" type="submit">
          <SignIn :size="16" weight="bold" />登录
        </button>
      </form>
      <p class="login-hint">在 QQ 中发送「权限 登录」获取临时密码</p>
    </article>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { useToast } from '../composables/useToast'
import { PhSignIn as SignIn } from "@phosphor-icons/vue"

const router = useRouter()
const { login } = useAuth()
const { showToast } = useToast()

const qq = ref('')
const pwd = ref('')
const busy = ref(false)

async function doLogin() {
  if (!qq.value || !pwd.value) return
  busy.value = true
  try {
    await login(qq.value, pwd.value)
    router.push('/')
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '登录失败'
    showToast(msg, 'error')
  } finally {
    busy.value = false
  }
}
</script>
