# 新版 WebUI 指南（预览与部署）

> 更新日期：2026-09-15
> 适用版本：分支 `dev/webui-five-modules`（WebUI 由单一「权限管理」扩展为五大模块）

---

## 一、本次更新内容

### 1. 前端（webui/）

**新增五个顶级菜单**（`webui/src/config/site.tsx`）：

| 菜单 | 路由 | 页面 | 说明 |
|---|---|---|---|
| 基础信息 | `/info` | `BotInfoPage.tsx` | 头像 + 谛听名称 + 在线状态 + Bot 账号/所在群数量/运行时长/连接状态 |
| 权限管理 | `/permissions/*` | 原有页面 | 未改动 |
| 插件管理 | `/plugins` | `PluginsPage.tsx` | 36 个插件按分组卡片展示，Modal 看完整用法，纯只读 |
| 群管理 | `/groups/list` | `QQGroupsPage.tsx` | 群列表 + 成员数/消息量/活跃度统计，行内统计弹窗 |
| 群管理 | `/groups/features` | `GroupFeaturesPage.tsx` | 5 个群功能开关（入群欢迎/离群通知/违禁词检测/告警日志/入群审核） |
| 消息日志 | `/logs` | `MessageLogsPage.tsx` | 多条件筛选（群号/QQ号/关键词/类型/时间范围）+ 分页 + 详情弹窗 |

**品牌资源**：
- `webui/public/logo.jpg` — 侧边栏/登录页 logo + 基础信息页头像（`BrandIcon.tsx` 组件，图片缺失自动回退盾牌 SVG）
- `webui/public/favicon.png` — 浏览器标签页图标（`index.html` 已修正 type 声明）

**新增依赖**（`webui/package.json`）：
- `@heroui/date-picker@2.3.33`、`@internationalized/date@3.12.0`（消息日志页时间选择，磨砂玻璃日历弹层）

### 2. 后端（src/api/）

全部挂载于 `/api/v1` 前缀，**均要求 JWT 鉴权**（`verify_token`），响应统一 `success()` 包装：

| 接口 | 文件 | 说明 |
|---|---|---|
| `GET /api/v1/bot/info` | `api/bot.py` | bot_id、昵称、适配器、在线状态、群数量、真实运行时长、Bot DB/ICPC DB/Redis 连通状态（并发 ping） |
| `GET /api/v1/plugins` | `api/plugins.py` | `get_loaded_plugins()` 元信息 + 权限点数量，与 QQ 群内 /help 同源 |
| `GET /api/v1/groups/list` | `api/groups.py` | 合并 group_statistics / monitored_groups 表 + `bot.get_group_list()`（成员数）+ messages_event_logs 聚合；bot 离线优雅降级 |
| `GET /api/v1/groups/{id}/stats` | `api/groups.py` | 单群统计详情 |
| `GET /api/v1/groups/features/{id}` | `api/groups.py` | 群功能开关状态（与运行时 `is_group_feature_enabled` 同源） |
| `POST /api/v1/groups/features/{id}/toggle` | `api/groups.py` | 开关切换，复用 auto_manage_group 的 FEATURE_MAP 与开关逻辑（PermissionGroupPerm/GroupPermBinding 增删 + `perm_cache` 清理） |
| `GET /api/v1/logs/messages` | `api/logs.py` | MessageEventLog 分页 + 多条件过滤，按时间倒序 |

**顺带修复**：`GET /api/status` 的 uptime 由写死的 3600 改为进程真实启动时长。

---

## 二、快速预览

> 只想看看页面长什么样，看这一节；要上生产，直接跳第三节。

### 0. 代码在哪个分支

五个新页面（基础信息 / 插件管理 / 群管理 / 消息日志）位于分支 **`dev/webui-five-modules`**，**尚未并入 `master`**。

```bash
git clone -b dev/webui-five-modules https://gitee.com/half_a_radish/maomao-bot-NoneBot.git
cd maomao-bot-NoneBot
```

clone `master` 只能看到原来的「权限管理」，没有新模块。

### 1. 用 Docker 一条命令跑起来

前提：Docker Desktop 已启动。

```bash
cp env.template .env      # 然后按第三节「生产环境变量」填数据库/Redis
bash scripts/docker-manager.sh build
bash scripts/docker-manager.sh start
```

浏览器打开 **http://localhost:6090** 。

**不用本地装 Node** —— `Dockerfile` 的第 0 阶段（`Dockerfile:1-8`）已在容器里跑完 `npm ci --legacy-peer-deps && npm run build`，产物 `webui/dist` 被打进镜像，由后端的 SPA handler 托管。

> 首次 `build` 会拉 Node/Python 镜像并安装 Playwright chromium，耗时较长，属正常。

### 2. 想改前端 / 看细节：本地 dev server（热更新）

改一行等容器重建太慢，用 Vite dev server：

```bash
# 1) 先把后端跑起来（Docker 方式即可，占 6090）
bash scripts/docker-manager.sh start

# 2) 另开一个终端起前端
cd webui
npm ci --legacy-peer-deps      # 与 Dockerfile 保持一致
npm run dev
```

浏览器打开 **http://localhost:5173** 。

**不用改任何代理配置**：`webui/vite.config.ts:12-20` 已把 `/api` 代理到 `http://localhost:6090`，dev server 上的页面与后端直接连通。改 `webui/src/` 下的文件会热更新，不用刷新。

```bash
npm run dev        # 开发服务器（5173）
npm run build      # tsc 类型检查 + 打包出 dist/
npm run typecheck  # 只做类型检查
```

### 3. 五个新页面在哪

登录后看左侧菜单：

| 菜单 | 路径 | 看什么 |
|---|---|---|
| 基础信息 | `/info` | Bot 头像/昵称/在线状态、群数量、运行时长，以及 **Bot DB / ICPC DB / Redis 三个连接状态灯** |
| 插件管理 | `/plugins` | 36 个插件按 5 个分组铺成卡片墙，点卡片看用法 |
| 群管理 → 群列表 | `/groups/list` | 群列表 + 消息量/活跃人数/7 天消息，行内按钮开单群统计弹窗 |
| 群管理 → 群功能 | `/groups/features` | 5 个群功能开关（入群欢迎/离群通知/违禁词检测/告警日志/入群审核） |
| 消息日志 | `/logs` | 群号/QQ号/关键词/类型/时间范围筛选 + 分页 + 详情弹窗 |

**最快的自检方式**：打开 `/info`，看三个连接灯是否全绿。全绿说明数据库和 Redis 都通了，其余页面就不会是空的。

### 4. 登录

两种方式，取决于 `.env` 里的 `ENVIRONMENT`：

**非 prod 环境**（本地预览推荐）：

```
ENVIRONMENT=local          # 注意：不能是 prod，auth.py 有硬门禁
WEBUI_DEV_PASSWORD=123     # 自定
SUPERUSERS=["你的QQ号"]
```

用 **`SUPERUSERS` 里的 QQ 号 + `WEBUI_DEV_PASSWORD`** 登录。

**生产环境**：`WEBUI_DEV_PASSWORD` 会被禁用，需在 QQ 群发送「**权限 登录**」拿到 6 位临时密码（5 分钟有效、一次性）。

> 登录接口有防爆破：同一 QQ 号 3 次失败后锁定 60 秒。

### 5. 三个容易踩的坑

**① `webui/dist` 不在仓库里**

`dist/` 被 `.gitignore:50` 忽略，克隆下来**没有前端构建产物**。如果既没起 `npm run dev`、也没 `npm run build`，直接访问 `http://localhost:6090/` 会返回 404。Docker 构建会自动处理这一步；手动跑 Python 后端则需要自己先 `npm run build` 一次。

**② 页面数据全部来自数据库，库空则页面空**

新页面读的是 **Bot DB 的 `diting_qq_bot`**（`messages_event_logs`、`permission_*`、`monitored_groups` 等），**不是** ICPC 竞赛库。至少要保证 `BOT_DB_*` 和 Redis 可达。

参考：一台有真实数据的库约含 46 万条 `messages_event_logs`、26 个权限组。

**③ QQ 网关不在线是正常的，不影响看页面**

`bot_count: 0`（网关未连接）时：

- `/info` 页：昵称、群数量显示为空/离线
- `/groups/list`：**成员数显示「—」** —— 这是后端优雅降级的结果（走 `bot.get_group_list()` 实时查询，拿不到就是 `null`），**不是 bug**

其余页面（插件管理、消息日志、权限管理）是纯 DB 数据，不受影响。

### 6. 改了前端之后

前端**不在热重载范围内**（`HOT_RELOAD` 只监视 `src/`、`bot.py`、`.env*`）。改完要让 6090 上的正式页面生效：

```bash
cd webui && npm run build          # 产出 webui/dist
bash scripts/docker-manager.sh restart
```

或直接重建镜像（`docker-manager.sh build && start`）。

开发期如需后端自动重载，在 `.env` 加 `HOT_RELOAD=true`（生产建议关闭）。

---

## 三、部署到服务器

### 1. 代码提交状态

本节所列文件均已随 `2d58ae5` 提交入库，无需再逐项检查：

- `webui/public/logo.jpg`、`webui/public/favicon.png`（二进制资源）
- `webui/package.json` / `webui/package-lock.json`（date-picker 依赖）
- 后端：`src/api/{bot,plugins,groups,logs}.py` 及 `src/api/__init__.py`
- 前端：`webui/src/pages/*`、`components/{BrandIcon,PageLoading}.tsx`、`hooks/useTheme.ts`、`config/site.tsx`、`constants.ts`、`utils/`、`App.tsx`、`api/{endpoints,hooks}.ts`、`types/api.ts`、`index.html`

> 生产构建前建议先对照 `webui-dev-guide` 6.3 检查清单做一次视觉验收。

### 2. 生产环境变量（.env）

- [ ] `ENVIRONMENT=prod`（auth.py 有硬门禁：prod 下禁用 `WEBUI_DEV_PASSWORD` 后门）
- [ ] `WEBUI_DEV_PASSWORD` 生产环境**清空或删除**
- [ ] `SUPERUSERS` 配置为实际超管 QQ 号
- [ ] `BOT_DB_*` / `ICPC_DB_*` / `REDIS_*` 指向生产 MySQL/Redis

### 3. Docker 构建与启动

```bash
# 构建镜像（Dockerfile 已含 npm ci --legacy-peer-deps && npm run build，
# 构建产物 webui/dist 打进镜像，由 FastAPI SPA handler 提供服务）
bash scripts/docker-manager.sh build

# 启动（ENVIRONMENT=prod → 宿主端口 6090）
bash scripts/docker-manager.sh start
```

> ⚠️ 构建镜像会用新 UI 覆盖 6090 上的旧 UI（之前的对比基线），确认满意后再构建。

### 4. 运行时依赖

- **MySQL**（`diting_qq_bot` / `diting_icpc` 两库）与 **Redis** 必须可达 —— 否则基础信息页连接状态灯变红、各页面数据为空
- **QQ 网关（OpenClaw/NapCat）在线与否**的影响：
  - 基础信息页：昵称、所在群数量显示「网关离线」
  - 群列表页：成员数/最大成员数缺失（仅剩数据库统计列，已优雅降级）
  - 群功能开关、插件管理、消息日志**不受影响**（纯 DB 数据）

### 5. 登录方式（生产）

- 生产环境无 `WEBUI_DEV_PASSWORD` 时，管理员需在 QQ 群发送「权限 登录」获取 6 位临时密码（5 分钟有效、一次性使用）
- 登录接口自带防爆破：同一 QQ 号 3 次失败后锁定 60 秒

### 6. 可选：反向代理 / HTTPS

- 6090 由容器直接暴露，如需域名/HTTPS，用 Nginx/Caddy 反代到 `127.0.0.1:6090` 即可
- WebSocket 路径 `/onebot/v11/ws`（bot 与网关通信）如需经反代，注意开启 WebSocket 支持；前端页面本身纯 HTTP 无特殊要求

### 7. 后续维护提醒

- **后端热重载**：`.env` 的 `HOT_RELOAD` 未设置时，改 `src/` 代码后需 `docker restart diting-nonebot` 生效；开发期如需自动重载，加 `HOT_RELOAD=true`（生产建议保持关闭）
- **前端改动**：必须 `npm run build` + 重启容器，不在热重载范围内
- **换 logo/头像**：直接替换 `webui/public/logo.jpg` 与 `favicon.png`，重新构建镜像即生效（前端代码无需改动；图片缺失会自动回退盾牌图标）
- **加新插件管理功能**：后端在 `src/api/` 新增 router 并在 `__init__.py` 挂 `/v1` 前缀；前端走 pages + App.tsx 路由 + site.tsx 菜单 + endpoints/hooks/types 全链路

---

## 四、接口速查（供联调）

```bash
# 登录拿 token（dev 环境：超管 QQ + WEBUI_DEV_PASSWORD）
curl -X POST http://<host>:6090/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"qq_number": "<超管QQ>", "temp_password": "<临时密码>"}'

# 后续请求带 token
curl -H "Authorization: Bearer <token>" http://<host>:6090/api/v1/bot/info
curl -H "Authorization: Bearer <token>" http://<host>:6090/api/v1/plugins
curl -H "Authorization: Bearer <token>" "http://<host>:6090/api/v1/groups/list?page=1&size=20"
curl -H "Authorization: Bearer <token>" "http://<host>:6090/api/v1/logs/messages?page=1&size=20&keyword=关键词"
```

---

## 相关文档

- `.claude/skills/webui-dev-guide/SKILL.md` —— 前端开发约定（玻璃拟态、NapCat 配色对齐、新增页面全链路）
- `.claude/skills/perm-system-guide/SKILL.md` —— 权限系统与群功能开关机制
