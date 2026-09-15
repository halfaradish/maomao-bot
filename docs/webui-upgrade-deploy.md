# WebUI 升级说明与部署指南

> 更新日期：2026-09-09
> 适用版本：当前 master 分支（WebUI 由单一「权限管理」扩展为五大模块）

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

## 二、部署到服务器需要做的事

### 1. 提交前检查（本地仓库）

- [ ] `webui/public/logo.jpg`、`webui/public/favicon.png` 加入 git（本次新增的二进制文件）
- [ ] `webui/package.json` / `webui/package-lock.json` 提交（新增 date-picker 依赖）
- [ ] 后端新文件提交：`src/api/{bot,plugins,groups,logs}.py` 及 `src/api/__init__.py` 修改
- [ ] 前端新页面提交：`webui/src/pages/{BotInfoPage,PluginsPage,QQGroupsPage,GroupFeaturesPage,MessageLogsPage}.tsx`、`components/BrandIcon.tsx`、`utils/format.ts`、`App.tsx`、`config/site.tsx`、`api/{endpoints,hooks}.ts`、`types/api.ts`、`index.html`
- [ ] 确认视觉验收通过（对照 `webui-dev-guide` 6.3 检查清单），用户确认新 UI 满意后再构建镜像

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

> ⚠️ 注意：构建镜像会用新 UI 覆盖 6090 上的旧 UI（之前的对比基线），确认满意后再构建。

### 4. 运行时依赖

- **MySQL**（diting_qq_bot / diting_icpc 两库）与 **Redis** 必须可达 —— 否则基础信息页连接状态灯变红、各页面数据为空
- **QQ 网关（OpenClaw/NapCat）必须在线** —— 否则影响：
  - 基础信息页：昵称、所在群数量显示「网关离线」
  - 群列表页：成员数/最大成员数缺失（仅剩数据库统计列，已优雅降级）
  - 群功能开关、插件管理、消息日志不受影响（纯 DB 数据）

### 5. 登录方式（生产）

- 生产环境无 `WEBUI_DEV_PASSWORD` 时，管理员需在 QQ 群发送「权限 登录」获取 6 位临时密码（5 分钟有效、一次性使用）
- 登录接口自带防爆破：同一 QQ 号 3 次失败后锁定 60 秒

### 6. 可选：反向代理 / HTTPS

- 6090 由容器直接暴露，如需要域名/HTTPS，用 Nginx/Caddy 反代到 `127.0.0.1:6090` 即可
- WebSocket 路径 `/onebot/v11/ws`（bot 与网关通信）如需经反代，注意开启 WebSocket 支持；前端页面本身纯 HTTP 无特殊要求

### 7. 后续维护提醒

- **后端热重载**：`.env` 的 `HOT_RELOAD` 未设置时，改 `src/` 代码后需 `docker restart diting-nonebot` 生效；如需开发期自动重载，在 `.env` 加 `HOT_RELOAD=true`（生产建议保持关闭）
- **换 logo/头像**：直接替换 `webui/public/logo.jpg` 与 `favicon.png`，重新构建镜像即生效（前端代码无需改动；图片缺失会自动回退盾牌图标）
- **加新插件管理功能**：后端在 `src/api/` 新增 router 并在 `__init__.py` 挂 `/v1` 前缀；前端走 pages + App.tsx 路由 + site.tsx 菜单 + endpoints/hooks/types 全链路

---

## 三、接口速查（供联调）

```bash
# 登录拿 token（dev 环境：超管 QQ + 123）
curl -X POST http://<host>:6090/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"qq_number": "<超管QQ>", "temp_password": "<临时密码>"}'

# 后续请求带 token
curl -H "Authorization: Bearer <token>" http://<host>:6090/api/v1/bot/info
curl -H "Authorization: Bearer <token>" http://<host>:6090/api/v1/plugins
curl -H "Authorization: Bearer <token>" "http://<host>:6090/api/v1/groups/list?page=1&size=20"
curl -H "Authorization: Bearer <token>" "http://<host>:6090/api/v1/logs/messages?page=1&size=20&keyword=关键词"
```
