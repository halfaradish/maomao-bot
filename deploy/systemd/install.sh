#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# DiTing 部署执行器安装脚本（在服务器上以 root 运行）
#
#   sudo bash deploy/systemd/install.sh                 # 默认实例（生产），仓库 = 脚本所在目录
#   sudo bash deploy/systemd/install.sh --root /home/bot/diting/nonebot
#   sudo bash deploy/systemd/install.sh --name dev --root /home/bot/diting/nonebot-dev
#   sudo bash deploy/systemd/install.sh --name dev --uninstall
#
# 做三件事：
#   1. 建好 data/deploy/* 目录并置 0777（容器内是 root，跨 uid 时否则会互相写不动）
#   2. 把单元里的 @…@ 占位符替换成真实路径与实例名后安装到 /etc/systemd/system
#      （[Path] 段不支持环境变量展开，必须落成字面路径）
#   3. 启用 <实例>.path（监听队列）与 <实例>.timer（心跳 + 兜底排空）
#
# 两个环境同时使用（prod + dev）：
#   必须各自有一份独立目录（两份 clone），然后分别安装、用 --name 区分单元名：
#     sudo bash deploy/systemd/install.sh                     # 生产目录 → diting-agent.*
#     sudo bash deploy/systemd/install.sh --name dev --root /home/bot/diting/nonebot-dev
#   ⚠️ 千万不要对同一个目录装两个实例：compose 把 ./data 挂到 /app/data 且不随 SUFFIX 变化，
#      同一目录下两个环境会共享同一个 data/deploy 队列，执行器会认领到另一个环境的作业。
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

UNIT_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ROOT="$DEFAULT_ROOT"
UNINSTALL=0
NAME=""

info()  { printf '\033[0;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[OK]\033[0m    %s\n' "$*"; }
warn()  { printf '\033[0;33m[WARN]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '3,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --root) ROOT="${2:-}"; shift 2 ;;
        --name|-n) NAME="${2:-}"; shift 2 ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "未知参数：$1（用 --help 看用法）" ;;
    esac
done

[ "$(id -u)" = "0" ] || die "需要 root：sudo bash $0 $*"
command -v systemctl >/dev/null 2>&1 || die "没有 systemctl，本脚本只支持 systemd 主机"
[ -d "$ROOT" ] || die "目标目录不存在：$ROOT"
ROOT="$(cd "$ROOT" && pwd)"

# ── 实例命名 ──────────────────────────────────────────────────────────────────
# 不带 --name  → diting-agent.{service,path,timer} + /etc/default/diting-agent（生产默认）
# 带 --name dev → diting-agent-dev.{...} + /etc/default/diting-agent-dev
if [ -n "$NAME" ]; then
    printf '%s' "$NAME" | grep -Eq '^[A-Za-z0-9_-]+$' \
        || die "实例名只允许字母数字下划线短横线：$NAME"
fi
SUFFIX="${NAME:+-$NAME}"
PREFIX="diting-agent$SUFFIX"
TICK_PREFIX="${PREFIX}-tick"
ENV_FILE="/etc/default/diting-agent$SUFFIX"
UNITS=("$PREFIX.service" "$TICK_PREFIX.service" "$PREFIX.path" "$PREFIX.timer")
TEMPLATES=(diting-agent.service diting-agent-tick.service diting-agent.path diting-agent.timer)

if [ "$UNINSTALL" = "1" ]; then
    info "卸载部署执行器实例「${NAME:-默认}」（$ROOT）"
    for unit in "${UNITS[@]}"; do
        systemctl disable --now "$unit" 2>/dev/null || true
        rm -f "$UNIT_DIR/$unit"
    done
    systemctl daemon-reload
    ok "单元已移除：${UNITS[*]}"
    echo "  $ENV_FILE 与 $ROOT/data/deploy/ 保留未删（里面有部署配置、状态与日志）"
    exit 0
fi

[ -f "$ROOT/.env" ] || die "缺少 $ROOT/.env（compose 短语法挂载在源文件缺失时会创建同名目录，配置会静默丢失）"
[ -f "$ROOT/scripts/diting-agent.sh" ] || die "缺少 $ROOT/scripts/diting-agent.sh"
[ -f "$ROOT/scripts/docker-manager.sh" ] || die "缺少 $ROOT/scripts/docker-manager.sh（执行器靠它复用环境映射与构建/重启逻辑）"

# 同一个目录装第二个实例 = 两个环境共用 data/deploy 队列，直接拒绝
for unit in "$UNIT_DIR"/diting-agent*.service; do
    [ -f "$unit" ] || continue
    [ "$(basename "$unit")" = "$PREFIX.service" ] && continue
    if grep -qF "ExecStart=/bin/bash $ROOT/scripts/diting-agent.sh" "$unit" 2>/dev/null; then
        die "已有单元 $(basename "$unit") 指向同一个目录 $ROOT。
两个环境必须各自一份独立目录（两份 clone）：compose 把 ./data 挂到 /app/data 且不随 SUFFIX 变化，
同目录下两个环境会共享 data/deploy 队列，执行器会认领到另一个环境的作业。
请先 clone 出第二个目录，再用 --name <名字> --root <新目录> 安装。"
    fi
done

# ── 1. 部署目录 ───────────────────────────────────────────────────────────────
info "创建部署目录 $ROOT/data/deploy/*（0777）"
for sub in queue running status logs reported; do
    mkdir -p "$ROOT/data/deploy/$sub"
    chmod 0777 "$ROOT/data/deploy/$sub"
done
chmod 0777 "$ROOT/data/deploy"

# ── 2. 配置文件 ───────────────────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    warn "$ENV_FILE 已存在，保留不覆盖（要改配置请直接编辑它）"
else
    info "写入 $ENV_FILE"
    sed "s|@DITING_DEPLOY_ROOT@|$ROOT|g" "$SCRIPT_DIR/diting-agent.env.example" \
        | sed 's/^# DITING_DEPLOY_ENV=prod/DITING_DEPLOY_ENV=/' >"$ENV_FILE"
    chmod 0644 "$ENV_FILE"
fi

# ── 3. 安装单元 ───────────────────────────────────────────────────────────────
for idx in "${!UNITS[@]}"; do
    unit="${UNITS[$idx]}"
    template="$SCRIPT_DIR/${TEMPLATES[$idx]}"
    [ -f "$template" ] || die "缺少单元模板：$template"
    info "安装 $UNIT_DIR/$unit"
    sed -e "s|@DITING_DEPLOY_ROOT@|$ROOT|g" \
        -e "s|@DITING_AGENT_NAME@|$PREFIX|g" \
        -e "s|@DITING_AGENT_TICK_NAME@|$TICK_PREFIX|g" \
        -e "s|@DITING_AGENT_ENV_FILE@|$ENV_FILE|g" \
        "$template" >"$UNIT_DIR/$unit"
    chmod 0644 "$UNIT_DIR/$unit"
done
systemctl daemon-reload

# ── 4. 启用 ───────────────────────────────────────────────────────────────────
info "启用 $PREFIX.path 与 $PREFIX.timer"
systemctl enable --now "$PREFIX.path"
systemctl enable --now "$PREFIX.timer"

# 立刻跑一次心跳，让 QQ 里的 /diting status 马上有数据
info "执行一次心跳"
bash "$ROOT/scripts/diting-agent.sh" heartbeat || warn "心跳失败，请看上面的输出"

echo
ok "安装完成（实例：${NAME:-默认}，目录：$ROOT）"
if [ -n "$NAME" ]; then
    echo
    echo "提示：这是第二份实例，请确认它的 $ROOT/.env 里"
    echo "      ENVIRONMENT 与 DITING_DEPLOY_BRANCH 指向正确环境（例如 dev / dev/1.0），"
    echo "      并且和另一份实例用的是不同的 clone 目录。"
fi
echo
echo "验证步骤："
echo "  1) systemctl status $PREFIX.path $PREFIX.timer"
echo "  2) cat $ROOT/data/deploy/state.json"
echo "  3) QQ 里发 /diting status（dev 环境是 dev-diting status）"
echo
echo "排障："
echo "  journalctl -u $PREFIX -n 100           # 最近一次作业"
echo "  journalctl -u $TICK_PREFIX -n 50       # 心跳"
echo "  tail -n 100 $ROOT/data/deploy/logs/<job_id>.log"
echo
echo "注意：/diting build 与 restart 会重建容器，执行器在宿主机上不受影响，"
echo "      但服务起不来时 QQ 里不会收到消息（没人读状态文件）—— 这时看上面的 journalctl。"
