# 谛听部署（diting_deploy）故障排除

面向「QQ 命令没反应 / 作业失败 / 作业无声无息卡住」这类问题。
架构、协议、安装与配置项见 [`docs/diting-deploy.md`](./diting-deploy.md)，本文只讲怎么定位、怎么修。

下文用 `<repo>` 指仓库目录（生产 `/home/bot/diting/nonebot`，开发 `/home/bot/diting/nonebot-dev`）。
默认实例的单元/配置是 `diting-agent*`，第二个实例（`--name dev`）要把它们换成 `diting-agent-dev*`。

---

## 0. 先记住五件事

这五条解释了这个系统 90% 的「怪现象」，看现象之前先过一遍。

**① 插件与执行器是两半，失败特征完全不同。**
容器里没有 git、没有 docker CLI、没有 `.git`、没有 `docker.sock`，插件只能写文件。所以
「QQ 里有回执」只证明插件活着，跟作业能不能成没有半点关系。

**② 执行器进程的退出码永远是 0。**
systemd 的 oneshot 单元不该因为一次业务失败而变红，真正的结果写在
`status/<job_id>.json` 的 `exit_code` 里（0/2/3/4/5/6/8）。查失败永远先看状态文件，不是 `systemctl status`。

**③ systemd 服务看到的环境 ≠ 你的登录 shell。**
没有 `HOME`（git 读不到 `/root/.gitconfig` 与 `/root/.git-credentials`）、`PATH` 更窄（找不到 git/docker）、
`Type=oneshot` 的 `TimeoutStartSec` 是**整条作业**的预算（到点给整个 cgroup 发 SIGTERM，执行器来不及写终态）。
「在我终端里能跑、到执行器就失败」几乎都是这条。复现方法见 §2。

**④ 认领有两条路，所以「没动静」不等于失败。**
`diting-agent.path` 监听队列变更实时触发，`diting-agent.timer` 每 5 分钟兜底 `tick`（心跳 + 排空队列）。
只装 `.timer` 时作业最晚 5 分钟后才被处理，插件会在 90 秒时提醒一次「还没被认领」——
那是**提醒**，不是终态，它仍会继续跟到 30 分钟。

**⑤ 回报是「标记-发送」的幂等操作，而且非终态作业会被反复播报。**
`reported/<job_id>.json` 先落盘再发消息，所以成功结果既不重报也不漏报。
反过来，**没到终态**的作业没有这个标记，于是每次容器重启的启动钩子都会补报一条 🔄 ——
看到重复的 🔄 说明有僵尸作业（§4），而不是同一条命令执行了两次；看到重复的 ✅ 才是异常。

另外一条不用怀疑的事：`journalctl -u diting-agent` 里出现「**另一个执行器实例正在运行**」是**正常的**，
它表示执行锁在起作用（`.path` 触发与 `.timer` 兜底会成对启动，后到的那个拿不到锁就退出）。它不是错误。

---

## 1. 三分钟定位

### 1.1 拿到作业与它的三份证据

QQ 回执里第一行就是 `job_id`（形如 `20260916-144546-pull-ffbf2a`）。忘了就取最近的：

```bash
REPO=/home/bot/diting/nonebot
ls -1t "$REPO"/data/deploy/status | head -5
```

然后按「结论 → 过程 → 系统」三层各看一份：

```bash
JOB=20260916-144546-pull-ffbf2a

# 结论：这次作业的终态、卡在哪一步、退出码、结果字段
cat "$REPO"/data/deploy/status/$JOB.json

# 过程：git / docker 的完整输出（报错原文都在最后几行）
tail -40 "$REPO"/data/deploy/logs/$JOB.log

# 系统：认领、执行锁、systemd 超时、被 SIGTERM
journalctl -u diting-agent -n 100 --no-pager
```

### 1.2 判定矩阵

| 现象 | 先看什么 | 通常属于 |
|---|---|---|
| 机器人**完全静默**（不是回「没有权限」，是啥都不回） | 容器启动日志里的 `[diting_deploy]` warning | 插件：命令没匹配上 matcher |
| 回「没有权限」 | `.env` 的 `SUPERUSERS`、权限组绑定 | 权限层 |
| 回「宿主机执行器未就绪 / 心跳已过期」 | `systemctl status diting-agent.{path,timer}` | 执行器没装、没跑、`.timer` 挂了 |
| 回「⏳ 作业还没被认领」 | `queue/`、`running/`、`journalctl -u diting-agent` | 执行器没被触发，或拿不到执行锁 |
| **1 秒内失败**，`exit_code: 3` | `logs/<job>.log` 里的 git 报错原文 | 宿主机的 git 环境（凭据 / 所有权 / 分支） |
| 长时间没有新日志，`step` 停在 `rebuild` | 日志尾部、`df -h`、`docker system df` | 构建层（源慢 / 磁盘满 / 依赖坏） |
| `state: running` 再也不更新，日志停在半途 | `running/` 是否还有该文件、journal 有无 `timeout` | systemd 超时杀 / 执行器被 kill -9 |
| 收到**重复的 🔄** | `reported/` 里有没有该 job_id | 僵尸作业（§4） |
| 明明成功，却始终没有 ✅ | `reported/<job>.json` 是否存在 | 回报路径（bot 未连上 / 已标记 / 超过一天） |

### 1.3 一键收集证据

报障（或贴给别人/AI）时把这一段的结果带上就够定位了：

```bash
REPO=/home/bot/diting/nonebot
JOB=$(ls -1t "$REPO"/data/deploy/status | head -1); JOB=${JOB%.json}
echo "===== job: $JOB"
cat "$REPO"/data/deploy/status/$JOB.json
echo "===== log tail"; tail -40 "$REPO"/data/deploy/logs/$JOB.log
echo "===== queue / running"; ls -l "$REPO"/data/deploy/queue "$REPO"/data/deploy/running
echo "===== reported 最近几条"; ls -1t "$REPO"/data/deploy/reported | head -5
echo "===== state.json"; cat "$REPO"/data/deploy/state.json
echo "===== units"; systemctl is-active diting-agent.path diting-agent.timer
echo "===== journal"; journalctl -u diting-agent -n 60 --no-pager
```

---

## 2. 复现执行器的运行环境（最有用的一个技巧）

绝大多数「终端里能跑、执行器里不行」都源于 §0③。判断到底是环境差异还是真的坏了，
用 `systemd-run` 把执行器的环境原样复现出来跑一条命令即可。

看执行器实际拿到什么环境：

```bash
sudo systemd-run --wait --pipe --collect \
  -p EnvironmentFile=/etc/default/diting-agent \
  /bin/bash -c 'echo "HOME=${HOME:-<未设置>}"; echo "PATH=$PATH"; \
                echo "credential.helper=$(git config --get-all credential.helper)"; \
                command -v git docker'
```

- `HOME=<未设置>` 且 `credential.helper` 为空 → 执行器读不到 root 的全局 git 配置，
  这既会引发「可疑的仓库所有权」，也会引发「公开仓库也被要求登录」。
- `command -v docker` 没输出 → `PATH` 太窄，需要在单元里补 `Environment=PATH=…`。

再验证「凭据在没有任何 git 全局配置时是否够用」——这正是执行器的处境：

```bash
sudo systemd-run --unit=dg-cred --wait --collect \
  -p WorkingDirectory=<repo> \
  -- /bin/bash -c 'unset HOME; echo "HOME=${HOME:-<未设置>}"; \
       git -c "safe.directory=<repo>" \
           -c "credential.helper=store --file=/root/.git-credentials" \
           ls-remote --heads origin <分支> | head -3'
```

打印 `HOME=<未设置>` 之后还能列出 refs，就说明凭据文件本身没问题，
执行器侧的失败只可能是「没读到这份文件」。若这里也报 `致命错误`，那就是凭据内容本身的问题
（令牌过期、无仓库权限、用户名写错），与执行器无关。

> 换个单元名重跑，或先 `sudo systemctl reset-failed dg-cred`，否则会因同名瞬态单元残留而报错。

---

## 3. 按现象的处置卡

### A. 机器人完全静默

**确认**：容器启动日志里有没有这一条 warning：

```bash
docker compose logs diting-nonebot | grep -i diting_deploy
# [diting_deploy] DITING_DEPLOY_CMD='dev-diting' 已经带了 COMMAND_START 前缀 'dev-'…
```

**根因**：NoneBot 把 `COMMAND_START` 与命令名**拼接**成实际命令（`diting` + `dev-` = `dev-diting`）。
命令名里再写一次前缀就变成 `dev-dev-diting`，不匹配任何 matcher，于是啥都不回。

**修法**：`DITING_DEPLOY_CMD` 保持默认 `diting`，改完 `.env` 重启容器。
自查办法：发一条 `dev-dev-diting`（不带子命令）会回帮助文本，帮助里的命令形态按真实前缀算，直接告诉你正确写法。

### B. 回「没有权限」

- `SUPERUSERS`（各环境 `.env` 里各自写）天然放行，无需配置；
- 其余人在**群聊**里由超管执行：`perm 绑定 群 <群号> diting_deploy`；
- 私聊里群绑定不生效（没有 `group_id`，`checker.py` 会跳过群绑定检查）。

> **跨环境注意**：权限数据没有 `env_tag`，两个环境连同一个 Bot DB 时授权是共享的 ——
> 在开发群授权，生产同样生效。要严格隔离只能换 `BOT_DB_NAME`，或只给超管用。

### C. 回「执行器未就绪」/「心跳已过期」

```bash
systemctl status diting-agent.path diting-agent.timer
journalctl -u diting-agent-tick -n 50 --no-pager
sudo bash scripts/diting-agent.sh heartbeat      # 手动刷一次心跳
```

- 「未就绪（找不到 state.json）」= 执行器没装或没跑过；
- 「心跳已过期」= `.timer` 没启用或挂了（`state.json` 的 `updated_ts` 超过 `DITING_DEPLOY_REQUIRE_AGENT_FRESH`，默认 600 秒）；
- 只装 `.path` 不装 `.timer` 时，把 `DITING_DEPLOY_REQUIRE_AGENT_FRESH=0` 关掉这个前置要求。

### D. 回「未配置部署分支」

`.env` 里没有 `DITING_DEPLOY_BRANCH`，或改完之后没重启容器。分支的取值是级联的：
先 `.env` 再 `.env.<ENVIRONMENT>`，**同名键以 `.env` 为准**（dotenv 不覆盖已存在的变量），
所以为避免踩坑，统一写在 `.env` 里。

### E. ⏳ 一直不被认领

**这是提醒不是失败**，插件会继续跟踪到 30 分钟。

```bash
ls -l <repo>/data/deploy/queue            # 文件还在 = 确实没被认领
journalctl -u diting-agent -n 100 --no-pager
```

- journal 里只有「另一个执行器实例正在运行」→ 有别的作业在跑（执行锁被持有），等它结束；
- journal 里完全没有本次 `drain` 记录 → `.path` 没启用（`systemctl status diting-agent.path`）；
- 兜底：`.timer` 每 5 分钟 `tick` 会排空一次队列，也可以手动 `sudo bash scripts/diting-agent.sh drain`；
- 队列里如果有别人的残留文件，「已有任务在执行」预检会挡住新作业，先清残留。

### F. 秒失败、`exit_code: 3`（git 失败），按日志原文分五种

先取出原文（别猜）：

```bash
grep -m3 -iE "fatal|致命|error" <repo>/data/deploy/logs/<job>.log
```

1. **`could not read Username for 'https://…'`**
   远端要求认证，而执行器手头没有可用凭据。systemd 不设 `HOME`，git 读不到 `/root/.gitconfig`
   里的 `credential.helper=store`，也就找不到 `/root/.git-credentials`；公开仓库也会中招
   （gitee 对匿名请求回 401），表现为 1 秒内失败。
   **修法**：确保 `/root/.git-credentials` 存在、权限 `600`、内容形如
   `https://<用户名>:<私人令牌>@gitee.com`。执行器走**逐命令注入**
   （`-c credential.helper=store --file=<DITING_DEPLOY_GIT_CREDENTIAL_FILE>`），
   不依赖 `HOME`、不改宿主全局配置；文件不存在就不注入。
   区分平台与配置：在交互 shell 里 `sudo GIT_TERMINAL_PROMPT=0 git -C <repo> ls-remote origin`
   能成功而执行器失败，就是这个环境问题（用 §2 的探针确认）。

2. **`detected dubious ownership`**，或 `state.json` 里 `branch`/`sha` 全空而 `dirty: false`
   执行器以 root 运行、仓库属主是别的用户。新版执行器对每次 git 调用都带
   `-c safe.directory=<repo>`，老版本没有，症状是状态全空且**脏工作区保护静默失效**。
   手工确认：`sudo git -C <repo> rev-parse --short HEAD`。

3. **`工作区有未提交改动`**
   预检 fail-closed（`DITING_DEPLOY_ALLOW_DIRTY=0`）。`sudo git -C <repo> status --short` 看清楚，
   要么提交/丢弃，要么临时置 `ALLOW_DIRTY=1` —— 但注意它会 `git checkout -f`，改动直接丢。

4. **分支不存在 / 远端没有该分支**
   `git -C <repo> ls-remote --heads origin <分支>`；再核对 `DITING_DEPLOY_BRANCH`（命令不接受分支参数，这是设计）。

5. **git 命令超时**
   `DITING_DEPLOY_GIT_TIMEOUT`（默认 300 秒）到点被杀。网络问题；必要时调大。

### G. `exit_code: 2`（预检拒绝）

**不会改动任何东西**。常见原因：`ENVIRONMENT=local`（禁止）、`.env` 或 `.env.prod` 是**目录**而不是文件
（compose 短语法在源文件缺失时会创建目录，dotenv 读到空，配置整体静默丢失）、脏工作区、`data/deploy/*` 不可写。

### H. build 长时间没输出，或 `exit_code: 4`

- **正常量级**：一次全量重建实测约 28 分钟（含 playwright chromium 下载），所以单元超时给的是
  `TimeoutStartSec=7200`。半小时没动静不等于卡死。
- `#N <秒数>` 一直涨而 `Get:` 号几乎不动 = apt 源慢。换源按实测选（服务器上 ustc 13.4 MB/s，
  aliyun 只有 327 KB/s），换机器后用 `bash scripts/mirror-speedtest.sh` 重测；该脚本会同时确认候选站有
  `debian-security`（Dockerfile 把安全源也指到同一个站，缺了会 404）。
- `No space left on device` → `df -h /`、`docker system df`，清镜像层前先确认没有在跑的构建。
- `ModuleNotFoundError: pydantic_core` 或 `typing_extensions` 是 0 字节 → 磁盘不足时 pip 留下的坏文件
  （dist-info 完好，pip 误判已安装而不修）。Dockerfile 里那行
  `RUN python -m pip install --force-reinstall --no-deps typing-extensions …` 就是修它的；
  如果你的分支上还没有这行，补上再重建。
- 报「跳过重建」`BUILD_MODE=auto` 且构建指纹未变（依赖 / Dockerfile / `.cpp` / webui 都没动）。要强制就改 `always`。
- 改了 `src/**/*.cpp` 但 pull 后行为没变：原生扩展是在**镜像里**编译的，热重载不会重编译，
  用 `/diting build`（或 `/diting restart`，entrypoint 会发现源码比产物新而就地重编译）。

### I. `exit_code: 5` / `6`（重启、探活）

`5` = `docker-manager.sh restart` 失败；`6` = 重启后 HTTP 在超时内没就绪，pull 还会多一种
「worker 未在超时内重启」——后者基本等于**代码有问题**（语法/导入错误）。证据都在
`logs/<job>.log` 与其中附带的 `docker compose logs` 尾部，修好再重推。

> 服务起不来时 QQ 里不会有任何消息：容器没起来就没人读状态文件。这是已知限制，不是通知丢包。

### J. `state: running` 从此不再更新

```bash
ls -l <repo>/data/deploy/running                    # 还有没有该作业的标记
journalctl -u diting-agent --no-pager | grep -i timeout
systemctl cat diting-agent.service | grep TimeoutStartSec
```

- `TimeoutStartSec` 到点 → 整个 cgroup 被 SIGTERM，执行器来不及写终态。单元里应是 `7200`；
  早期模板误设成 `1800`，正好把 28 分钟的冷构建砍在 export 阶段。
- 被 `kill -9`（断电、OOM）也会留下 `running/` 残留。心跳里的 `cleanup_stale_running` 会在
  **确认没有作业在跑**（用 `flock -n` 试锁判断）时清掉超 30 分钟的残留；有作业在跑时一个都不删，
  免得把在飞作业的标记删掉让后续作业插队。
- 手工清理（先确认执行器确实没在跑）：

```bash
rm -f <repo>/data/deploy/status/<job>.json <repo>/data/deploy/running/<job>.json
```

### K. 收到重复的 🔄

非终态 + 没有 `reported/` 标记 → **每次容器启动**都会被启动钩子重新播报一条 🔄，并重新开始跟踪。
这不是「执行了两次」。按 §4 清掉僵尸作业即可，清干净后就不会再刷。

### L. 明明成功却没有 ✅

```bash
ls -l <repo>/data/deploy/reported/<job>.json
```

- 文件存在 = 插件认为已经报过了。可能是消息发出时 bot 正好离线（`reported/` 是**先标记后发送**，
  发送整体失败才会回滚标记）；也可能是超过一天（86400 秒）的旧任务，启动钩子只标记不打扰。
- 启动补报需要 bot 连接：启动后 180 秒内没连上就顺延到下次启动，仅在日志里留一条 warning。
- 想让它再报一次：删掉该 `reported/<job>.json` 再重启容器（作业仍是终态，会走补报路径）。

---

## 4. 僵尸作业（唯一的「会粘住」的故障）

**判定**：三条同时成立就是僵尸 ——
`status/<job>.json` 存在但**不是终态**（`state` 为 `queued`/`running`）、
`reported/<job>.json` 不存在、`running/<job>.json` 可能还在。

**后果**（比「少一条通知」严重得多）：

1. 每次容器重启都会补报一条 🔄，看起来像命令被重复执行；
2. `running/` 残留会让后续作业撞上「已有任务在执行」预检，一个都排不进来
   （残留超过 30 分钟、且执行器确实空闲时，`cleanup_stale_running` 会自动清掉）；
3. `state.json` 里的「上次任务」永远是这次失败的作业，掩盖后续真实状态。

**成因**：执行器没机会写终态就死了 —— `TimeoutStartSec` 到点被 SIGTERM（历史 1800 秒的坑）、
断电/OOM 被 `kill -9`、或磁盘满导致连状态文件都写不下去。

**清理**：

```bash
REPO=/home/bot/diting/nonebot
JOB=<僵尸作业 id>
ls -l "$REPO"/data/deploy/running            # 确认没有别的作业在跑（有就等它结束）
rm -f "$REPO"/data/deploy/status/$JOB.json "$REPO"/data/deploy/running/$JOB.json
```

顺带确认根因已修（单元超时是不是 7200、磁盘够不够），否则还会再造一个。
**注意**：状态文件删掉后插件就没有可回报的对象了，QQ 里不会再出现这条作业的任何消息，这是预期。

> 想从根上避免「僵尸」这一类，可以让执行器在任何非正常退出路径（收到 SIGTERM/SIGINT）上也写一个
> `failed/interrupted` 终态。当前实现里终端状态只由正常流程写，这一点是已知短板。

---

## 5. 日志与证据位置速查

```bash
# 宿主机（执行器）
journalctl -u diting-agent -n 100 --no-pager        # 最近一次作业（含 git/docker 摘要、锁竞争）
journalctl -u diting-agent-tick -n 50 --no-pager    # 心跳
<repo>/data/deploy/logs/<job_id>.log                # 单次作业完整输出
<repo>/data/deploy/status/<job_id>.json             # 终态与结果
<repo>/data/deploy/state.json                       # 心跳：分支/SHA/容器/警告

# 容器（插件）
docker compose logs --tail 200 diting-nonebot      # 含 [diting_deploy] 的告警与回报记录
```

`state.json` 里两个字段最值钱：`git_ok`（false 说明执行器读不到 git，`warnings` 会写明原因）
与 `behind`（落后远端多少个提交，判断「pull 了但没变」）。

---

## 6. 别再走这些弯路（反模式）

1. **不要用 `systemctl stop diting-agent` 去中断一次 build。** 那会让作业停在非终态、变成僵尸。
   要打断构建就 `pkill -f "compose.*build"`，让执行器自己走完错误分支并写下终态。
2. **不要为了修 ownership / 凭据去改宿主机的全局 git 配置。** 执行器对每次调用都用
   `-c safe.directory=` / `-c credential.helper=…` 逐命令注入：无全局副作用、幂等、换机器行为一致。
   改全局配置还会让「终端里能跑、服务里不能」的差异更难复现。
3. **不要试图把分支写进命令。** 命令不接受任何参数是刻意的设计（分支只来自 `DITING_DEPLOY_BRANCH`，注入面为零）。
4. **不要用 `ENVIRONMENT=local`。** `docker-manager.sh` 会把 `local` 映射成生产档位（容器 `diting-nonebot`、端口 6090）
   却挂载 `.env.local`，档位与配置错配；执行器会直接拒绝这种作业。
5. **不要在生产目录手工 `git checkout` 或改文件。** 脏工作区预检是 fail-closed 的，会让后续 pull 全部失败；
   开 `ALLOW_DIRTY=1` 则是把改动直接丢掉。
6. **不要在容器里找 git / docker。** 镜像里没有，`.git` 与 `scripts/` 也被 `.dockerignore` 排除，这是刻意的边界。
7. **不要在同一个目录里跑两个环境。** `./data` 挂载不随 `SUFFIX` 变化，两个环境的队列、哨兵、执行锁会互相打架；
   `install.sh` 检测到同目录装第二个实例会直接拒绝，它是对的。

---

## 7. 附：上线后 5 分钟验收清单

对一个新装的环境（例如刚上线的生产）按顺序过一遍，全绿就说明链路是通的：

- [ ] `systemctl is-active diting-agent.path diting-agent.timer` 两个都 `active`
- [ ] `cat <repo>/data/deploy/state.json` → `git_ok: true`、`branch` 与远端分支一致、`warnings` 为空
- [ ] `grep -n '^HOME=' /etc/default/diting-agent` 有值，或 §2 的探针能列出 refs（凭据可用）
- [ ] QQ 里发 `/diting status` → 心跳新鲜、SHA 与服务器一致
- [ ] QQ 里发一次 `/diting pull` → 收到 ✅、`exit_code: 0`、`state: succeeded`
- [ ] 收不到 ✅ 时看 `reported/<job>.json` 是否存在（§3-L）
- [ ] 需要给非超管用 → 在群里执行 `perm 绑定 群 <群号> diting_deploy`
