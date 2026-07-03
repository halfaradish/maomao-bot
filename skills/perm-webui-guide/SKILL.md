---
name: perm-webui-guide
description: >
  DiTing-NoneBot 权限系统 WebUI 管理面板开发与使用指南。
  当需要开发/调试/构建 WebUI 前端、理解登录认证流程、添加新的管理视图、
  排查前端问题、或了解 REST API 端点时使用。
  触发词：WebUI、web管理面板、管理面板前端、前端、Vue、Vite、SPA、
  LoginView、DashboardView、GroupListView、GroupDetailView、
  BindingListView、BlacklistView、WhitelistView、PointsView、
  UserStatusView、npm run dev、npm run build、WEBUI_JWT_SECRET、
  WEBUI_DEV_PASSWORD、perm-webui、useAuth、api client、前端构建、
  vite.config.js、diting_jwt、JWT token、登录、login、auth。
---

# DiTing 权限系统 WebUI 管理面板

> Vue 3 + Vite SPA，通过 REST API 提供权限系统的图形化管理界面。
> 提供 9 个管理视图、JWT 认证、开发环境密码绕过，替代 QQ 聊天命令的部分管理操作。

## 1. 架构概览

```
┌─────────────────────────────────────────────────┐
│              浏览器 (Browser)                     │
│  Vue 3 SPA (Pico.css dark theme)                 │
│  ├─ router/index.js       hash 路由 (9 routes)   │
│  ├─ api/client.js         fetch 封装 (JWT)       │
│  ├─ composables/          useAuth/Confirm/Toast  │
│  └─ views/                9 个管理视图            │
└──────────────┬──────────────────────────────────┘
               │  HTTP  (npm run dev → :5173 proxy → :6090)
               │  生产环境: 从 :6090 直接提供 dist/
               ▼
┌─────────────────────────────────────────────────┐
│           FastAPI (NoneBot ~fastapi driver)       │
│  /api/v1/auth/*          认证端点                │
│  /api/v1/permissions/*    权限 CRUD 端点 (30+)   │
│  /api/status             健康检查                │
│  /*                      SPA fallback (dist/)    │
└──────────────┬──────────────────────────────────┘
               │  SQLAlchemy 2.0 async
               ▼
┌─────────────────────────────────────────────────┐
│         Bot DB (diting_qq_bot)                   │
│  8 张权限表  +  perm_cache (进程内 TTL)          │
└─────────────────────────────────────────────────┘
```

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3.5 + Vite 5.4 + Pico.css 2.0 | `<script setup>` SFC，无 TypeScript |
| 路由 | Vue Router 4.5 + createWebHashHistory | hash 路由避免服务端 rewrite |
| 状态 | 模块级 composable 单例 | `useAuth` / `useConfirm` / `useToast` |
| 图标 | Phosphor Icons Vue 2.2 | 侧边栏导航 + 视图标题图标 |
| 认证 | JWT HS256 (24h) | Bearer token → `src/api/deps.py` 依赖注入 |
| API | FastAPI → SQLAlchemy 2.0 async | 全部 30+ 端点需要 JWT 认证 |
| 后端引擎 | `src/common/permission/` | 与 QQ 管理面板共享同一权限核心 |

**关键约束**：
- 生产环境构建产物在 `webui/dist/`，由 FastAPI 的 SPA fallback handler 提供
- 开发环境使用 Vite 开发服务器（端口 5173），代理 `/api` 到后端（端口 6090）
- API 响应格式统一为 `{status, code, message, data, timestamp, path}`
- 所有权限 API 端点位于 `/api/v1/permissions/` 下，需要 `Authorization: Bearer <token>` 头
- JWT 存储在 `localStorage` key `diting_jwt` 中，页面刷新不丢失

---

## 2. 登录认证

### 2.1 完整登录流程

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────┐
│   QQ 频道     │     │  NoneBot 进程     │     │   WebUI 浏览器  │
└──────┬───────┘     └────────┬─────────┘     └───────┬───────┘
       │  权限 登录             │                       │
       │ ────────────────────► │                       │
       │                       │ 生成 6 位随机密码       │
       │                       │ perm_cache.set(        │
       │                       │   "webui:temp_pwd:     │
       │                       │    {qq}", 密码, 300)   │
       │  6 位临时密码           │                       │
       │ ◄──────────────────── │                       │
       │                       │                       │
       │                       │    POST /api/v1/auth/login
       │                       │    {qq_number, temp_password}
       │                       │ ◄──────────────────────│
       │                       │                       │
       │                       │ 验证密码 + 暴力破解保护  │
       │                       │ 密码正确 → 删除缓存     │
       │                       │ 签发 JWT (24h)         │
       │                       │ ──────────────────────►│
       │                       │                       │
       │                       │   存储到 localStorage   │
       │                       │   key: diting_jwt      │
```

### 2.2 后端登录端点

**文件**：[src/api/auth.py](../../src/api/auth.py)

```python
POST /api/v1/auth/login
Body: { "qq_number": "2091842518", "temp_password": "123456" }
Response: { "status": "success", "data": { "token": "eyJ...", "expires_in": 86400 } }
```

安全机制：
- **暴力破解保护**：每 QQ 号每 60 秒最多 3 次尝试 (`BRUTE_FORCE_MAX_ATTEMPTS = 3`)
- **一次性密码**：临时密码使用后立即从缓存删除，防止重放
- **JWT 黑名单**：`/logout` 和 `/refresh` 将旧 token 的 `jti` 加入黑名单缓存
- **24 小时过期**：JWT 包含 `exp` 声明，过期后强制重新登录

### 2.3 开发环境密码绕过

在本地开发时无法通过 QQ 获取临时密码。项目提供了 `WEBUI_DEV_PASSWORD` 环境变量作为开发绕过：

**工作方式**（[src/api/auth.py](../../src/api/auth.py#L105-L117)）：

```python
# 仅在以下条件全部满足时生效：
# 1. 设置了 WEBUI_DEV_PASSWORD 环境变量
# 2. ENVIRONMENT != 'prod'（硬性环境保护）
# 3. 登录的 QQ 号在 SUPERUSERS 列表中
# 4. 输入的密码与 WEBUI_DEV_PASSWORD 完全匹配
```

| 安全层 | 机制 |
|--------|------|
| 环境保护 | `ENVIRONMENT=prod` 时**强制忽略**，即使配置了 `WEBUI_DEV_PASSWORD` |
| 用户限制 | 仅 `SUPERUSERS` 中的 QQ 号可用 |
| 默认关闭 | `WEBUI_DEV_PASSWORD` 未设置时，绕过代码不激活 |
| 可复用 | 开发密码不会被一次性删除，方便重复登录 |

**配置**（`.env.local`）：

```bash
WEBUI_JWT_SECRET=diting-dev-secret-local   # 固定 secret，JWT 重启后仍有效
WEBUI_DEV_PASSWORD=123456                  # 开发密码
```

**更快的迭代方式** — 浏览器控制台直接注入 JWT，跳过登录页面：

```javascript
localStorage.setItem('diting_jwt', '<你的JWT>');
location.reload();
```

> ⚠️ **绝对不要在生产环境设置 `WEBUI_DEV_PASSWORD`**。即使误设，`ENVIRONMENT=prod` 的硬性门控也会使其失效，但不要依赖这个兜底。

### 2.4 前端 auth 可组合项

**文件**：[webui/src/composables/useAuth.js](../../webui/src/composables/useAuth.js)

```javascript
// 模块级单例 refs — 所有组件共享同一状态
const token = ref(localStorage.getItem('diting_jwt') || '')
const user = ref(null)
const isLoggedIn = computed(() => !!token.value)

// 导出的函数
login(qqNumber, tempPassword)   // POST /auth/login → 存储 token → 设置 user
logout()                        // POST /auth/logout (fire-and-forget) → 清除状态
clearToken()                    // 手动清除（API 客户端在收到 401 时调用）
initFromToken()                 // 从 JWT payload 解码恢复 user 信息
```

---

## 3. 视图参考

9 个管理视图，全部懒加载。路由守卫 (`beforeEach`) 自动将未登录用户重定向到 `/login`。

### 3.1 视图总览

| # | 路由 | 视图文件 | 功能描述 | API 端点 |
|---|------|---------|---------|---------|
| 1 | `/login` | `LoginView.vue` | QQ 号 + 临时密码登录表单 | `POST /auth/login` |
| 2 | `/` | `DashboardView.vue` | 6 张功能卡片，快捷导航 | (纯前端，无 API 调用) |
| 3 | `/groups` | `GroupListView.vue` | 权限组 CRUD + 分页列表 | `GET/POST/DELETE /permissions/groups` |
| 4 | `/groups/:id` | `GroupDetailView.vue` | 权限组详情：成员 + 权限点管理 | `GET /permissions/groups/{id}` + members/perms 子端点 |
| 5 | `/bindings` | `BindingListView.vue` | 群-权限组绑定管理 | `GET/POST/DELETE /permissions/bindings` |
| 6 | `/blacklist` | `BlacklistView.vue` | 用户/群黑名单（双标签页） | `/permissions/blacklist/{users\|groups}` |
| 7 | `/whitelist` | `WhitelistView.vue` | 用户/群白名单（双标签页） | `/permissions/whitelist/{users\|groups}` |
| 8 | `/points` | `PointsView.vue` | 已注册权限点只读列表 | `GET /permissions/points` |
| 9 | `/user-status` | `UserStatusView.vue` | 聚合查看用户完整权限状态 | `GET /permissions/users/{user_id}/status` |

### 3.2 各视图详情

#### LoginView（`/login`）

- QQ 号输入框 + 临时密码输入框（6 位，`maxlength="6"`）
- 调用 `useAuth().login()`，成功后 `router.push('/')`
- 开发模式提示（仅 `localhost` 显示）：告知 `WEBUI_DEV_PASSWORD` 可用
- 独立布局：不显示侧边栏，`App.vue` 中条件渲染

#### DashboardView（`/`）

- 6 张功能卡片，每张含 Phosphor 图标 + 中文标题 + 描述文字
- 点击卡片跳转到对应路由：权限组、群绑定、黑名单、白名单、权限点、用户状态
- 无需 API 调用，纯导航页面

#### GroupListView（`/groups`）

- 权限组列表（分页 10 条/页），支持创建和删除
- 点击行进入 `GroupDetailView`
- 创建表单：名称（必填）、展示名、描述
- 删除操作：弹出确认对话框 (`useConfirm`)

#### GroupDetailView（`/groups/:id`）

- 权限组详情 + 面包屑导航（权限组 > 名称）
- **成员管理**：表格（QQ 号、添加时间）+ 添加表单（输入 QQ 号）+ 删除按钮
- **权限点管理**：表格（perm_key）+ 添加表单 + 删除按钮
- 权限点删除使用 `encodeURIComponent()` 处理冒号路径

#### BindingListView（`/bindings`）

- 群绑定列表（分页），支持创建和删除
- 创建表单：权限组下拉选择（从 `GET /permissions/groups` 获取选项）+ 群号输入
- 可按群号过滤

#### BlacklistView + WhitelistView（`/blacklist`, `/whitelist`）

- 双标签页（用户/群），每个标签页独立状态
- 添加表单：ID 输入 + 原因（可选）
- 表格列：ID、user_id/group_id、原因、创建者、创建时间、删除操作
- 两者结构完全相同，仅 API 路径和中文标签不同

#### PointsView（`/points`）

- 只读表格，列出所有已注册权限点
- 插件名称下拉过滤器（从数据中提取去重）
- 列：ID、插件名、perm_key、名称、描述
- 无操作按钮

#### UserStatusView（`/user-status`）

- 查询表单：输入 QQ 号 → 点击"查询"
- 结果以信息卡片展示：
  1. **基本信息**：user_id + 是否超级管理员（彩色徽章）
  2. **黑名单状态**：被拉黑 → 原因/操作者/时间；否则 "未拉黑"
  3. **白名单状态**：被加白 → 原因/操作者/时间；否则 "未加白"
  4. **所属权限组**：卡片列表，展示 display_name + 拥有的权限点（`<code>` 标签）；空 → "未加入任何权限组"

### 3.3 视图开发模式

所有视图遵循相同的 `<script setup>` 模式：

```vue
<template>
  <!-- 页面标题 + 图标 -->
  <!-- 内联添加表单 -->
  <!-- 数据表格 + 分页 -->
  <!-- 空状态 -->
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { apiGet, apiPost, apiDelete } from '../api/client'
import { useConfirm } from '../composables/useConfirm'
import { useToast } from '../composables/useToast'
import Pagination from '../components/Pagination.vue'

const PAGE_SIZE = 10
const { showConfirm } = useConfirm()
const { showToast } = useToast()

// 状态
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

// 加载
async function load(p = page.value) {
  loading.value = true
  try {
    const res = await apiGet(`/permissions/...?page=${p}&size=${PAGE_SIZE}`)
    items.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

// 创建
async function doAdd() { /* POST → showToast → load() */ }

// 删除
async function doDelete(item) {
  await showConfirm('确认删除', `确定要删除 ${item.name} 吗？`)
  await apiDelete(`/permissions/.../${item.id}`)
  showToast('删除成功')
  load()
}

onMounted(() => load())
watch(page, () => load())
</script>
```

---

## 4. API 端点参考

全部端点位于 `/api/v1/` 下，需要 `Authorization: Bearer <token>` 头（认证端点自身除外）。

### 4.1 认证

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/auth/login` | 否 | 提交 QQ 号 + 临时密码，获取 JWT |
| `POST` | `/auth/refresh` | 是 | 刷新 JWT（旧 token 立即入黑名单） |
| `POST` | `/auth/logout` | 是 | 撤销 JWT（加入黑名单） |

### 4.2 黑名单

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/permissions/blacklist/users?page=&size=` | — | 用户黑名单列表（分页） |
| `POST` | `/permissions/blacklist/users` | `{user_id, reason}` | 添加用户到黑名单 |
| `DELETE` | `/permissions/blacklist/users/{user_id}` | — | 从黑名单移除用户 |
| `GET` | `/permissions/blacklist/groups?page=&size=` | — | 群黑名单列表（分页） |
| `POST` | `/permissions/blacklist/groups` | `{group_id, reason}` | 添加群到黑名单 |
| `DELETE` | `/permissions/blacklist/groups/{group_id}` | — | 从黑名单移除群 |

### 4.3 白名单

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/permissions/whitelist/users?page=&size=` | — | 用户白名单列表（分页） |
| `POST` | `/permissions/whitelist/users` | `{user_id, reason}` | 添加用户到白名单 |
| `DELETE` | `/permissions/whitelist/users/{user_id}` | — | 从白名单移除用户 |
| `GET` | `/permissions/whitelist/groups?page=&size=` | — | 群白名单列表（分页） |
| `POST` | `/permissions/whitelist/groups` | `{group_id, reason}` | 添加群到白名单 |
| `DELETE` | `/permissions/whitelist/groups/{group_id}` | — | 从白名单移除群 |

### 4.4 权限组

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/permissions/groups?page=&size=` | — | 权限组列表（分页） |
| `POST` | `/permissions/groups` | `{name, display_name?, description?}` | 创建权限组 |
| `GET` | `/permissions/groups/{id}` | — | 权限组详情（含成员和权限点） |
| `DELETE` | `/permissions/groups/{id}` | — | 删除权限组（级联删除关联） |

**权限组成员**：

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/permissions/groups/{id}/members` | — | 列出权限组成员 |
| `POST` | `/permissions/groups/{id}/members` | `{user_ids: [int, ...]}` | 批量添加成员 |
| `DELETE` | `/permissions/groups/{id}/members/{user_id}` | — | 移除成员 |

**权限组权限点**：

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/permissions/groups/{id}/perms` | — | 列出权限组的权限点 |
| `POST` | `/permissions/groups/{id}/perms` | `{perm_keys: [str, ...]}` | 批量添加权限点 |
| `DELETE` | `/permissions/groups/{id}/perms/{perm_key:path}` | — | 移除权限点（注意 `:path` 转换） |

### 4.5 群绑定

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/permissions/bindings?qq_group_id=&page=&size=` | — | 绑定列表，可选按群号过滤 |
| `POST` | `/permissions/bindings` | `{qq_group_id, permission_group_id}` | 创建群-权限组绑定 |
| `DELETE` | `/permissions/bindings/{binding_id}` | — | 删除绑定 |

### 4.6 权限点 & 用户状态 & 缓存

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| `GET` | `/permissions/points?plugin=&page=&size=` | — | 已注册权限点列表，可按插件过滤 |
| `GET` | `/permissions/users/{user_id}/status` | — | 聚合查看用户完整权限状态 |
| `POST` | `/permissions/cache/clear` | — | 手动清除所有权限检查缓存 |

### 4.7 响应格式

所有 API 返回统一格式：

```json
{
  "status": "success",
  "code": 200,
  "message": "操作成功",
  "data": {
    "items": [...],
    "total": 42,
    "page": 1,
    "page_size": 10
  },
  "timestamp": "2026-07-03T12:00:00.000000Z",
  "path": "/api/v1/permissions/groups"
}
```

错误响应：

```json
{
  "status": "error",
  "code": 401,
  "message": "临时密码无效或已过期",
  "data": null,
  "timestamp": "...",
  "path": "/api/v1/auth/login"
}
```

前端 `api()` 客户端在 `status === 'error'` 时自动 `throw new Error(json.message)`。调用方只需 `try/catch` 并用 `showToast` 显示错误即可。

### 4.8 分页查询参数

所有列表端点支持分页：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从 1 开始） |
| `size` | int | 10 | 每页条数 |

过滤参数：

| 端点 | 参数 | 说明 |
|------|------|------|
| `/permissions/points` | `plugin` | 按插件名过滤 |
| `/permissions/bindings` | `qq_group_id` | 按群号过滤 |

---

## 5. 前端架构

### 5.1 目录结构

```
webui/
├── index.html                  # Vite 入口 HTML
├── package.json                # 依赖管理
├── vite.config.js              # Vite 配置（代理 + 构建）
└── src/
    ├── main.js                 # createApp + router + Pico.css
    ├── App.vue                 # 根组件（条件布局：侧边栏 vs 登录页）
    ├── router/
    │   └── index.js            # 9 条路由 + beforeEach 守卫
    ├── api/
    │   └── client.js           # fetch 封装（JWT 注入 + 401 处理）
    ├── composables/
    │   ├── useAuth.js          # token/user 状态 + login/logout
    │   ├── useConfirm.js       # 确认对话框 Promise 封装
    │   └── useToast.js         # Toast 通知管理
    ├── components/
    │   ├── ConfirmDialog.vue   # 模态确认对话框
    │   ├── ToastItem.vue       # 固定右下角 Toast 通知
    │   └── Pagination.vue      # 通用分页组件
    ├── views/
    │   ├── LoginView.vue       # 登录页
    │   ├── DashboardView.vue   # 仪表盘
    │   ├── GroupListView.vue   # 权限组列表
    │   ├── GroupDetailView.vue # 权限组详情
    │   ├── BindingListView.vue # 群绑定列表
    │   ├── BlacklistView.vue   # 黑名单
    │   ├── WhitelistView.vue   # 白名单
    │   ├── PointsView.vue      # 权限点列表
    │   └── UserStatusView.vue  # 用户状态查询
    └── styles/
        └── main.css            # Pico.css 暗色主题覆盖 + 布局样式
```

### 5.2 API 客户端

**文件**：[webui/src/api/client.js](../../webui/src/api/client.js)

```javascript
const API_BASE = '/api/v1'

// 核心函数 — 所有请求通过此函数
async function api(method, path, body = null) {
  // 1. 自动注入 Authorization: Bearer <token>
  // 2. 网络错误 → showToast + throw
  // 3. HTTP 401 → clearToken + redirect /login + throw
  // 4. 响应 status === 'error' → throw new Error(message)
  // 5. 成功 → 返回完整 JSON
}

// 便捷导出
export const apiGet = (path) => api('GET', path)
export const apiPost = (path, body) => api('POST', path, body)
export const apiDelete = (path) => api('DELETE', path)
```

**设计要点**：
- 仅 GET / POST / DELETE 三种方法（无需 PUT/PATCH）
- 401 自动清除 token 并跳转登录页 — 所有视图无需各自处理
- `apiDelete` 的 path 参数中若含冒号（如 `perm_key`），调用方需 `encodeURIComponent()`

### 5.3 路由设计

**文件**：[webui/src/router/index.js](../../webui/src/router/index.js)

- `createWebHashHistory()` — hash 路由避免服务端 URL 重写
- 全部 9 条路由，所有视图懒加载（`() => import(...)`）
- `beforeEach` 守卫：未认证 → 重定向 `/login`
- 路由键名 `route.path` 用于 `<transition>` 动画

### 5.4 可组合项（Composables）

| 可组合项 | 文件 | 模式 | 功能 |
|----------|------|------|------|
| `useAuth` | `composables/useAuth.js` | 模块级单例 refs | token 持久化、login/logout、从 JWT 恢复 user |
| `useConfirm` | `composables/useConfirm.js` | reactive + Promise | `showConfirm(title, msg)` → 返回 Promise，取消时 reject |
| `useToast` | `composables/useToast.js` | reactive 数组 | `showToast(msg, type)` → 3 秒自动清除，type 空或 `'error'` |

**为什么不用 Pinia**：模块级 `ref()` 共享状态已足够覆盖 3 个可组合项的场景。`useAuth` 的 `token` 和 `user` refs 在 `api/client.js`、`router/index.js` 和所有视图间共享，无需额外状态管理库。

### 5.5 共享组件

| 组件 | Props | 事件 | 说明 |
|------|-------|------|------|
| `Pagination` | `page` (v-model), `total`, `pageSize` (默认 10) | `update:page` | 上一页/下一页 + 页码（最多 5 个加省略号）+ "共 N 条" |
| `ConfirmDialog` | (无 — 通过 `useConfirm` 读取状态) | — | 模态遮罩层 + 确认/取消按钮；点击遮罩 = 取消 |
| `ToastItem` | (无 — 通过 `useToast` 读取状态) | — | 固定右下角，fadeIn 动画，3 秒自动消失 |

### 5.6 App.vue 条件布局

**文件**：[webui/src/App.vue](../../webui/src/App.vue)

```javascript
// 登录页：只渲染 <router-view>，无侧边栏
// 其他页面：侧边栏 + 主内容区
if (route.name !== 'login') {
  // 渲染完整布局：sidebar + <router-view>
} else {
  // 只渲染 <router-view>
}
```

**侧边栏结构**：
- 顶部：品牌标识 "谛听 · 权限管理"
- 中部：7 个导航链接（含 Phosphor 图标）
- 底部：当前用户 QQ 号 + 退出登录链接

---

## 6. 开发工作流

### 6.1 Vite 开发服务器

```bash
cd webui
npm install       # 首次安装依赖
npm run dev       # 启动在 http://localhost:5173
```

**代理配置**（[vite.config.js](../../webui/vite.config.js)）：

```javascript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://localhost:6090',  // NoneBot FastAPI 端口
      changeOrigin: true,
    },
  },
},
```

开发工作流：`nb run`（后端 6090）+ `cd webui && npm run dev`（前端 5173）→ 浏览器访问 `localhost:5173`。

**优点**：Vite HMR（热模块替换）— 修改 Vue 文件即时生效，无需刷新。

### 6.2 生产构建

```bash
cd webui && npm run build
# → webui/dist/index.html + webui/dist/assets/*.js + webui/dist/assets/*.css
```

构建产物由 [src/api/__init__.py](../../src/api/__init__.py) 的 `_spa_404_handler` 提供：

```python
_WEBUI_INDEX = _WEBUI_DIR / "dist" / "index.html"
# 对所有非 /api 路径的 404 GET 请求，返回 SPA 的 index.html
```

### 6.3 Docker 构建

`Dockerfile` 包含前端构建阶段：

```dockerfile
# 阶段：前端构建
FROM node:20-alpine AS webui-builder
WORKDIR /app/webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci
COPY webui/ ./
RUN npm run build
# → dist/ 复制到最终镜像
```

### 6.4 构建后验证

```bash
# 1. 检查 dist 目录
ls webui/dist/
# 应包含: index.html + assets/

# 2. 确认后端可提供
curl http://localhost:6090/          # → SPA HTML
curl http://localhost:6090/api/hello # → JSON（不被 fallback 拦截）

# 3. 确认 WebSocket 不受影响（NapCat 连接）
# 查看日志: onebot v11 连接正常
```

---

## 7. 添加新视图

按以下 6 步流程添加新的管理视图：

### Step 1: 创建 Vue SFC

```bash
# 复制现有视图作为模板
cp webui/src/views/PointsView.vue webui/src/views/NewFeatureView.vue
```

修改 `<script setup>` 中的 API 端点和表单字段。

### Step 2: 添加路由

在 [webui/src/router/index.js](../../webui/src/router/index.js) 中添加：

```javascript
{
  path: '/new-feature',
  name: 'new-feature',
  component: () => import('../views/NewFeatureView.vue'),
},
```

### Step 3: 添加 API 端点（后端）

在 [src/api/permissions.py](../../src/api/permissions.py) 中添加新的路由处理函数。使用 `verify_token` 依赖注入进行认证保护。

### Step 4: 添加侧边栏导航

在 [webui/src/App.vue](../../webui/src/App.vue) 的 `<nav class="app-nav">` 中添加：

```html
<router-link to="/new-feature"><SomeIcon :size="18" />新功能</router-link>
```

记得在 `<script setup>` 中导入对应的 Phosphor 图标。

### Step 5: 添加 Dashboard 卡片（可选）

如果新功能重要，在 [webui/src/views/DashboardView.vue](../../webui/src/views/DashboardView.vue) 中添加导航卡片。

### Step 6: 重新构建

```bash
cd webui && npm run build
```

重启 NoneBot 使新构建生效。

---

## 8. 故障排除

### 8.1 构建后访问空白页面

**现象**：`http://localhost:6090/` 显示白屏，浏览器控制台报 404 加载 JS/CSS 失败。

**原因**：Vite 构建后 `index.html` 中的资源路径以 `/` 开头，需要确认 `_spa_404_handler` 正确提供静态文件。

**排查**：
```bash
# 1. 确认 dist 文件存在
ls webui/dist/assets/

# 2. 确认 index.html 中的路径正确
head -20 webui/dist/index.html
# 应有 <script type="module" crossorigin src="/assets/index-xxx.js">

# 3. 检查 api/__init__.py 中的 _WEBUI_DIR 指向
grep "_WEBUI_DIR\|_WEBUI_INDEX" src/api/__init__.py
```

### 8.2 Vite 代理不工作

**现象**：`npm run dev` 启动成功但 API 请求返回 404。

**解决**：
1. 确保后端在 6090 端口运行
2. 检查 `vite.config.js` 中 proxy target 是否正确
3. 清除浏览器缓存
4. 验证：`curl http://localhost:6090/api/hello` 应返回 JSON

### 8.3 登录后立即被踢回登录页

**现象**：登录 API 返回成功 token，但立即重定向回 `/login`。

**原因**：
1. JWT 签名验证失败 — `WEBUI_JWT_SECRET` 在重启后变化（未在 `.env.local` 中固定）
2. Token 已过期（24 小时后）
3. Token 的 `jti` 被意外加入黑名单缓存

**解决**：
```bash
# 1. 在 .env.local 中固定 JWT SECRET
WEBUI_JWT_SECRET=diting-dev-secret-local

# 2. 清除浏览器 localStorage
localStorage.removeItem('diting_jwt')

# 3. 重新登录
```

### 8.4 页面刷新后回到登录页

**现象**：登录状态在页面刷新后丢失。

**原因**：`useAuth.js` 从 `localStorage` 读取 token 的初始化失败。

**排查**：
1. 打开浏览器 DevTools → Application → Local Storage → 确认 `diting_jwt` 存在
2. 检查 `initFromToken()` 解码 JWT payload 是否成功
3. 查看 console 是否有未捕获的错误

### 8.5 DELETE 权限点失败（400 Bad Request）

**现象**：在 GroupDetailView 中删除权限点时报错。

**原因**：`perm_key` 包含冒号（如 `group_ban:ban`），FastAPI 需要 `:path` 转换器。

**解决**：前端调用时使用 `encodeURIComponent()`：
```javascript
await apiDelete(`/permissions/groups/${id}/perms/${encodeURIComponent(permKey)}`)
```

### 8.6 缓存不一致

**现象**：通过 WebUI 修改了权限，但 QQ 频道的权限检查仍使用旧结果。

**原因**：`perm_cache` TTL 为 60 秒，最多需要 60 秒才能反映变更。WebUI 的所有写操作都会自动调用 `perm_cache.clear_pattern()` 或 `clear_all()`，但检查时间窗口可能尚未过期。

**解决**：
- 等待最多 60 秒自动刷新
- 或调用 `POST /api/v1/permissions/cache/clear` 手动清除所有缓存

### 8.7 常见控制台错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `Uncaught TypeError: Cannot read properties of null` | `res.data.items` 为 null | 检查 API 返回结构，确认 `data` 中存在 `items` |
| `router.push is not a function` | `api/client.js` 导入 router 失败 | 确认 `import router from '../router'` 路径正确 |
| `Authorization header missing` | 未登录直接访问 API | 检查路由守卫是否正常工作 |
| `CORS policy error` | 跨域请求被拒绝 | 使用 Vite 代理或确保前后端同源 |
| `npm run build` 失败 | Node 版本或依赖问题 | 确认 Node ≥ 18，`rm -rf node_modules && npm install` |

---

## 快速参考卡片

### 常用命令

```bash
cd webui
npm install          # 安装依赖
npm run dev          # 启动开发服务器 (:5173)
npm run build        # 生产构建 → dist/
```

### API 速查

```
认证:   POST /api/v1/auth/login    {qq_number, temp_password} → {token, expires_in}
黑名单: /api/v1/permissions/blacklist/{users|groups}  GET/POST/DELETE
白名单: /api/v1/permissions/whitelist/{users|groups}  GET/POST/DELETE
权限组: /api/v1/permissions/groups[/{id}[/members|/perms]]
绑定:   /api/v1/permissions/bindings  GET/POST/DELETE
权限点: /api/v1/permissions/points  GET
用户状态: /api/v1/permissions/users/{user_id}/status  GET
缓存:   /api/v1/permissions/cache/clear  POST
```

### 导入速查

```javascript
// Vue
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// API
import { apiGet, apiPost, apiDelete } from '../api/client'

// 可组合项
import { useAuth } from '../composables/useAuth'
import { useConfirm } from '../composables/useConfirm'
import { useToast } from '../composables/useToast'

// 组件
import Pagination from '../components/Pagination.vue'

// 图标
import { PhShieldCheck as ShieldCheck } from "@phosphor-icons/vue"
```

### 相关 Skill

- 权限系统核心引擎 + QQ 管理面板 → 参见 **[perm-system-guide](../perm-system-guide/SKILL.md)**
- Bot DB 操作（权限数据存储） → 参见 **[diting-db-guide](../diting-db-guide/SKILL.md)**
