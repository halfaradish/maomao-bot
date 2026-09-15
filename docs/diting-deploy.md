# 谛听部署（diting_deploy）

在 QQ 里发 `/diting pull|build|restart|status|log`，让服务器拉代码、重建 Docker、重启服务，不用 SSH。

---

## 1. 为什么是两半

容器里没有执行部署的条件，这不是偷懒而是硬约束：

| 事实 | 后果 |
|---|---|
| 镜像 `python:3.10-slim`，未装 `git`、未装 `docker` CLI | 容器内无法 pull、无法 build |
| `.dockerignore` 排除 `**/.git` 与 `scripts/`（只保留 `entrypoint.sh`） | 容器内没有仓库元数据，也没有 `docker-manager.sh` |
| `docker-compose.yml` 没有挂 `/var/run/docker.sock` | 容器内没有宿主机 docker 权限 |
| `src/`、`bot.py`、`.env*` 是 bind mount，`bot.py` 带 watchfiles 热重载 | 代码一落到宿主机工作区，热重载天然生效 |

所以：

- **插件（容器内）** 只做：鉴权 → 写请求文件 → 受理回执 → 跟踪并回报结果。
- **执行器（宿主机）** 做全部脏活：`git fetch/checkout`、`docker compose build`、`restart`、探活。
- **通信通道**：`docker-compose.yml` 里已有的 `./data:/app/data` 可写挂载，两边看到同一份文件，**不需要改 Dockerfile、docker-compose.yml 或 docker-manager.sh**。

执行器在宿主机上，不在容器里，所以 `docker compose down/up` 重建 bot 容器不会杀掉它 —— 这是它能跑完探活、写下终态、再由新容器回报结果的前提。

```
QQ 群 /diting build
   │ ① 权限点校验 → ② 写请求 → ③ 立刻回「已受理」
   ▼
<repo>/data/deploy/queue/<job_id>.json          ← 容器内 root 写
   │ ④ diting-agent.path 触发 → 执行器 mv 认领
   ▼
scripts/diting-agent.sh（宿主机，root）
   │ ⑤ flock → 开哨兵 → git fetch/checkout → 关哨兵
   │ ⑥ docker-manager.sh build（按需）/ restart → HTTP 探活
   ▼
data/deploy/status/<job_id>.json + logs/<job_id>.log + state.json（心跳）
   │ ⑦ 轮询任务读回（未重启）或新实例启动钩子补报（重启后）
   ▼
QQ 回报进度与结果
```

---

## 2. 命令手册

| 命令 | 权限点 | 二次确认 | 说明 |
|---|---|---|---|
| `/diting pull` | `diting_deploy:pull` | 否 | 拉取 `DITING_DEPLOY_BRANCH` 配置的分支，等热重载生效 |
| `/diting build` | `diting_deploy:build` | **是** | 拉取 → 按需重建镜像 → 重启容器 → 探活 |
| `/diting restart` | `diting_deploy:restart` | **是** | 不拉代码，直接重启并探活 |
| `/diting status` | `diting_deploy:view` | 否 | agent 心跳、代码版本、工作区、容器、待执行与上次任务 |
| `/diting log [job_id]` | `diting_deploy:view` | 否 | 执行日志尾部，默认最近一次作业 |
| `/diting confirm <令牌>` | 同该动作 | — | 执行待确认的 build / restart（60 秒内有效，一次性） |
| `/diting cancel` | — | — | 取消本会话内待确认的操作 |
| `/diting` / `/diting help` | — | — | 帮助 |

别名：`deploy`→`pull`、`rebuild`→`build`、`state`→`status`、`logs`→`log`。

### 二次确认用令牌，不用 `got()`

`build` 与 `restart` 会中断服务，需要二次确认。这里刻意**没有**用 `matcher.got()`：

- `got()` 会把会话里的**下一条消息**当作回答吞掉，群里极易误吞别人的正常发言；
- `got()` 没有超时机制，会一直挂着；
- 令牌方案一次性、绑定 `user_id` + 会话、60 秒过期、存内存（重启即作废），语义清晰且没有状态冲突。

### ⚠️ dev 环境的命令前缀

`COMMAND_START` 由 `.env` 决定，`.env.dev` 是 `["dev-"]`，所以 dev 环境必须输入 `dev-diting pull`；
`.env.prod` 是 `["/", ""]`，`/diting pull` 与裸 `diting pull` 都能触发。这是 NoneBot 的全局行为，所有命令一致。

### 权限

插件启动时会自动创建权限组 `diting_deploy`（名字可由 `DITING_DEPLOY_PERM_GROUP` 改）并绑定全部 4 个权限点。
授权只需超管在群里执行：

```
perm 绑定 群 <群号> diting_deploy
```

超级管理员（`.env` 的 `SUPERUSERS`）天然放行，无需任何配置。

> **边界**：权限系统里「群绑定权限组」只在**群聊**生效（见 `src/common/permission/checker.py` 的 `_check_permission_groups`：
> 私聊没有 `group_id`，跳过群绑定检查）。所以私聊里只有超管和被直接加入权限组的成员能通过。

---

## 3. 协议契约

`data/deploy/` 下每个文件的所有权严格划分，**谁写谁读不重叠**，避免互相覆盖：

| 路径 | 谁写 | 谁读 | 说明 |
|---|---|---|---|
| `queue/<job_id>.json` | 插件 | 执行器 | 待执行请求。执行器用 `mv` 到 `running/` 认领，认领后文件从 queue 消失 |
| `running/<job_id>.json` | 执行器 | 插件（仅展示） | 已认领。作业结束时执行器会删掉它；残留说明执行器异常退出 |
| `status/<job_id>.json` | 执行器 | 插件 | 状态与结果，`tmp + mv` 原子落盘 |
| `logs/<job_id>.log` | 执行器 | 插件（`/diting log` 取尾部） | 完整 stdout/stderr |
| `state.json` | 执行器（每 5 分钟 + 每次作业） | 插件 | 心跳：分支/SHA/容器状态/诊断警告 |
| `boot.json` | 插件（每次启动） | 执行器 | 执行器靠它的 mtime 判断 pull 后热重载是否真的把 worker 拉起来了 |
| `reported/<job_id>.json` | 插件 | 插件 | 回报去重标记（重启后不漏报、不重报） |
| `pull.lock` | 执行器 | `bot.py` 的 watcher | 热重载暂停哨兵 |
| `agent.lock` | 执行器 `flock` | — | 串行化，防并发部署 |
| `build.fingerprint` | 执行器 | 执行器 | 构建指纹，决定 `build` 是否需要真的重建镜像 |

**时间约定**：机器判定一律用 epoch 秒整数字段（`*_ts`），ISO 字符串字段（`*_at`）只用于展示。
两者都写，避免跨进程解析时区字符串。

**job_id 格式**：`20260915-143012-build-8f3a2c`（时间戳-动作-随机后缀），可排序、可在 QQ 里肉眼引用。

**解析约定**：执行器用 `sed` 按行取扁平字段，不依赖 `jq`。因此插件写出的 JSON 必须由
`json.dumps(indent=2)` 生成（一键一行），且键在整个文档里唯一（`session` 里的
`type`/`group_id`/`user_id` 与顶层不重复）。

### 请求（插件 → 执行器）

```json
{
  "protocol": 1,
  "job_id": "20260915-143012-build-8f3a2c",
  "action": "build",
  "branch": "master",
  "requested_by": 2091842518,
  "requested_at": "2026-09-15T14:30:12",
  "requested_ts": 1789000212,
  "bot_self_id": "1234567",
  "env": "prod",
  "session": {
    "type": "group",
    "group_id": 123456,
    "user_id": 2091842518
  }
}
```

### 状态（执行器 → 插件）

```json
{
  "protocol": 1,
  "job_id": "20260915-143012-build-8f3a2c",
  "action": "build",
  "state": "succeeded",
  "step": "done",
  "message": "代码与镜像已就绪，服务探活通过",
  "exit_code": 0,
  "requested_by": 2091842518,
  "session": { "type": "group", "group_id": 123456, "user_id": 2091842518 },
  "branch": "master",
  "started_at": "2026-09-15T14:30:20",
  "started_ts": 1789000220,
  "updated_at": "2026-09-15T14:33:41",
  "updated_ts": 1789000421,
  "finished_at": "2026-09-15T14:33:41",
  "finished_ts": 1789000421,
  "result": {
    "old_sha": "71d4d1c",
    "new_sha": "a1b2c3d",
    "changed": true,
    "rebuild_needed": true,
    "rebuilt": true,
    "rebuild_skipped": false,
    "restarted": true,
    "reloaded": false,
    "rollback_hint": "cd /home/bot/diting/nonebot && git checkout -f 71d4d1c && bash scripts/docker-manager.sh build && bash scripts/docker-manager.sh restart"
  },
  "log_file": "logs/20260915-143012-build-8f3a2c.log"
}
```

`state` 取值：`queued`（已认领）→ `running` → 终态 `succeeded` / `failed` / `rejected`。
`step` 取值：`preflight`、`lock`、`git-fetch`、`git-checkout`、`reload`、`rebuild`、`restart`、`health`、`done`。

**`session` 与 `requested_by` 在状态里冗余一份**，是为了容器重建后新实例能独立完成回报，不依赖任何内存状态。

### 执行器退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 预检拒绝（未改动任何东西） |
| 3 | git 失败（fetch 或 checkout） |
| 4 | 镜像构建失败 |
| 5 | 重启失败 |
| 6 | 探活失败 / pull 后 worker 未在超时内起来 |
| 8 | 执行器内部错误 |

> 注意：退出码写在**状态文件**里（`exit_code`），执行器本身的进程退出码始终是 0 ——
> systemd 的 oneshot 单元不该因为一次业务失败而变红，业务结果以状态文件为准。

---

## 4. 宿主机安装

前提：Linux + systemd + 已装 docker / docker compose / git；仓库已在服务器上 clone 好
（例如生产 `/home/bot/diting/nonebot`，开发 `/home/bot/diting/nonebot-dev`）。

### 4.1 准备 `.env`

```bash
cd /home/bot/diting/nonebot
```

`.env`（base，两个环境都会加载）：

```
ENVIRONMENT=prod
HOT_RELOAD=true                  # pull 靠它自动生效；设 false 则 pull 完必须 /diting restart
DITING_DEPLOY_BRANCH=master      # 唯一的分支来源，命令不接受分支参数
```

必须确认的几点：

- **`DITING_DEPLOY_BRANCH` 写 `.env` 或 `.env.<ENVIRONMENT>` 都行**，执行器与插件都按同一套级联去读。
  唯一要记住的是：`local_config.py` 先 `load_dotenv(".env")` 再 `load_dotenv(".env.<ENV>")`，
  而 python-dotenv 默认**不覆盖已存在的环境变量**，compose 的 `env_file` 又只注入 `.env` ——
  所以同名键**以 `.env` 为准**，`.env.<ENV>` 只补前者没有的键。想避免踩这个坑就统一写在 `.env` 里。
- `.env` 与 `.env.prod` 必须是**普通文件**。若存在同名**目录**（compose 短语法挂载在源文件缺失时会创建目录），
  `local_config.py` 用 `os.path.exists` 判断（目录也为真）会打印 `successful load`，但 dotenv 实际读到空 ——
  配置整体静默丢失。执行器的预检会直接拒绝并提示。
- **`ENVIRONMENT` 只能是 `prod` 或 `dev`。** 不要用 `local`：`docker-manager.sh` 会把 `local` 映射成生产档位
  （容器 `diting-nonebot`、端口 6090）却挂载 `.env.local`，档位与配置错配。执行器会拒绝这种作业。
- `NEW_OJ_REDIS_HOST` 不能是 `localhost`/`127.0.0.1`：bridge 网络里那指向容器自身，应填 compose 服务名
  `diting-redis`。执行器心跳会把这一条作为 warning 报给 `/diting status`。
- 开发目录的 `.env` 用 `ENVIRONMENT=dev`、`DITING_DEPLOY_BRANCH=dev/1.0`。
- **仓库目录的属主与执行器运行身份（root）不一致是可以的**，执行器对每次 git 调用都带
  `-c safe.directory=<仓库>`，不会因 git 的 dubious ownership 拒绝工作，也不会去改宿主的全局 git 配置。
  但如果你手工在其他脚本里用 root 跑 git，仍会遇到这个问题。

### 4.2 安装执行器

```bash
sudo bash deploy/systemd/install.sh                    # 默认实例，用脚本所在仓库作为目标目录
sudo bash deploy/systemd/install.sh --root /home/bot/diting/nonebot
sudo bash deploy/systemd/install.sh --uninstall        # 卸载
sudo bash deploy/systemd/install.sh --help             # 用法

# 第二个环境（dev）：必须指向另一份独立目录，并用 --name 区分单元名
sudo bash deploy/systemd/install.sh --name dev --root /home/bot/diting/nonebot-dev
sudo bash deploy/systemd/install.sh --name dev --uninstall
```

安装脚本会：

1. 建好 `<repo>/data/deploy/{queue,running,status,logs,reported}` 并置 `0777`
   （容器内是 root，跨 uid 时否则会互相写不动；执行器也以 root 运行，这是刻意定死的边界）；
2. 生成 `/etc/default/diting-agent`（已存在则不覆盖）；
3. 把单元里的 `@DITING_DEPLOY_ROOT@` 替换成真实路径后装到 `/etc/systemd/system`
   —— `[Path]` 段不支持环境变量展开，必须落成字面路径；
4. `enable --now` 两个单元并立刻跑一次心跳。

单元说明：

| 单元 | 作用 | 触发 |
|---|---|---|
| `diting-agent.service` | `drain`：排空队列 | `diting-agent.path` 监听 `data/deploy/queue` 变更 |
| `diting-agent-tick.service` | `tick`：心跳 + 兜底排空 | `diting-agent.timer` 每 5 分钟（`OnBootSec=2min`） |

`.timer` **不能省**：它既是 `/diting status` 的心跳来源，也是 `.path` 漏事件时的兜底。
只装 `.path` 的话插件会因为「心跳过期」拒绝派发（可用 `DITING_DEPLOY_REQUIRE_AGENT_FRESH=0` 关掉这个前置要求）。

### 4.3 两个环境同时使用（prod + dev）

可以，但有三个条件，都不是可选的：

**① 各自一份独立目录（两份 clone）。** `docker-compose.yml` 把 `./data` 挂到 `/app/data`、`./logs` 挂到
`/app/logs`，**不随 `SUFFIX` 变化**。如果在同一个目录里靠 `--project-name` 同时起 prod 和 dev 两个容器，
它们会共享同一个宿主机 `data/`：

- 两个插件往同一个 `queue/` 写作业，「已有任务在执行」的预检会互相挡；
- 执行器按自己那份 `.env` 的 `ENVIRONMENT` 决定重启哪个容器，却会认领到另一个环境的作业 ——
  等于用一套档位去跑两个环境的部署；
- `pull.lock` 哨兵也会互相干扰（一个环境拉代码会顺带暂停另一个的热重载）。

而且 `docker-manager.sh` 本身就是从 `.env` 的 `ENVIRONMENT` 推导容器名/端口/项目名的，
所以**一个目录同一时刻只能服务一个环境**，执行器同理。`install.sh` 会检测到「同一个目录装第二个实例」
并直接拒绝（它知道这个坑）。

**② 用 `--name` 装两份执行器。** 单元名与配置文件都是按实例名区分的：

| | 生产（默认） | 开发（`--name dev`） |
|---|---|---|
| 目录 | `/home/bot/diting/nonebot` | `/home/bot/diting/nonebot-dev` |
| 分支（`.env` 的 `DITING_DEPLOY_BRANCH`） | `master` | `dev/1.0` |
| 单元 | `diting-agent.{service,path,timer}` | `diting-agent-dev.{service,path,timer}` |
| 配置 | `/etc/default/diting-agent` | `/etc/default/diting-agent-dev` |
| QQ 命令 | `/diting ...` | `dev-diting ...`（`.env.dev` 的 `COMMAND_START=["dev-"]`） |

两份实例的队列、状态、日志、哨兵、执行锁**完全隔离**，互不影响。

**③ 权限数据是跨环境共享的 —— 这条最需要留意。** `src/common/permission/` 的 8 张表都没有 `env_tag` 列，
`checker.py` 也不按环境过滤。所以只要两个环境连的是同一个 Bot DB，`diting_deploy:*` 的授权就是共享的：
**在开发环境给某个群或某个人授权，生产环境同样生效。** `SUPERUSERS` 是各环境 `.env` 里各自写的，不受影响。
如果部署权必须严格隔离，只有两条路：两个环境用不同的 `BOT_DB_NAME`，或者只给超管用、不给非超管授权。

另外：如果两个 bot 号在同一个 QQ 群里，`/diting` 会被两个 bot 同时响应（所有命令的通用问题），
建议 dev bot 只放在开发群。

### 4.4 验证

```bash
systemctl status diting-agent.path diting-agent.timer
cat /home/bot/diting/nonebot/data/deploy/state.json     # 应有 local_sha / container / warnings
```

然后在 QQ 里 `/diting status`，应看到 agent 心跳正常、分支与 SHA 与服务器一致。
**先在开发目录跑一次 `/diting pull`**，确认无误再上生产。

单独手动跑一次执行器（排查用）：

```bash
sudo bash scripts/diting-agent.sh heartbeat      # 只刷新心跳
sudo bash scripts/diting-agent.sh drain          # 排空队列
sudo DITING_DEPLOY_DRY_RUN=1 bash scripts/diting-agent.sh drain   # 只走预检与状态写入，不碰 git/docker
```

### 4.5 配置项（`/etc/default/diting-agent`）

见 `deploy/systemd/diting-agent.env.example`。常用：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DITING_DEPLOY_ENV` | 读 `<repo>/.env` 的 `ENVIRONMENT` | `prod` / `dev`，禁止 `local` |
| `DITING_DEPLOY_BUILD_MODE` | `auto` | `auto` 指纹未变且镜像存在则跳过重建；`always` 每次都重建 |
| `DITING_DEPLOY_RELOAD_TIMEOUT` | `120` | pull 后等热重载拉起 worker 的上限秒数 |
| `DITING_DEPLOY_HEALTH_TIMEOUT` | `120` | 重启后等 HTTP 就绪的上限秒数 |
| `DITING_DEPLOY_ALLOW_DIRTY` | `0` | 置 1 允许在工作区有未提交改动时执行（会 `git checkout -f` 丢弃它们） |
| `DITING_DEPLOY_DRY_RUN` | `0` | 置 1 只走预检与状态写入 |
| `DITING_DEPLOY_HEARTBEAT_REMOTE` | `1` | 置 0 心跳不做 `git ls-remote`（省一次网络往返，但看不到落后提交数） |

---

## 5. 排障

下文命令里的 `diting-agent` 是默认实例名；用 `--name dev` 装的第二个实例要把命令里的
`diting-agent` 换成 `diting-agent-dev`（配置文件名同理）。

| 现象 | 原因与处理 |
|---|---|
| QQ 回「宿主机执行器未就绪（找不到 state.json）」 | 执行器没装或没跑。`systemctl status diting-agent.timer`；装完手动 `bash scripts/diting-agent.sh heartbeat` |
| QQ 回「宿主机执行器心跳已过期」 | `.timer` 没启用或挂了。`journalctl -u diting-agent-tick -n 50` |
| QQ 回「⏳ 作业 … 还没被宿主机执行器认领」 | 队列有文件但没人处理：`.path` 没启用，或执行器拿不到执行锁。这是**提醒不是失败**，作业仍会在 `.timer` 下一次触发时（≤5 分钟）被执行并回报真实结果。持续不认领就看 `journalctl -u diting-agent -n 100` 有没有「另一个执行器实例正在运行」 |
| QQ 回「未配置部署分支」 | `.env` 里没有 `DITING_DEPLOY_BRANCH`，或没重启容器让它生效 |
| QQ 回「部署队列目录不可写」 | 属主/权限问题。执行器需以 root 运行，或把 `data/deploy/*` 改 `0777` |
| QQ 回「已有任务在执行」 | `queue/` 或 `running/` 里有残留。执行器正常结束时都会清理；历史残留可手动删除并看 `journalctl` |
| QQ 回「部署锁被占用」 | `data/deploy/pull.lock` 还在。它只应在 `git checkout` 期间存在几秒；一直存在说明执行器被 kill。超过 10 分钟 watcher 会自动忽略它，也可以直接 `rm` |
| pull 报「worker 未在超时内重启」 | **代码有问题**：热重载后 worker 起不来。作业日志与 `docker compose logs` 尾部已经在 `/diting log` 里；修好后重推 |
| pull 成功但消息末尾说「HOT_RELOAD=false，需执行 /diting restart 才会生效」 | 服务器 `.env` 的 `HOT_RELOAD` 不是 `true`。要么改 `.env`（重启容器生效），要么养成 pull 后跟一条 `/diting restart` 的习惯 |
| pull 成功但消息末尾说「本次变更未触及 src/ 与 bot.py，服务无需重启」 | 正常：watcher 只盯 `src/`、`bot.py`、`.env*`，只有文档之类的提交不会触发重启，也不会白等 120 秒 |
| 装第二个环境时 install.sh 直接报错退出 | 它在保护你：检测到已有单元指向同一个目录。两个环境必须各有一份独立 clone（见 4.3），换目录后用 `--name` 再装 |
| pull 成功但代码没变 | 看 `state.json` 的 `behind`；可能是分支配错（`DITING_DEPLOY_BRANCH`）或远端确实没新提交 |
| `state.json` 里 `branch`/`local_sha`/`remote_sha` 全是空、`dirty` 却是 `false` | 执行器读不到 git。`git_ok: false` + `warnings` 里会写明原因（2026-09-15 之后的版本才有这两个字段）。最常见是**执行器以 root 运行而仓库属主是别的用户**（git 的 dubious ownership）—— 新版本已用逐命令 `safe.directory` 解决；老版本会表现为 `/diting pull` 能用但状态全是空、**脏工作区保护静默失效**。手工确认：`sudo git -C <仓库> rev-parse --short HEAD`，若报 `detected dubious ownership` 就是这个原因 |
| `state.json` 报「宿主机 PATH 里找不到 git」 | systemd 服务的 PATH 比登录 shell 窄。确认 `command -v git`（root 身份）能找到，必要时给单元加 `Environment=PATH=/usr/local/bin:/usr/bin:/bin` |
| build 报「跳过重建」 | `BUILD_MODE=auto` 且构建指纹未变（依赖/Dockerfile/webui 都没动）。改 `always` 可强制 |
| 服务起不来，QQ 里没有任何消息 | 已知限制，见下节 |

日志位置：

```bash
journalctl -u diting-agent -n 100            # 最近一次作业（含 git/docker 输出摘要）
journalctl -u diting-agent-tick -n 50        # 心跳
cat <repo>/data/deploy/logs/<job_id>.log     # 单次作业完整日志
```

---

## 6. 已知限制（刻意的边界）

1. **服务起不来时 QQ 里不会有任何消息。** 容器没起来就没人读状态文件 —— 这是物理限制。
   执行器会在作业日志里附上 `docker compose logs` 尾部，服务器上 `journalctl -u diting-agent` 能看到；
   服务恢复后 `/diting status` 也会显示上次任务失败。
2. **不做自动回滚。** 失败时状态里带 `rollback_hint`（可直接复制执行的命令），恢复靠人工。
3. **命令不接受任何参数。** 没有分支、路径、ref、选项 —— 分支只来自 `DITING_DEPLOY_BRANCH`，注入面为零。
   `job_id` 只用于只读查询，且会被用作文件名前会做字符校验。
4. **执行器以 root 运行。** 与容器内 root 保持一致，避免跨 uid 写不动 `data/deploy/*`。
   这是安装时的既定边界，不做用户态隔离。
5. **确认令牌存内存**，进程重启即作废（预期行为）。
6. **`build` 用 `docker-manager.sh restart`（down + up）**，会短暂中断 redis 与 bot 两个容器；
   与现有脚本行为一致，不为本插件单独改重启语义。
7. **不做 WebUI 触发。** 队列本身就是接口，后续加一个 API 端点往里写文件即可，QQ 侧不用动。

## 7. 与 CI/CD 计划的关系

`.zcode/plans/plan-sess_863f2992-*.md` 里的 `scripts/deploy.sh` + Gitee Go 流水线是**另一条** push 即部署的通路，
与本插件并行、互不阻塞：它由 push 触发、有回滚与语法门禁；本插件由人在 QQ 里触发、走同一条
`docker-manager.sh` 执行路径。

两者刻意保持的能力边界一致（分支、`.env` 预检、脏工作区拒绝、`ENVIRONMENT=local` 拒绝、构建指纹），
所以执行器后续可以改成 `deploy.sh` 的薄封装（`drain` 里改调 `bash scripts/deploy.sh --branch ...`），
QQ 侧与协议完全不用动。
