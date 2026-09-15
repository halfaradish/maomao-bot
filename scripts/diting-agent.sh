#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# DiTing 部署执行器（宿主机侧）
#
# 这是 /diting 命令真正干活的一半。容器里没有 git、没有 docker CLI、没有 .git、
# 没有 docker.sock（见 Dockerfile 与 .dockerignore），所以插件只负责鉴权、受理与回报，
# 所有 git / docker 操作都在宿主机上由本脚本完成，结果写回 data/deploy/ 供 bot 回报。
#
# 用法：
#   diting-agent.sh drain       处理队列中的作业（由 diting-agent.path 触发）
#   diting-agent.sh heartbeat   刷新 state.json 心跳（由 diting-agent.timer 触发）
#   diting-agent.sh tick        心跳 + 兜底排空队列（timer 用这个）
#   diting-agent.sh dry-run     只走预检与状态写入，不碰 git/docker（本地验证协议用）
#   diting-agent.sh help        帮助
#
# 配置（环境变量，生产上放 /etc/default/diting-agent，见 deploy/systemd/diting-agent.env.example）：
#   DITING_DEPLOY_ROOT           项目根目录（仓库所在目录）
#   DITING_DEPLOY_ENV            prod|dev，留空则读 $ROOT/.env 的 ENVIRONMENT
#   DITING_DEPLOY_BUILD_MODE     auto（默认，指纹未变则跳过重建）| always
#   DITING_DEPLOY_RELOAD_TIMEOUT 等热重载拉起 worker 的上限秒数（默认 120）
#   DITING_DEPLOY_HEALTH_TIMEOUT 服务探活上限秒数（默认 120）
#   DITING_DEPLOY_ALLOW_DIRTY    1 允许在工作区有未提交改动时执行
#   DITING_DEPLOY_DRY_RUN        1 等价于 dry-run 子命令
#
# 退出码：0 成功 / 2 预检拒绝 / 3 git 失败 / 4 构建失败 / 5 重启失败 / 6 探活失败 / 8 内部错误
# ═══════════════════════════════════════════════════════════════════════════════

set -uo pipefail   # 刻意不用 -e：每一步失败都要落成明确的作业状态，而不是静默中断

AGENT_VERSION="1"
PROTOCOL=1

# ── 定位项目根目录（必须在自我复制之前算出来，因为 exec 后 $0 会变成 /tmp 里的副本） ──
_abspath() { readlink -f "$1" 2>/dev/null || realpath "$1" 2>/dev/null || printf '%s' "$1"; }

[ -r /etc/default/diting-agent ] && . /etc/default/diting-agent

_SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
ROOT="${DITING_DEPLOY_ROOT:-$(cd "$(dirname "$_SELF")/.." && pwd)}"
ROOT="$(_abspath "$ROOT")"

# ── 自保护重入 ────────────────────────────────────────────────────────────────
# 脚本自身就在工作区内，而本脚本会 git checkout 掉整个工作区。bash 是按字节偏移读取
# 脚本文件的，文件被替换后可能执行到乱码内容（CI 里的经典坑），所以先复制到 /tmp 再 exec。
if [ "${_DITING_AGENT_REENTRY:-}" != "1" ]; then
    case "$(_abspath "$_SELF")" in
        "$ROOT"/*)
            _tmp="/tmp/diting-agent.$$.sh"
            if cp "$_SELF" "$_tmp" 2>/dev/null; then
                chmod +x "$_tmp" 2>/dev/null || true
                export _DITING_AGENT_REENTRY=1
                export DITING_DEPLOY_ROOT="$ROOT"
                export _DITING_AGENT_TMP="$_tmp"
                exec bash "$_tmp" "$@"
            fi
            echo "[WARN] 无法自我复制到 /tmp，直接原地执行（git checkout 期间有风险）"
            ;;
    esac
fi

# /tmp 副本的清理与哨兵释放统一交给下面唯一的 EXIT trap（_agent_cleanup）

# ── 路径 ──────────────────────────────────────────────────────────────────────
DEPLOY_DIR="$ROOT/data/deploy"
QUEUE_DIR="$DEPLOY_DIR/queue"
RUNNING_DIR="$DEPLOY_DIR/running"
STATUS_DIR="$DEPLOY_DIR/status"
LOGS_DIR="$DEPLOY_DIR/logs"
STATE_FILE="$DEPLOY_DIR/state.json"
FINGERPRINT_FILE="$DEPLOY_DIR/build.fingerprint"
SENTINEL="$DEPLOY_DIR/pull.lock"
LOCK_FILE="$DEPLOY_DIR/agent.lock"

# ── 配置 ──────────────────────────────────────────────────────────────────────
BUILD_MODE="${DITING_DEPLOY_BUILD_MODE:-auto}"
RELOAD_TIMEOUT="${DITING_DEPLOY_RELOAD_TIMEOUT:-120}"
HEALTH_TIMEOUT="${DITING_DEPLOY_HEALTH_TIMEOUT:-120}"
GIT_TIMEOUT="${DITING_DEPLOY_GIT_TIMEOUT:-300}"
ALLOW_DIRTY="${DITING_DEPLOY_ALLOW_DIRTY:-0}"
DRY_RUN="${DITING_DEPLOY_DRY_RUN:-0}"
HEARTBEAT_REMOTE="${DITING_DEPLOY_HEARTBEAT_REMOTE:-1}"

# ── 作业级全局（每次 process_job 重置） ────────────────────────────────────────
JOB_ID=""
JOB_ACTION=""
JOB_BRANCH=""
JOB_REQUESTED_BY="0"
JOB_SESSION_TYPE="private"
JOB_SESSION_GROUP="null"
JOB_SESSION_USER="0"
JOB_LOG=""
JOB_STARTED_AT=""
JOB_STARTED_TS=""
OLD_SHA=""
NEW_SHA=""
CHANGED_JSON=false
REBUILD_NEEDED_JSON=false
REBUILT_JSON=false
REBUILD_SKIPPED_JSON=false
RESTARTED_JSON=false
RELOADED_JSON=false
ROLLBACK_HINT=""
JOB_REJECT_REASON=""
RELOAD_NOTE=""

# ── 小工具 ────────────────────────────────────────────────────────────────────
log() {
    local line
    line="$(date '+%Y-%m-%dT%H:%M:%S') $*"
    printf '%s\n' "$line"
    [ -n "$JOB_LOG" ] && printf '%s\n' "$line" >>"$JOB_LOG"
}

# 执行外部命令：输出同时进作业日志，返回命令自身的退出码
run_cmd() {
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] $*"
        return 0
    fi
    log "+ $*"
    if [ -n "$JOB_LOG" ]; then
        "$@" 2>&1 | tee -a "$JOB_LOG"
        return "${PIPESTATUS[0]}"
    fi
    "$@" 2>&1
}

with_timeout() { # $1=秒数，其余为命令
    local t="$1"; shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$t" "$@"
    else
        "$@"
    fi
}

# git 包装。执行器以 root 运行（systemd 系统单元）而仓库属主可能是别的用户时，
# git 会以 dubious ownership 直接拒绝工作，症状是 rev-parse / status 全部返回空、
# 而 stderr 被 2>/dev/null 吞掉 —— 极难排查，且会让「脏工作区」保护静默失效。
# 用逐命令的 -c safe.directory 而不是写全局 git config：不改宿主状态、幂等、可重复。
GIT_SAFE=(-c "safe.directory=$ROOT")
gitr() { git "${GIT_SAFE[@]}" -C "$ROOT" "$@"; }

_mtime_of() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }

json_escape() {
    local s="${1:-}"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# 从插件写出的请求/状态文件里取扁平字段。
# 前提：文件由 json.dumps(indent=2) 生成，一键一行，且键在整个文档里唯一
# （session 里的 type/group_id/user_id 都不与顶层重复）。这样就不需要 jq 依赖。
# 先 tr 掉 \r：即使写入方在 Windows 上生成了 CRLF，行尾的 \r 也不会破坏后面的取值。
json_get() { # $1=文件 $2=键
    [ -f "$1" ] || return 0
    sed -n "s/^[[:space:]]*\"$2\"[[:space:]]*:[[:space:]]*//p" "$1" | head -1 \
        | tr -d '\r\n' | sed 's/^"//; s/",\{0,1\}$//; s/,$//; s/"$//'
}

read_env_file() { # $1=文件 $2=键
    [ -f "$1" ] || return 0
    sed -n "s/^[[:space:]]*$2[[:space:]]*=[[:space:]]*//p" "$1" | tail -1 \
        | tr -d '\r' | sed "s/^['\"]//; s/['\"]$//" | tr -d ' '
}

# 读取一个「插件侧」配置项，文件顺序与容器内 local_config.py 的加载顺序一致：
# .env 先加载、.env.<ENV> 后加载，而 python-dotenv 默认不覆盖已存在的环境变量，
# 所以同名键以 .env 为准，.env.<ENV> 只补前者没有的键。
read_app_config() { # $1=键
    local value
    value="$(read_env_file "$ROOT/.env" "$1")"
    if [ -z "$value" ]; then
        value="$(read_env_file "$ROOT/.env.$ENVIRONMENT" "$1")"
    fi
    printf '%s' "$value"
}

SHA_TOOL=""
if command -v sha256sum >/dev/null 2>&1; then SHA_TOOL="sha256sum"
elif command -v shasum >/dev/null 2>&1; then SHA_TOOL="shasum -a 256"
fi
sha256_file() { [ -n "$SHA_TOOL" ] && $SHA_TOOL "$1" 2>/dev/null | awk '{print $1}'; }
sha256_stdin() { [ -n "$SHA_TOOL" ] && $SHA_TOOL 2>/dev/null | awk '{print $1}'; }

ensure_dirs() {
    local d
    for d in "$QUEUE_DIR" "$RUNNING_DIR" "$STATUS_DIR" "$LOGS_DIR"; do
        mkdir -p "$d" 2>/dev/null || true
        chmod 0777 "$d" 2>/dev/null || true
    done
    chmod 0666 "$DEPLOY_DIR/build.fingerprint" 2>/dev/null || true
}

# ── 环境推导 ──────────────────────────────────────────────────────────────────
ENVIRONMENT="${DITING_DEPLOY_ENV:-$(read_env_file "$ROOT/.env" ENVIRONMENT)}"
ENVIRONMENT="${ENVIRONMENT:-prod}"
ENVIRONMENT_INVALID=0
SUFFIX=""
case "$ENVIRONMENT" in
    dev|development) ENVIRONMENT="dev"; SUFFIX="-dev" ;;
    prod|production) ENVIRONMENT="prod"; SUFFIX="" ;;
    *) ENVIRONMENT_INVALID=1; SUFFIX="" ;;
esac
CONTAINER="diting-nonebot${SUFFIX}"
IMAGE="diting-nonebot${SUFFIX}:latest"
HOT_RELOAD="$(read_app_config HOT_RELOAD)"
[ -z "$HOT_RELOAD" ] && HOT_RELOAD="false"

# ── 部署哨兵：容器内 bot.py 的 watcher 看到它就推迟重启 worker ─────────────────
sentinel_on() {
    printf '%s %s\n' "$(date +%s)" "$$" >"$SENTINEL" 2>/dev/null || true
    log "部署哨兵已开启：$SENTINEL"
}
sentinel_off() {
    rm -f "$SENTINEL" 2>/dev/null || true
}

# 单一 EXIT trap：sentinel_off 与 /tmp 副本清理必须挂在同一个 trap 上，
# 挂两个会互相覆盖（后一个替换前一个）
_agent_cleanup() {
    sentinel_off
    if [ -n "${_DITING_AGENT_TMP:-}" ]; then
        rm -f "$_DITING_AGENT_TMP" 2>/dev/null || true
    fi
}
trap '_agent_cleanup' EXIT

# ── 执行锁 ────────────────────────────────────────────────────────────────────
acquire_lock() {
    if command -v flock >/dev/null 2>&1; then
        exec 200>"$LOCK_FILE"
        flock -n 200 || return 1
        return 0
    fi
    # 退路：mkdir 的原子性 + 30 分钟超龄回收（脚本被 kill -9 时会留下目录）
    if mkdir "$LOCK_FILE.d" 2>/dev/null; then return 0; fi
    local age
    age=$(( $(date +%s) - $(_mtime_of "$LOCK_FILE.d") ))
    if [ "$age" -gt 1800 ]; then
        log "回收超龄执行锁（${age}s）"
        rmdir "$LOCK_FILE.d" 2>/dev/null || true
        mkdir "$LOCK_FILE.d" 2>/dev/null && return 0
    fi
    return 1
}
release_lock() {
    command -v flock >/dev/null 2>&1 && return 0
    rmdir "$LOCK_FILE.d" 2>/dev/null || true
}

# ── 状态写入（原子：先写 .json.tmp 再 mv，插件按 *.json 通配不会读到半成品） ──
write_status() { # $1=state $2=step $3=message [$4=exit_code]
    local state="$1" step="$2" message="$3" code="${4:-}"
    local now_iso now_ts started_at started_ts finished_at finished_ts exit_json
    now_iso="$(date '+%Y-%m-%dT%H:%M:%S')"
    now_ts="$(date +%s)"
    started_at="${JOB_STARTED_AT:-$now_iso}"
    started_ts="${JOB_STARTED_TS:-$now_ts}"
    finished_at="null"; finished_ts="0"
    case "$state" in
        succeeded|failed|rejected) finished_at="\"$now_iso\""; finished_ts="$now_ts" ;;
    esac
    exit_json="null"
    [ -n "$code" ] && exit_json="$code"

    local tmp="$STATUS_DIR/$JOB_ID.json.tmp"
    cat >"$tmp" <<EOF
{
  "protocol": $PROTOCOL,
  "job_id": "$JOB_ID",
  "action": "$JOB_ACTION",
  "state": "$state",
  "step": "$step",
  "message": "$(json_escape "$message")",
  "exit_code": $exit_json,
  "requested_by": $JOB_REQUESTED_BY,
  "session": {
    "type": "$(json_escape "$JOB_SESSION_TYPE")",
    "group_id": $JOB_SESSION_GROUP,
    "user_id": $JOB_SESSION_USER
  },
  "branch": "$(json_escape "$JOB_BRANCH")",
  "started_at": "$started_at",
  "started_ts": $started_ts,
  "updated_at": "$now_iso",
  "updated_ts": $now_ts,
  "finished_at": $finished_at,
  "finished_ts": $finished_ts,
  "result": {
    "old_sha": "$OLD_SHA",
    "new_sha": "$NEW_SHA",
    "changed": $CHANGED_JSON,
    "rebuild_needed": $REBUILD_NEEDED_JSON,
    "rebuilt": $REBUILT_JSON,
    "rebuild_skipped": $REBUILD_SKIPPED_JSON,
    "restarted": $RESTARTED_JSON,
    "reloaded": $RELOADED_JSON,
    "rollback_hint": "$(json_escape "$ROLLBACK_HINT")"
  },
  "log_file": "logs/$JOB_ID.log"
}
EOF
    mv -f "$tmp" "$STATUS_DIR/$JOB_ID.json"
}

# ── 预检 ──────────────────────────────────────────────────────────────────────
do_preflight() {
    if [ "$ENVIRONMENT_INVALID" = "1" ]; then
        echo "ENVIRONMENT=$ENVIRONMENT 不受支持：只允许 prod / dev。local 会被 docker-manager.sh 映射成生产档位（容器 diting-nonebot、6090）却挂载 .env.local，档位与配置错配，必须拒绝。"
        return 1
    fi
    if [ ! -d "$ROOT" ]; then
        echo "项目目录不存在：$ROOT"
        return 1
    fi
    # compose 短语法挂载在源文件缺失时会创建同名「目录」，而 local_config.py 用
    # os.path.exists 判断（目录也为真），会打印 successful load 但 dotenv 实际读到空 —— 配置整体静默丢失
    if [ ! -f "$ROOT/.env" ]; then
        echo "缺少普通文件 $ROOT/.env（若存在同名目录请先删除）"
        return 1
    fi
    if [ ! -f "$ROOT/.env.$ENVIRONMENT" ]; then
        echo "缺少普通文件 $ROOT/.env.$ENVIRONMENT（若存在同名目录请先删除）"
        return 1
    fi
    if [ -f "$ROOT/docker-compose.yml" ] || [ -f "$ROOT/docker-compose.yaml" ]; then
        :
    else
        echo "缺少 docker-compose.yml"
        return 1
    fi

    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] 跳过 docker / git 可用性检查"
        return 0
    fi
    if ! command -v docker >/dev/null 2>&1; then
        echo "宿主机找不到 docker 命令"
        return 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        echo "docker compose 不可用"
        return 1
    fi
    if ! command -v git >/dev/null 2>&1; then
        echo "宿主机找不到 git 命令"
        return 1
    fi
    if [ ! -d "$ROOT/.git" ]; then
        echo "缺少 $ROOT/.git，无法拉取代码"
        return 1
    fi
    return 0
}

check_worktree_clean() {
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] 跳过工作区干净检查"
        return 0
    fi
    if [ "$ALLOW_DIRTY" = "1" ]; then
        log "DITING_DEPLOY_ALLOW_DIRTY=1，跳过工作区干净检查"
        return 0
    fi
    # 必须 fail-closed：git 读不出来时如果不报错就当作「干净」，
    # 后面的 checkout -f 会静默丢掉服务器上的手工改动
    local dirty rc
    dirty="$(gitr status --porcelain 2>&1)"
    rc=$?
    if [ "$rc" != "0" ]; then
        echo "无法读取工作区状态（git status 失败），拒绝执行，以免误丢服务器上的改动："
        printf '%s\n' "$dirty" | head -5
        echo "常见原因：执行器以 root 运行而仓库属主不是 root，或宿主机 PATH 里没有 git"
        return 1
    fi
    if [ -n "$dirty" ]; then
        echo "工作区有未提交改动，拒绝执行（git checkout -f 会摧毁服务器上的手工改动）："
        printf '%s\n' "$dirty" | head -20
        echo "确认可以丢弃时，在对应实例的 /etc/default/diting-agent* 里设 DITING_DEPLOY_ALLOW_DIRTY=1"
        return 1
    fi
    return 0
}

# ── 步骤实现 ──────────────────────────────────────────────────────────────────
do_checkout() {
    if [ "$DRY_RUN" = "1" ]; then
        OLD_SHA="dry-run-old"; NEW_SHA="dry-run-new"
        CHANGED_JSON=true
        log "[dry-run] 跳过 git fetch / checkout"
        sleep 1
        return 0
    fi
    # 注：repo 的 safe.directory 由 gitr() 逐命令带上，这里不再改全局 git config
    OLD_SHA="$(gitr rev-parse --short HEAD 2>/dev/null)"
    write_status running git-fetch "拉取远端 origin"
    run_cmd with_timeout "$GIT_TIMEOUT" git "${GIT_SAFE[@]}" -C "$ROOT" fetch --prune origin || return 3

    write_status running git-checkout "切换到 $JOB_BRANCH"
    run_cmd with_timeout "$GIT_TIMEOUT" git "${GIT_SAFE[@]}" -C "$ROOT" checkout -f -B "$JOB_BRANCH" "origin/$JOB_BRANCH" || return 3

    NEW_SHA="$(gitr rev-parse --short HEAD 2>/dev/null)"
    if [ -n "$OLD_SHA" ] && [ "$OLD_SHA" = "$NEW_SHA" ]; then
        CHANGED_JSON=false
    else
        CHANGED_JSON=true
    fi
    ROLLBACK_HINT="cd $ROOT && git checkout -f ${OLD_SHA:-<上一个SHA>} && bash scripts/docker-manager.sh build && bash scripts/docker-manager.sh restart"
    log "代码：${OLD_SHA:-未知} → ${NEW_SHA:-未知}（分支 $JOB_BRANCH，changed=$CHANGED_JSON）"
    return 0
}

compute_fingerprint() {
    [ -n "$SHA_TOOL" ] || return 1
    local files=(requirements.txt Dockerfile .dockerignore pyproject.toml poetry.lock scripts/entrypoint.sh webui/package.json webui/package-lock.json)
    local out="" f
    for f in "${files[@]}"; do
        if [ -f "$ROOT/$f" ]; then
            out+="$f:$(sha256_file "$ROOT/$f")"$'\n'
        fi
    done
    out+="webui:$(gitr rev-parse HEAD:webui 2>/dev/null || echo none)"
    printf '%s' "$out" | sha256_stdin
}

do_rebuild() { # 返回 0=成功（可能跳过） 4=构建失败
    local current="" stored=""
    current="$(compute_fingerprint)"
    if [ -z "$current" ]; then
        log "无法计算构建指纹（宿主机缺少 sha256sum/shasum），将直接重建"
    fi

    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] 跳过镜像构建（BUILD_MODE=$BUILD_MODE）"
        REBUILD_NEEDED_JSON=true
        sleep 1
        return 0
    fi

    if [ "$BUILD_MODE" = "auto" ] && [ -n "$current" ] && [ -f "$FINGERPRINT_FILE" ]; then
        stored="$(cat "$FINGERPRINT_FILE" 2>/dev/null)"
        if [ "$stored" = "$current" ] && docker image inspect "$IMAGE" >/dev/null 2>&1; then
            REBUILD_SKIPPED_JSON=true
            log "构建指纹未变且镜像存在，跳过重建（BUILD_MODE=always 可强制重建）"
            return 0
        fi
    fi

    REBUILD_NEEDED_JSON=true
    write_status running rebuild "重建镜像 $IMAGE"
    run_cmd bash "$ROOT/scripts/docker-manager.sh" build || return 4
    REBUILT_JSON=true
    if [ -n "$current" ]; then
        printf '%s' "$current" >"$FINGERPRINT_FILE" 2>/dev/null || true
        chmod 0666 "$FINGERPRINT_FILE" 2>/dev/null || true
    fi
    return 0
}

do_restart() {
    RESTARTED_JSON=true
    write_status running restart "重启服务（docker-manager.sh restart）"
    run_cmd bash "$ROOT/scripts/docker-manager.sh" restart || return 5
    return 0
}

container_host_port() {
    local name
    name="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -x "$CONTAINER" | head -1)"
    if [ -n "$name" ]; then
        docker port "$name" 6090/tcp 2>/dev/null | head -1 | sed 's/.*://'
    fi
}

http_get() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -fsS -o /dev/null -m 2 "$url" >/dev/null 2>&1
        return $?
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$url" >/dev/null 2>&1 <<'PY'
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=2).read(1)
PY
        return $?
    fi
    local hp host port
    hp="${url#http://}"; host="${hp%%:*}"; port="${hp#*:}"; port="${port%%/*}"
    (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null
}

wait_healthy() { # 返回 0=就绪 6=超时
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] 跳过服务探活"
        sleep 1
        return 0
    fi
    write_status running health "等待服务就绪（上限 ${HEALTH_TIMEOUT}s）"
    local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        local port
        port="$(container_host_port)"
        if [ -n "$port" ] && http_get "http://127.0.0.1:$port/"; then
            log "服务已就绪：容器 $CONTAINER 端口 $port"
            return 0
        fi
        sleep 5
    done
    log "等待 ${HEALTH_TIMEOUT}s 后服务仍未就绪"
    return 6
}

watched_paths_changed() {
    [ -z "$OLD_SHA" ] && return 0
    [ -z "$NEW_SHA" ] && return 0
    local out
    out="$(gitr diff --name-only "$OLD_SHA" "$NEW_SHA" -- src bot.py 2>/dev/null | head -1)"
    [ -n "$out" ]
}

wait_for_reload() { # 返回 0=热重载已生效或不需要 6=worker 未在超时内起来
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] 跳过热重载校验"
        RELOADED_JSON=true
        sleep 1
        return 0
    fi
    if [ "$HOT_RELOAD" != "true" ]; then
        log "HOT_RELOAD != true：拉取不会自动生效，需要 /diting restart（或把 .env 的 HOT_RELOAD 设为 true）"
        RELOAD_NOTE="HOT_RELOAD=false，需执行 /diting restart 才会生效"
        return 0
    fi
    if [ "$CHANGED_JSON" != "true" ]; then
        log "代码无变化，无需等待热重载"
        RELOADED_JSON=true
        return 0
    fi
    if ! watched_paths_changed; then
        log "变更未触及 src/ 或 bot.py，watcher 不会重启（正常情况）"
        RELOAD_NOTE="本次变更未触及 src/ 与 bot.py，服务无需重启"
        return 0
    fi

    write_status running reload "等待热重载拉起 worker（上限 ${RELOAD_TIMEOUT}s）"
    local boot_file="$DEPLOY_DIR/boot.json"
    local base deadline
    base="$(_mtime_of "$boot_file")"
    deadline=$(( $(date +%s) + RELOAD_TIMEOUT ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if [ "$(_mtime_of "$boot_file")" -gt "$base" ]; then
            RELOADED_JSON=true
            log "boot.json 已刷新，热重载生效"
            return 0
        fi
        sleep 2
    done
    log "等待 ${RELOAD_TIMEOUT}s 后 boot.json 仍未刷新：worker 可能因代码错误起不来"
    return 6
}

# ── 单个作业 ──────────────────────────────────────────────────────────────────
process_job() {
    local job_file="$1"

    JOB_ID="$(json_get "$job_file" job_id)"
    # job_id 会被用作文件名，任何不在白名单里的字符都退回用文件名兜底
    case "$JOB_ID" in
        ''|*[!A-Za-z0-9._-]*) JOB_ID="$(basename "$job_file" .json)" ;;
    esac
    JOB_ACTION="$(json_get "$job_file" action)"
    JOB_BRANCH="$(json_get "$job_file" branch)"
    JOB_REQUESTED_BY="$(json_get "$job_file" requested_by)"
    JOB_SESSION_TYPE="$(json_get "$job_file" type)"
    JOB_SESSION_GROUP="$(json_get "$job_file" group_id)"
    JOB_SESSION_USER="$(json_get "$job_file" user_id)"

    case "$JOB_SESSION_TYPE" in group|private) ;; *) JOB_SESSION_TYPE="private" ;; esac
    case "$JOB_SESSION_GROUP" in ''|null) JOB_SESSION_GROUP="null" ;; *) [[ "$JOB_SESSION_GROUP" =~ ^[0-9]+$ ]] || JOB_SESSION_GROUP="null" ;; esac
    case "$JOB_REQUESTED_BY" in ''|*[!0-9]*) JOB_REQUESTED_BY="0" ;; esac
    case "$JOB_SESSION_USER" in ''|*[!0-9]*) JOB_SESSION_USER="0" ;; esac

    JOB_LOG="$LOGS_DIR/$JOB_ID.log"
    : >"$JOB_LOG" 2>/dev/null || true
    JOB_STARTED_AT="$(date '+%Y-%m-%dT%H:%M:%S')"
    JOB_STARTED_TS="$(date +%s)"
    OLD_SHA=""; NEW_SHA=""
    CHANGED_JSON=false; REBUILD_NEEDED_JSON=false; REBUILT_JSON=false
    REBUILD_SKIPPED_JSON=false; RESTARTED_JSON=false; RELOADED_JSON=false
    ROLLBACK_HINT=""; JOB_REJECT_REASON=""; RELOAD_NOTE=""

    log "══════════════════════════════════════════════"
    log "开始作业 $JOB_ID｜action=$JOB_ACTION｜branch=$JOB_BRANCH｜env=$ENVIRONMENT｜by=$JOB_REQUESTED_BY"

    local rc=0

    # 1) 动作与参数校验 —— 即使请求文件是手工伪造的，也在这里被挡住
    case "$JOB_ACTION" in
        pull|build|restart) ;;
        *)
            JOB_REJECT_REASON="未知动作：$JOB_ACTION"
            log "拒绝：未知动作 $JOB_ACTION"
            rc=2
            ;;
    esac

    if [ "$rc" = "0" ] && [ "$JOB_ACTION" != "restart" ]; then
        if [ -z "$JOB_BRANCH" ]; then
            JOB_REJECT_REASON="作业未携带分支（请在服务器 .env 配置 DITING_DEPLOY_BRANCH）"
            rc=2
        elif ! printf '%s' "$JOB_BRANCH" | grep -Eq '^[A-Za-z0-9._/-]+$'; then
            JOB_REJECT_REASON="分支名非法：$JOB_BRANCH"
            rc=2
        fi
    fi

    # 2) 预检
    if [ "$rc" = "0" ]; then
        write_status running preflight "预检中"
        local err
        if ! err="$(do_preflight)"; then
            JOB_REJECT_REASON="$err"
            log "预检失败：$err"
            rc=2
        fi
    fi

    if [ "$rc" = "0" ] && [ "$JOB_ACTION" != "restart" ]; then
        local derr
        if ! derr="$(check_worktree_clean)"; then
            JOB_REJECT_REASON="$derr"
            log "拒绝：工作区不干净"
            rc=2
        fi
    fi

    # 3) 拉取 + 重建（哨兵覆盖全部工作区改写动作，避免 watcher 在半同步状态重启 worker）
    if [ "$rc" = "0" ] && [ "$JOB_ACTION" != "restart" ]; then
        sentinel_on
        do_checkout || rc=$?
        if [ "$rc" = "0" ] && [ "$JOB_ACTION" = "build" ]; then
            do_rebuild || rc=$?
        fi
        sentinel_off
    fi

    # 4) pull 的热重载校验（build/restart 会重建容器，不需要）
    if [ "$rc" = "0" ] && [ "$JOB_ACTION" = "pull" ]; then
        wait_for_reload || rc=$?
    fi

    # 5) 重启 + 探活
    if [ "$rc" = "0" ] && [ "$JOB_ACTION" != "pull" ]; then
        do_restart || rc=$?
        if [ "$rc" = "0" ]; then
            wait_healthy || rc=$?
        fi
    fi

    # 6) 落终态
    local final_state="succeeded" final_step="done" final_msg=""
    case "$rc" in
        0)
            final_state="succeeded"
            case "$JOB_ACTION" in
                pull)
                    if [ "$CHANGED_JSON" = "true" ]; then
                        final_msg="已更新到 $NEW_SHA"
                        if [ "$RELOADED_JSON" = "true" ]; then
                            final_msg="$final_msg，热重载已生效"
                        elif [ -n "$RELOAD_NOTE" ]; then
                            # 关键：没生效时必须让 QQ 里的人看到原因，否则会以为已经上线了
                            final_msg="$final_msg，$RELOAD_NOTE"
                        fi
                    else
                        final_msg="远端无新提交，已是最新（$NEW_SHA）"
                    fi
                    ;;
                build) final_msg="代码与镜像已就绪，服务探活通过" ;;
                restart) final_msg="服务已重启，探活通过" ;;
            esac
            ;;
        2) final_state="rejected"; final_step="preflight"; final_msg="${JOB_REJECT_REASON:-预检未通过，未改动任何东西}" ;;
        3) final_state="failed"; final_step="git-checkout"; final_msg="拉取或切换分支失败" ;;
        4) final_state="failed"; final_step="rebuild"; final_msg="镜像构建失败" ;;
        5) final_state="failed"; final_step="restart"; final_msg="服务重启失败" ;;
        6)
            final_state="failed"
            if [ "$JOB_ACTION" = "pull" ]; then
                final_step="reload"
                final_msg="拉取完成但 worker 未在 ${RELOAD_TIMEOUT}s 内重启（代码可能有错，服务可能未恢复）"
            else
                final_step="health"
                final_msg="服务未在 ${HEALTH_TIMEOUT}s 内就绪"
            fi
            ;;
        *) final_state="failed"; final_msg="执行器内部错误（退出码 $rc）" ;;
    esac

    if [ "$rc" != "0" ] && [ "$final_state" != "rejected" ]; then
        # 被预检拒绝的作业根本没碰过容器，dump 容器日志只会增加噪音
        log "---- 失败，附带容器日志尾部 ----"
        if command -v docker >/dev/null 2>&1 && [ "$DRY_RUN" != "1" ]; then
            with_timeout 30 docker compose --project-name "$CONTAINER" logs --tail=100 2>&1 | tail -60 | tee -a "$JOB_LOG" >/dev/null || true
            docker logs --tail=100 "$CONTAINER" 2>&1 | tail -60 >>"$JOB_LOG" || true
        fi
    fi

    write_status "$final_state" "$final_step" "$final_msg" "$rc"
    log "作业 $JOB_ID 结束：$final_state（rc=$rc）耗时 $(( $(date +%s) - JOB_STARTED_TS ))s"
    log "══════════════════════════════════════════════"

    # 完成后必须撤下 running 标记：残留会让插件的「已有任务在执行」预检永久拒绝新作业
    rm -f "$RUNNING_DIR/$JOB_ID.json" 2>/dev/null || true
    return 0
}

# ── 排空队列 ──────────────────────────────────────────────────────────────────
cmd_drain() {
    ensure_dirs
    if ! acquire_lock; then
        log "另一个执行器实例正在运行，本次跳过（作业仍留在队列里）"
        return 0
    fi

    local processed=0 job_file base
    while :; do
        job_file="$(ls -1 "$QUEUE_DIR"/*.json 2>/dev/null | sort | head -1)"
        [ -z "$job_file" ] && break
        base="$(basename "$job_file")"
        if ! mv -f "$job_file" "$RUNNING_DIR/$base" 2>/dev/null; then
            log "认领失败（可能已被处理）：$base"
            break
        fi
        process_job "$RUNNING_DIR/$base" || true
        processed=$((processed + 1))
        if [ "$processed" -ge 10 ]; then
            log "单次最多处理 10 个作业，剩余留待下次触发"
            break
        fi
    done

    release_lock
    log "本次排空结束，处理 $processed 个作业"
    return 0
}

# ── 心跳 ──────────────────────────────────────────────────────────────────────
cleanup_stale_running() {
    # 执行器被 kill -9 时 running/ 会残留，超过 30 分钟且状态非 running 的清掉
    local f age
    for f in "$RUNNING_DIR"/*.json; do
        [ -f "$f" ] || continue
        age=$(( $(date +%s) - $(_mtime_of "$f") ))
        [ "$age" -le 1800 ] && continue
        local state
        state="$(json_get "$f" state)"
        if [ "$state" = "running" ] || [ -z "$state" ]; then
            log "清理超龄 running 残留（${age}s）：$(basename "$f")"
            rm -f "$f" 2>/dev/null || true
        fi
    done
}

cmd_heartbeat() {
    ensure_dirs
    cleanup_stale_running 2>/dev/null || true

    # 全部给初值：`local x` 不赋值在 set -u 下等于「未绑定」，一旦某条分支没走到就会
    # 让整个心跳崩掉（而不是给出空值）
    local now_iso now_ts branch="" local_sha="" local_full="" remote_full="" remote_sha="" behind=0
    local dirty=false dirs_ok=true container_state="" hot_reload="$HOT_RELOAD"
    local git_ok=true git_err=""
    now_iso="$(date '+%Y-%m-%dT%H:%M:%S')"
    now_ts="$(date +%s)"

    # git 读不出来时必须显式说出来。否则 state.json 里 branch/sha 全是空字符串、
    # dirty 还会假报 false，光看文件根本查不出问题（on-call 噩梦）。
    if ! command -v git >/dev/null 2>&1; then
        git_ok=false
        git_err="宿主机 PATH 里找不到 git（systemd 服务的 PATH 比登录 shell 窄，必要时给单元加 Environment=PATH=...）"
    elif [ ! -d "$ROOT/.git" ]; then
        git_ok=false
        git_err="$ROOT 不是 git 仓库（缺少 .git），无法拉取代码"
    fi

    if [ "$git_ok" = "true" ]; then
        branch="$(gitr rev-parse --abbrev-ref HEAD 2>/dev/null)"
        local_sha="$(gitr rev-parse --short HEAD 2>/dev/null)"
        local_full="$(gitr rev-parse HEAD 2>/dev/null)"
        if [ -z "$local_full" ]; then
            git_ok=false
            git_err="$(gitr rev-parse HEAD 2>&1 | head -1)"
            [ -z "$git_err" ] && git_err="git 无法读取 $ROOT 的 HEAD（原因未知）"
        elif [ -n "$(gitr status --porcelain 2>/dev/null | head -1)" ]; then
            dirty=true
        fi
    fi
    [ -z "$branch" ] && branch="$(read_app_config DITING_DEPLOY_BRANCH)"

    remote_sha=""
    if [ "$HEARTBEAT_REMOTE" = "1" ] && [ -n "$branch" ]; then
        remote_full="$(with_timeout 15 git "${GIT_SAFE[@]}" -C "$ROOT" ls-remote origin "refs/heads/$branch" 2>/dev/null | awk '{print $1}' | head -1)"
        [ -n "$remote_full" ] && remote_sha="${remote_full:0:7}"
    fi
    if [ -n "$local_full" ] && [ -n "$remote_full" ] && [ "$remote_full" != "$local_full" ]; then
        behind="$(gitr rev-list --count "$local_full..$remote_full" 2>/dev/null || echo 0)"
    else
        behind=0
    fi

    container_state="$(with_timeout 10 docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null)"
    [ -z "$container_state" ] && container_state="not-found"

    local d
    for d in "$QUEUE_DIR" "$RUNNING_DIR" "$STATUS_DIR" "$LOGS_DIR"; do
        if ! touch "$d/.write_probe" 2>/dev/null; then
            dirs_ok=false
            break
        fi
        rm -f "$d/.write_probe" 2>/dev/null || true
    done

    local sentinel_present=false sentinel_age=0 age
    if [ -f "$SENTINEL" ]; then
        sentinel_present=true
        age=$(( now_ts - $(_mtime_of "$SENTINEL") ))
        [ "$age" -lt 0 ] && age=0
        sentinel_age="$age"
    fi

    # 诊断信息：这些是部署最容易踩的坑，直接摆到 /diting status 的第一屏
    local warnings=() w redis_host
    redis_host="$(read_app_config NEW_OJ_REDIS_HOST)"
    case "$redis_host" in
        localhost|127.0.0.1) warnings+=("NEW_OJ_REDIS_HOST=$redis_host 在容器内指向自身，Redis 不可达，应改为 compose 服务名 diting-redis") ;;
    esac
    [ "$ENVIRONMENT_INVALID" = "1" ] && warnings+=("ENVIRONMENT=$ENVIRONMENT 不受支持（只允许 prod/dev），执行器会拒绝作业")
    [ -z "$(read_app_config DITING_DEPLOY_BRANCH)" ] && warnings+=("未在 .env 或 .env.$ENVIRONMENT 配置 DITING_DEPLOY_BRANCH，/diting pull 与 build 会被拒绝")
    [ "$git_ok" = "false" ] && warnings+=("$git_err")
    [ "$hot_reload" != "true" ] && warnings+=("HOT_RELOAD!=true：pull 拉完不会自动生效，需要 /diting restart")
    [ "$dirs_ok" = "false" ] && warnings+=("部署目录不可写，执行器需以 root 运行（或把 data/deploy/* 改为 0777）")

    local warn_json="[]" count=0
    for w in ${warnings[@]+"${warnings[@]}"}; do
        [ "$count" -eq 0 ] && warn_json="[" || warn_json+=","
        warn_json+="\"$(json_escape "$w")\""
        count=$((count + 1))
    done
    [ "$count" -gt 0 ] && warn_json+="]"

    local last_file last_job_id="" last_action="" last_state="" last_finished_ts=0
    last_file="$(ls -1t "$STATUS_DIR"/*.json 2>/dev/null | head -1)"
    if [ -n "$last_file" ]; then
        last_job_id="$(json_get "$last_file" job_id)"
        last_action="$(json_get "$last_file" action)"
        last_state="$(json_get "$last_file" state)"
        last_finished_ts="$(json_get "$last_file" finished_ts)"
        case "$last_finished_ts" in ''|*[!0-9]*) last_finished_ts=0 ;; esac
    fi

    local pending
    pending="$(( $(ls -1 "$QUEUE_DIR"/*.json 2>/dev/null | wc -l) + $(ls -1 "$RUNNING_DIR"/*.json 2>/dev/null | wc -l) ))"

    local tmp="$STATE_FILE.tmp"
    cat >"$tmp" <<EOF
{
  "protocol": $PROTOCOL,
  "agent_version": "$AGENT_VERSION",
  "updated_at": "$now_iso",
  "updated_ts": $now_ts,
  "host": "$(json_escape "$(hostname 2>/dev/null)")",
  "env": "$ENVIRONMENT",
  "root": "$(json_escape "$ROOT")",
  "branch": "$(json_escape "$branch")",
  "local_sha": "$(json_escape "$local_sha")",
  "local_sha_full": "$(json_escape "$local_full")",
  "remote_sha": "$(json_escape "$remote_sha")",
  "behind": $behind,
  "dirty": $dirty,
  "git_ok": $git_ok,
  "hot_reload": $hot_reload,
  "build_mode": "$BUILD_MODE",
  "container": {
    "name": "$CONTAINER",
    "state": "$container_state"
  },
  "image": "$IMAGE",
  "dirs_writable": $dirs_ok,
  "pending_jobs": $pending,
  "sentinel": {
    "present": $sentinel_present,
    "age_sec": $sentinel_age
  },
  "last_job": {
    "job_id": "$(json_escape "$last_job_id")",
    "action": "$(json_escape "$last_action")",
    "state": "$(json_escape "$last_state")",
    "finished_ts": $last_finished_ts
  },
  "warnings": $warn_json
}
EOF
    chmod 0666 "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$STATE_FILE"
    log "心跳已更新：$STATE_FILE（branch=$branch sha=$local_sha behind=$behind container=$container_state pending=$pending）"
    return 0
}

cmd_tick() {
    cmd_heartbeat
    cmd_drain
}

usage() {
    cat <<'EOF'
DiTing 部署执行器（宿主机侧）

用法：diting-agent.sh <命令>

命令：
  drain       处理 data/deploy/queue 里的作业（由 diting-agent.path 触发）
  heartbeat   刷新 data/deploy/state.json 心跳（由 diting-agent.timer 触发）
  tick        心跳 + 兜底排空队列（timer 推荐用这个）
  dry-run     只走预检与状态写入，不碰 git/docker（本地验证协议闭环）
  help        显示本帮助

配置：见 /etc/default/diting-agent（diting-agent.env.example）
EOF
}

main() {
    case "${1:-}" in
        drain) cmd_drain ;;
        heartbeat) cmd_heartbeat ;;
        tick) cmd_tick ;;
        dry-run) DRY_RUN=1; cmd_drain ;;
        help|-h|--help) usage ;;
        *) usage; exit 1 ;;
    esac
}

main "$@"
