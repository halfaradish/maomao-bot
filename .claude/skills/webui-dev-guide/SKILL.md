---
name: webui-dev-guide
description: >
  DiTing-NoneBot WebUI 前端开发指南。使用 React 19 + HeroUI + TailwindCSS
  构建的玻璃拟态管理面板，视觉风格对齐 NapCatQQ。
  当需要开发/调试/构建 WebUI 前端、添加新页面或功能、排查前端问题、
  确保 UI 风格一致、或修改任何 webui/ 下的代码时使用。
  触发词：WebUI、前端、webui、React、HeroUI、TailwindCSS、页面、
  组件、样式、glassmorphism、毛玻璃、NapCat、对齐、npm run dev、
  npm run build、权限组、黑名单、白名单、权限点、用户状态、登录页、
  仪表盘、侧边栏、菜单、面包屑、表格、卡片、按钮、弹窗、对话框、
  JWT、diting_jwt、authStore、useAuth、api client、React Query。
---

# DiTing WebUI 前端开发指南

> React 19 + HeroUI 2 + TailwindCSS 3 — 玻璃拟态管理面板，视觉风格对齐 NapCatQQ。

## 1. 技术栈

| 层面 | 技术 | 说明 |
|------|------|------|
| 框架 | React 19 + TypeScript | 函数组件 + Hooks |
| 组件库 | HeroUI 2 (`@heroui/*`) | NapCat 同款，独立包导入 |
| CSS | TailwindCSS 3 + HeroUI 主题 | `dark:` 前缀暗色模式，`class` 策略 |
| 路由 | react-router-dom v7 | `BrowserRouter`，嵌套 `<Routes>` |
| 状态管理 | Zustand v5 | `persist` 中间件持久化 token |
| 服务端状态 | TanStack React Query v5 | 自动缓存/重取，30s staleTime |
| 动画 | Framer Motion v12 (`motion`) | 弹簧侧边栏、页面过渡、交错列表 |
| 图标 | react-icons (`md`, `fi`, `lu`) | Material Design + Feather + Lucide |
| 通知 | react-hot-toast v2 | 与 NapCat 相同 |
| 构建 | Vite 6 + @vitejs/plugin-react | 开发端口 5173，代理 `/api` → 6090 |

**核心原则**：所有 UI 元素使用 HeroUI 组件 + TailwindCSS 工具类，不写自定义 CSS 组件。HeroUI 的玻璃拟态效果通过 `backdrop-blur` + 半透明背景 + 微妙边框实现，这是 NapCat 风格的核心。

## 2. 目录结构

```
webui/src/
├── main.tsx                     # 入口：ReactDOM + BrowserRouter + Provider + App
├── App.tsx                      # 路由配置 + AuthChecker 守卫 + Toaster
├── provider.tsx                 # HeroUIProvider + QueryClientProvider 组合
├── api/
│   ├── client.ts                # fetch 封装（Bearer token + 401 处理）
│   ├── endpoints.ts             # API URL 常量工厂
│   └── hooks.ts                 # React Query hooks（useGroups, useBlacklist...）
├── components/
│   ├── Sidebar.tsx              # 侧边栏外壳（可折叠，弹簧动画）
│   ├── SidebarMenus.tsx         # 递归菜单渲染器
│   ├── BreadcrumbBar.tsx        # 顶部粘性面包屑栏
│   ├── PageBackground.tsx       # 装饰性模糊光斑背景
│   ├── ConfirmDialog.tsx        # 确认弹窗（HeroUI Modal 封装）
│   ├── EmptyState.tsx           # 空状态占位组件
│   └── ErrorFallback.tsx        # ErrorBoundary 回退 UI
├── config/
│   └── site.ts                  # 菜单配置 + MenuItem 类型
├── hooks/
│   ├── useConfirm.ts            # 确认对话框状态管理
│   └── useListManager.ts        # 黑/白名单泛型 CRUD 管理器
├── layouts/
│   └── DefaultLayout.tsx        # 认证后布局：侧边栏 + 内容区
├── pages/
│   ├── LoginPage.tsx            # 登录页（无侧边栏）
│   ├── DashboardPage.tsx        # 仪表盘导航卡片
│   ├── GroupsPage.tsx           # 权限组列表
│   ├── GroupDetailPage.tsx      # 权限组详情（成员/绑定/权限点 三标签页）
│   ├── BlacklistPage.tsx        # 黑名单（用户/群 双标签页）
│   ├── WhitelistPage.tsx        # 白名单（用户/群 双标签页）
│   ├── PointsPage.tsx           # 权限点目录
│   └── UserStatusPage.tsx       # 用户权限状态查询
├── store/
│   └── authStore.ts             # Zustand 认证 store（持久化到 localStorage）
├── styles/
│   └── globals.css              # Tailwind 指令 + 滚动条样式 + 全局重置
└── types/
    └── api.ts                   # API 响应/实体 TypeScript 类型
```

## 3. 视觉风格规范（对齐 NapCatQQ）

以下所有模式直接复制自 NapCatQQ 的代码实践。开发新功能时必须遵守。

### 3.1 玻璃拟态卡片

这是最重要的设计模式。所有内容容器使用此 className 组合：

```tsx
<Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl
                 border border-white/40 dark:border-white/10
                 shadow-sm rounded-2xl transition-all">
```

**关键点**：
- 半透明背景 `bg-white/60 dark:bg-black/40`（亮色/暗色各有不同的透明度）
- 背景模糊 `backdrop-blur-xl` 创建毛玻璃效果
- 微妙边框 `border-white/40`（亮色）/ `border-white/10`（暗色）
- 16px 圆角 `rounded-2xl`
- `transition-all` 实现悬停时的平滑过渡

### 3.2 配色系统

主题定义在 [tailwind.config.js](../../webui/tailwind.config.js)，使用 HeroUI 的 HSL 色彩变量：

| 语义色 | 亮色模式 | 暗色模式 | 用途 |
|--------|---------|---------|------|
| primary | `#FF7FAC` 樱花粉 | `#F33B7C` 深粉 | 主操作按钮、活动状态、链接 |
| secondary | `#88C0D0` 冰霜蓝 | `#4C8DAE` 深蓝 | 导航徽章、次要信息 |
| success | `#22C55E` 绿色 | 同 | 成功状态、白名单操作 |
| warning | `#F59E0B` 琥珀 | 同 | 超级管理员标签 |
| danger | `#DB3694` 紫粉 | 同 | 删除/危险操作、黑名单操作 |

**使用方式**：始终通过 Tailwind 的语义色类名引用颜色（如 `text-primary`、`bg-danger-50/50`），不要硬编码颜色值。

### 3.3 表格样式

统一使用 HeroUI `<Table>` 并应用此 classNames 配置：

```tsx
<Table
  aria-label="..."
  radius="sm"
  classNames={{
    wrapper: "bg-transparent shadow-none",
    th: "bg-white/40 dark:bg-white/5 backdrop-blur-md text-default-600",
    td: "group-data-[first=true]:first:before:rounded-none",
  }}
>
```

**要点**：
- 表格外包装 `bg-transparent` — 由外层 Card 提供背景
- 表头 `backdrop-blur-md` 实现毛玻璃表头效果
- `radius="sm"`（8px 内圆角）

### 3.4 按钮层级

| 层级 | 用法 | 代码 |
|------|------|------|
| Primary | 主要操作（创建、提交、确认） | `<Button color="primary" radius="full" variant="shadow" className="font-medium">` |
| Flat | 次要操作（取消、返回） | `<Button variant="flat" className="bg-default-100 dark:bg-default-50/50 text-default-600 font-medium">` |
| Light | 图标按钮（表格行操作） | `<Button isIconOnly size="sm" variant="light">` |
| Theme/Logout | 侧边栏底部按钮（药丸形、彩色背景） | `<Button radius="full" variant="flat" className="w-full bg-primary-50/50 hover:bg-primary-100/80 text-primary-600">` |

### 3.5 侧边栏设计

**容器**：
- 宽度：`w-64`（256px），通过 Framer Motion 弹簧动画折叠
- 背景：移动端 `bg-content1/70 backdrop-blur-xl backdrop-saturate-150`，桌面端 `md:bg-transparent md:backdrop-blur-none`
- Logo：`h-5 w-1 bg-primary rounded-full shadow-sm`（竖条）+ 粗体文本

**菜单项样式**：
- **非激活**：`hover:bg-default-100 hover:translate-x-1` + `variant="light"`
- **激活**：`bg-primary/10 text-primary dark:bg-primary/20 dark:text-primary-400 font-semibold translate-x-1` + `variant="shadow"`
- **叶子项指示器**：`w-3 h-1.5 rounded-full`，激活时 `bg-primary-500`，否则 `bg-primary-200`
- **子菜单箭头**：CSS `::before`/`::after` 伪元素绘制 45° 旋转条形，展开时旋转 180°

**底部按钮**（主题切换 + 退出登录）：
```tsx
// 主题切换
<Button radius="full" variant="flat"
  className="w-full bg-primary-50/50 hover:bg-primary-100/80
             text-primary-600 font-medium shadow-sm hover:shadow-md
             transition-all duration-300 backdrop-blur-sm">
// 退出登录（同样模式，用 danger 色）
<Button radius="full" variant="flat"
  className="w-full bg-danger-50/50 hover:bg-danger-100/80
             text-danger-500 ...">
```

### 3.6 面包屑栏

```tsx
<div className="h-10 flex items-center sticky top-2 z-30 m-2 mb-0
                rounded-full backdrop-blur-lg
                bg-background !bg-opacity-50 shadow-sm">
  {/* 侧边栏切换按钮 */}
  <Button isIconOnly radius="full" variant="light" onPress={onToggleSideBar}>
    {openSideBar ? <MdMenuOpen size={24} /> : <MdMenu size={24} />}
  </Button>
  {/* HeroUI Breadcrumbs */}
  <Breadcrumbs>
    {title.map(item => <BreadcrumbItem key={item}>{item}</BreadcrumbItem>)}
  </Breadcrumbs>
</div>
```

### 3.7 页面背景

三个大尺寸模糊彩色圆形装饰，固定在所有内容下方（`-z-10`）：

```tsx
<div className="fixed inset-0 -z-10 overflow-hidden
                bg-gradient-to-br from-indigo-50 via-white to-pink-50
                dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
  {/* 左上 primary */}
  <div className="absolute top-[-10%] left-[-10%] w-[600px] h-[600px]
                  rounded-full bg-primary/40 blur-[120px] opacity-30" />
  {/* 中右 secondary */}
  <div className="absolute top-[20%] right-[-10%] w-[500px] h-[500px]
                  rounded-full bg-secondary/40 blur-[100px] opacity-20" />
  {/* 底部 success */}
  <div className="absolute bottom-[-10%] left-[30%] w-[400px] h-[400px]
                  rounded-full bg-success/30 blur-[80px] opacity-25" />
</div>
```

### 3.8 暗色模式切换

暗色模式使用 Tailwind 的 `class` 策略，通过切换 `<html>` 上的 `"dark"` 类来控制：

```tsx
// DefaultLayout.tsx
function toggleTheme() {
  document.documentElement.classList.toggle("dark");
  setIsDark(!isDark);
}
```

所有颜色必须同时提供亮色和暗色变体：`bg-white/60 dark:bg-black/40`、`text-default-900 dark:text-white` 等。

### 3.9 滚动条

在 [globals.css](../../webui/src/styles/globals.css) 中定义的自定义滚动条：

```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: hsl(var(--heroui-default-300));
  border-radius: 3px;
}
```

## 4. 组件开发模式

### 4.1 列表页模式

标准的 CRUD 列表页遵循以下模式（参考 GroupsPage、PointsPage）：

```tsx
function MyListPage() {
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  // React Query 数据获取
  const { data, isLoading } = useMyList(page, PAGE_SIZE);
  const items = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;

  // 变更操作
  const createMutation = useCreateItem();
  const deleteMutation = useDeleteItem();

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="p-4">
      {/* 玻璃拟态卡片容器 */}
      <Card className="bg-white/60 dark:bg-black/40 backdrop-blur-xl ...">
        <CardBody>
          {/* 页面标题 + 内联添加表单（可折叠） */}
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-bold text-default-900 dark:text-white">页面标题</h1>
            <Button color="primary" radius="full" variant="shadow" onPress={toggleForm}>
              <MdAdd /> 新建
            </Button>
          </div>

          {/* HeroUI 表格 */}
          <Table classNames={{ wrapper: "bg-transparent shadow-none", ... }}>
            <TableHeader>...</TableHeader>
            <TableBody items={items} loadingState={isLoading ? "loading" : "idle"}>
              {(item) => (...)}
            </TableBody>
          </Table>

          {/* 分页（仅在多页时显示） */}
          {totalPages > 1 && (
            <div className="flex justify-center mt-4">
              <Pagination total={totalPages} page={page} onChange={setPage} />
            </div>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
```

### 4.2 内联创建表单

```tsx
{showForm && (
  <motion.div
    initial={{ opacity: 0, height: 0 }}
    animate={{ opacity: 1, height: "auto" }}
    className="mb-4 p-4 rounded-xl bg-default-100/50 dark:bg-white/5"
  >
    <div className="flex gap-3 items-end">
      <Input label="名称" value={name} onValueChange={setName} variant="bordered" />
      <Input label="描述" value={desc} onValueChange={setDesc} variant="bordered" />
      <Button color="primary" radius="full" onPress={handleCreate} isLoading={createMutation.isPending}>
        创建
      </Button>
      <Button variant="flat" radius="full" onPress={() => setShowForm(false)}>
        取消
      </Button>
    </div>
  </motion.div>
)}
```

### 4.3 确认删除对话框

使用项目中的 `useConfirm` hook + `ConfirmDialog` 组件：

```tsx
const { confirm, confirmState } = useConfirm();

async function handleDelete(item: Item) {
  await confirm({
    title: "确认删除",
    message: `确定要删除「${item.name}」吗？此操作不可撤销。`,
    confirmText: "删除",
    onConfirm: async () => {
      await deleteMutation.mutateAsync(item.id);
      toast.success("删除成功");
    },
  });
}

// 在 JSX 中渲染
<ConfirmDialog {...confirmState} onCancel={confirmState.handleCancel} />
```

**要点**：`useConfirm` 是异步的 — 等待用户点击确认后才执行 `onConfirm`。

### 4.4 Toast 通知

使用 react-hot-toast（已在 App.tsx 中全局配置）：

```tsx
import toast from "react-hot-toast";

// 成功
toast.success("创建成功");
// 错误
toast.error("操作失败，请重试");

// React Query mutation 中自动处理
const createMutation = useMutation({
  mutationFn: (data) => apiPost(API.xxx.create, data),
  onSuccess: () => {
    toast.success("创建成功");
    queryClient.invalidateQueries({ queryKey: ["my-list"] });
  },
  onError: (err) => toast.error(err.message),
});
```

### 4.5 空状态

```tsx
import EmptyState from "@/components/EmptyState";

// 默认（"暂无数据" + 收件箱图标）
<EmptyState />
// 自定义
<EmptyState icon={<MdGroup size={48} />} title="暂无权限组" description="点击「新建」创建第一个权限组" />
```

### 4.6 错误回退

页面级错误使用 `ErrorFallback` 组件（由 `react-error-boundary` 的 `ErrorBoundary` 消费）：

```tsx
// DefaultLayout 已包裹 ErrorBoundary，页面出错时自动显示
<ErrorBoundary FallbackComponent={ErrorFallback}>
  <Outlet />
</ErrorBoundary>
```

组件内部错误也可内联处理：
```tsx
if (error) {
  return (
    <Card className="bg-danger-50/50 dark:bg-danger-900/20 border-danger/30">
      <CardBody className="flex items-center gap-2 text-danger">
        <MdError size={20} />
        <span>加载失败：{error.message}</span>
      </CardBody>
    </Card>
  );
}
```

### 4.7 确认弹窗组件

```tsx
// ConfirmDialog 基于 HeroUI Modal
<Modal isOpen={isOpen} onClose={onCancel} size="sm" backdrop="blur">
  <ModalContent>
    <ModalHeader>{title}</ModalHeader>
    <ModalBody>{message}</ModalBody>
    <ModalFooter>
      <Button variant="light" onPress={onCancel}>{cancelText ?? "取消"}</Button>
      <Button color="danger" onPress={onConfirm}>{confirmText ?? "确认"}</Button>
    </ModalFooter>
  </ModalContent>
</Modal>
```

## 5. 添加新功能流程

### 5.1 添加新页面

**Step 1**：在 `src/pages/` 下创建页面组件，使用与现有页面相同的结构模式。

**Step 2**：在 [App.tsx](../../webui/src/App.tsx) 中添加路由：

```tsx
// 在 DefaultLayout 的 children 路由中添加
<Route path="new-feature" element={<NewFeaturePage />} />
```

**Step 3**：在 [config/site.ts](../../webui/src/config/site.ts) 的 `navItems` 中添加菜单项：

```tsx
{ key: "new-feature", label: "新功能", href: "/permissions/new-feature" }
```

如果放在"权限管理"下，作为新的 children 项添加；如果是一个新的顶级菜单，添加新的父级对象。

### 5.2 添加新 API Hook

**Step 1**：在 [endpoints.ts](../../webui/src/api/endpoints.ts) 中添加 API 端点工厂：

```tsx
// 添加新的路径方法
// 例如：API 对象中添加
newFeatureList: (page: number, size: number) =>
  `/permissions/new-feature?page=${page}&size=${size}`,
```

**Step 2**：在 [hooks.ts](../../webui/src/api/hooks.ts) 中添加 React Query hook：

```tsx
export function useNewFeatureList(page: number, size: number = 20) {
  return useQuery({
    queryKey: ["new-feature", page, size],
    queryFn: () => apiGet<PaginatedData<NewFeatureItem>>(
      API.newFeatureList(page, size)
    ),
  });
}

export function useCreateNewFeature() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: NewFeatureInput) => apiPost(API.newFeatureCreate, data),
    onSuccess: () => {
      toast.success("创建成功");
      queryClient.invalidateQueries({ queryKey: ["new-feature"] });
    },
  });
}
```

**Step 3**：在 [types/api.ts](../../webui/src/types/api.ts) 中添加 TypeScript 类型。

### 5.3 添加新菜单项

菜单配置在 [config/site.ts](../../webui/src/config/site.ts)：

```ts
export type MenuItem = {
  key: string;
  label: string;
  icon?: string;        // 当前未使用，预留扩展
  href?: string;        // 叶子节点：导航目标
  children?: MenuItem[]; // 父节点：子菜单列表
};

export const siteConfig = {
  name: "谛听 · 权限管理",
  navItems: [
    {
      key: "permissions",          // 一级菜单 key（唯一标识）
      label: "权限管理",            // 显示文本
      children: [                  // 二级菜单项
        { key: "groups", label: "权限组", href: "/permissions/groups" },
        // ... 添加新项
      ],
    },
    // 未来：添加新的一级菜单
  ],
};
```

## 6. NapCatQQ 对齐参考

### 6.1 本地参考路径

NapCatQQ 前端源码位于：`D:\Project\technical_group\diting\NapCatQQ\packages\napcat-webui-frontend\src\`

### 6.2 关键参考文件

| NapCat 文件 | 对应 DiTing 文件 | 参考用途 |
|-------------|-----------------|---------|
| `layouts/default.tsx` | `layouts/DefaultLayout.tsx` | 整体布局结构、面包屑栏实现 |
| `components/sidebar/index.tsx` | `components/Sidebar.tsx` | 侧边栏动画参数、玻璃态背景 |
| `components/sidebar/menus.tsx` | `components/SidebarMenus.tsx` | 递归菜单、活动检测、子菜单动画 |
| `components/page_background.tsx` | `components/PageBackground.tsx` | 背景光斑位置/尺寸/颜色 |
| `components/modal.tsx` | `components/ConfirmDialog.tsx` | Modal 样式和回调模式 |
| `components/toaster.tsx` | (App.tsx 中的 Toaster) | Toast 配置 |
| `const/themes/nc_pink.ts` | `tailwind.config.js` | 主题色板 HSL 值 |
| `config/site.tsx` | `config/site.ts` | 菜单数据结构 |
| `styles/globals.css` | `styles/globals.css` | 滚动条样式、字体声明 |

### 6.3 对齐检查清单

开发新功能或修改现有页面时，对照以下条目检查：

- [ ] 内容容器是否使用了玻璃拟态卡片 className？
- [ ] 表格是否使用 `bg-transparent` wrapper + `backdrop-blur-md` 表头？
- [ ] 主操作按钮是否使用 `color="primary" radius="full" variant="shadow"`？
- [ ] 删除/危险操作是否使用 `color="danger"` 并需要确认对话框？
- [ ] 是否同时提供了亮色和暗色模式的样式（`dark:` 前缀）？
- [ ] 页面是否有入场动画（`motion.div` + opacity/y）？
- [ ] 侧边栏活跃菜单项是否正确高亮？
- [ ] Toast 通知是否使用了 `react-hot-toast`？
- [ ] API 调用是否使用 React Query hook 而非直接 fetch？
- [ ] 新的 API 端点是否添加到 `endpoints.ts` 而非硬编码？
- [ ] 分页逻辑是否与现有页面一致（`page` state + `PAGE_SIZE` 常量）？

## 7. API 层参考

### 7.1 客户端使用

```tsx
import { apiGet, apiPost, apiDelete } from "@/api/client";

// GET 请求
const data = await apiGet<PaginatedData<Item>>("/permissions/groups?page=1&size=20");

// POST 请求
await apiPost("/permissions/groups", { name: "admin", display_name: "管理员组" });

// DELETE 请求
await apiDelete(`/permissions/groups/${id}`);
```

**自动行为**：
- 自动附加 `Authorization: Bearer <token>`（从 authStore 读取）
- 401 响应 → 自动清除 token + toast 提示 + 重定向 `/login`
- 网络错误 → 自动 toast 提示
- 业务错误（`status === "error"`）→ 抛出 Error

**不要在组件中直接使用 `apiGet/apiPost/apiDelete`** — 请通过 React Query hooks 使用。

### 7.2 端点速查

所有端点定义在 [endpoints.ts](../../webui/src/api/endpoints.ts) 中，通过 `API` 对象访问：

```
认证:     API.auth.login
权限组:   API.groups.list/create/get/delete
         API.groups.members.list/add/remove
         API.groups.perms.list/add/remove
         API.groups.bindings.list
绑定:     API.bindings.list/create/delete
黑名单:   API.blacklist.users.list/add/remove
         API.blacklist.groups.list/add/remove
白名单:   API.whitelist.users.list/add/remove
         API.whitelist.groups.list/add/remove
权限点:   API.points.list
         API.points.plugins
用户状态: API.userStatus.get
缓存:     API.cache.clear
```

### 7.3 响应格式

```ts
// 分页响应
interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// 外层包装
// API 客户端自动解包：apiGet 返回的数据已经过处理，
// 直接使用 data.data.items 读取列表
```

### 7.4 React Query 模式

```tsx
// 查询
const { data, isLoading, error } = useQuery({
  queryKey: ["key", ...params],
  queryFn: () => apiGet<ResponseType>(API.something.list(...params)),
});

// 变更
const mutation = useMutation({
  mutationFn: (input: InputType) => apiPost(API.something.create, input),
  onSuccess: () => {
    toast.success("操作成功");
    queryClient.invalidateQueries({ queryKey: ["key"] });
  },
});
```

## 8. 认证流程

### Zustand Auth Store

[store/authStore.ts](../../webui/src/store/authStore.ts) 使用 Zustand + `persist` 中间件：

- Token 持久化到 `localStorage` key `diting_jwt`
- `login(token, qq)` — 存储 token 和用户信息
- `logout()` — 清除所有状态
- `setToken(null)` — 由 API 客户端在收到 401 时调用

### 路由守卫

App.tsx 中的 `AuthChecker` 组件检查 `token` 是否存在。未认证时自动重定向到 `/login`。

### 登录页

LoginPage 提交 QQ 号 + 临时密码到 `POST /api/v1/auth/login`，成功后调用 `authStore.login()` 并导航到 `/permissions`。

**前提**：用户在 QQ 群中发送「权限 登录」获取 6 位临时密码。本地开发可使用 `WEBUI_DEV_PASSWORD` 环境变量绕过（具体配置见旧版 perm-webui-guide 或后端 auth.py）。

## 9. 开发工作流

```bash
cd webui

# 安装依赖
npm install

# 开发模式（端口 5173，/api 代理到 localhost:6090）
npm run dev

# 生产构建（输出到 dist/）
npm run build

# 预览构建结果
npm run preview
```

**并行启动后端**：`nb run`（端口 6090）+ `npm run dev`（端口 5173）。

**构建产物**：`webui/dist/` 由 FastAPI 的 SPA fallback handler 提供 — 非 `/api/*` 的 GET 404 请求返回 `index.html`。

**Docker 构建**：Dockerfile 包含 `npm ci && npm run build` 阶段，产物复制到最终镜像。

## 10. 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 页面白屏 | JS 加载失败或路由不匹配 | 检查浏览器控制台，确认 `dist/` 或 dev server 正常运行 |
| API 返回 401 | Token 过期或未登录 | 清除 `localStorage.diting_jwt`，重新登录 |
| 样式异常 | Tailwind 类未生成 | 检查类名是否在 `tailwind.config.js` safelist 中（动态类名） |
| 组件导入失败 | 缺少 HeroUI 子包 | 检查 `package.json` 是否包含所需的 `@heroui/*` 包 |
| 暗色模式不生效 | `dark` 类未添加到 `<html>` | 检查 `toggleTheme()` 调用 |
| 构建失败 | Node 版本或依赖问题 | 确认 Node ≥ 18，尝试 `rm -rf node_modules && npm install` |

## 11. 相关 Skills

- **[perm-system-guide](../perm-system-guide/SKILL.md)** — 后端权限系统核心、`check_permission`、权限模型
- **[diting-db-guide](../diting-db-guide/SKILL.md)** — Bot DB SQLAlchemy 操作（权限数据存储）
