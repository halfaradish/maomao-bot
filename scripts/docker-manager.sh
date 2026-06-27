#!/bin/bash

# DiTing Docker 管理脚本
# 从 .env 读取 ENVIRONMENT，推导 compose 变量并调用 docker compose

set -e

# ============================================================
# 颜色定义
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================
# 路径解析
# ============================================================
SCRIPT_PATH=$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# ============================================================
# 日志
# ============================================================
info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}    $1"; }
error()   { echo -e "${RED}[ERROR]${NC}   $1"; }

# ============================================================
# 状态变量（由 load_env_config 填充）
# ============================================================
CURRENT_ENV=""
SUFFIX=""
BOT_HOST_PORT=""
REDIS_HOST_PORT=""
PROJECT_NAME=""
CONTAINER_NAME=""

# ============================================================
# 从 .env 读取 ENVIRONMENT 并推导 compose 变量
# ============================================================
load_env_config() {
    if [ -f "$ENV_FILE" ]; then
        CURRENT_ENV=$(grep -E '^ENVIRONMENT=' "$ENV_FILE" | cut -d'=' -f2- | tr -d ' \r\n' | sed "s/^['\"]//;s/['\"]$//")
    fi
    CURRENT_ENV="${CURRENT_ENV:-prod}"

    case "$CURRENT_ENV" in
        dev|development)
            CURRENT_ENV="dev"
            SUFFIX="-dev"
            BOT_HOST_PORT="6095"
            REDIS_HOST_PORT="6380"
            PROJECT_NAME="diting-nonebot-dev"
            CONTAINER_NAME="diting-nonebot-dev"
            ;;
        prod|production|local)
            # local 和 prod 都使用 prod 的 docker 配置
            CURRENT_ENV="prod"
            SUFFIX=""
            BOT_HOST_PORT="6090"
            REDIS_HOST_PORT="6379"
            PROJECT_NAME="diting-nonebot"
            CONTAINER_NAME="diting-nonebot"
            ;;
        *)
            warn ".env 中未知的 ENVIRONMENT '$CURRENT_ENV'，回退为 prod 配置"
            CURRENT_ENV="prod"
            SUFFIX=""
            BOT_HOST_PORT="6090"
            REDIS_HOST_PORT="6379"
            PROJECT_NAME="diting-nonebot"
            CONTAINER_NAME="diting-nonebot"
            ;;
    esac
}

# ============================================================
# 打印环境信息
# ============================================================
show_env_info() {
    echo -e "${BLUE}当前环境配置 (从 ${ENV_FILE} 读取):${NC}"
    echo -e "  ENVIRONMENT:      ${GREEN}${CURRENT_ENV}${NC}"
    echo -e "  Project 名:       ${GREEN}${PROJECT_NAME}${NC}"
    echo -e "  Bot 端口:          ${GREEN}${BOT_HOST_PORT}:6090${NC}"
    echo -e "  Redis 端口:        ${GREEN}${REDIS_HOST_PORT}:6379${NC}"
    echo ""
}

# ============================================================
# Docker compose 包装函数
# 所有调用都传入推导出的 compose 变量和 project-name
# ============================================================
dc() {
    SUFFIX="$SUFFIX" \
    BOT_HOST_PORT="$BOT_HOST_PORT" \
    REDIS_HOST_PORT="$REDIS_HOST_PORT" \
        docker compose --project-name "$PROJECT_NAME" "$@"
}

# ============================================================
# 命令实现
# ============================================================

cmd_build() {
    load_env_config
    echo -e "${BLUE}正在构建 ${CURRENT_ENV} 环境镜像...${NC}"
    echo ""
    cd "$PROJECT_ROOT"
    if dc build; then
        info "清理悬空镜像..."
        docker image prune -f --filter "dangling=true" >/dev/null 2>&1 || true
        success "${CURRENT_ENV} 环境镜像构建成功！"
    else
        error "${CURRENT_ENV} 环境镜像构建失败"
        return 1
    fi
}

cmd_start() {
    load_env_config
    echo -e "${BLUE}正在启动 DiTing ${CURRENT_ENV} 环境...${NC}"
    show_env_info
    cd "$PROJECT_ROOT"
    if dc up -d; then
        success "${CURRENT_ENV} 环境启动成功！"
        echo -e "  Bot 访问端口: ${GREEN}${BOT_HOST_PORT}${NC}"
        echo -e "  Redis 端口:   ${GREEN}${REDIS_HOST_PORT}${NC}"
    else
        error "${CURRENT_ENV} 环境启动失败"
        return 1
    fi
}

cmd_stop() {
    load_env_config
    echo -e "${YELLOW}正在停止 DiTing ${CURRENT_ENV} 环境...${NC}"
    echo ""
    cd "$PROJECT_ROOT"
    if dc down; then
        success "${CURRENT_ENV} 环境已停止"
    else
        error "停止失败"
        return 1
    fi
}

cmd_restart() {
    load_env_config
    echo -e "${YELLOW}正在重启 DiTing ${CURRENT_ENV} 环境...${NC}"
    echo ""
    cd "$PROJECT_ROOT"
    dc down >/dev/null 2>&1 || true
    if dc up -d; then
        success "${CURRENT_ENV} 环境已重启！"
        echo -e "  Bot 访问端口: ${GREEN}${BOT_HOST_PORT}${NC}"
        echo -e "  Redis 端口:   ${GREEN}${REDIS_HOST_PORT}${NC}"
    else
        error "重启失败"
        return 1
    fi
}

cmd_status() {
    load_env_config
    echo -e "${BLUE}DiTing ${CURRENT_ENV} 环境状态:${NC}"
    echo ""
    cd "$PROJECT_ROOT"

    echo -e "${CYAN}=== Compose 容器状态 (project: ${PROJECT_NAME}) ===${NC}"
    dc ps

    echo ""
    echo -e "${CYAN}=== Docker 容器详细状态（含已停止） ===${NC}"
    docker ps -a --filter "name=diting" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true

    echo ""
    echo -e "${CYAN}=== DiTing 镜像 ===${NC}"
    docker image ls --filter "reference=diting-nonebot*" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" 2>/dev/null || true
}

cmd_logs() {
    load_env_config
    echo -e "${BLUE}查看 DiTing ${CURRENT_ENV} 环境日志...${NC}"
    echo -e "${YELLOW}(按 Ctrl+C 退出日志)${NC}"
    echo ""

    cd "$PROJECT_ROOT"

    # 检查是否有参数指定行数或 -f
    if [ $# -gt 0 ]; then
        dc logs "$@"
    else
        # 交互式选择
        echo "1. 查看最近 100 行日志"
        echo "2. 实时跟踪日志"
        echo ""
        read -p "请选择 [1-2]: " log_choice

        case $log_choice in
            1) dc logs -n 100 diting-nonebot ;;
            2)
                echo -e "${YELLOW}实时跟踪日志，按 Ctrl+C 退出...${NC}"
                trap '' SIGINT
                dc logs -f diting-nonebot || true
                trap - SIGINT
                ;;
            *) error "无效选择!" ;;
        esac
    fi
}

cmd_shell() {
    load_env_config
    echo -e "${BLUE}进入 DiTing ${CURRENT_ENV} 容器...${NC}"
    echo -e "${YELLOW}(输入 'exit' 退出容器)${NC}"
    echo ""
    cd "$PROJECT_ROOT"

    # 检查容器是否运行
    if dc ps -q diting-nonebot 2>/dev/null | grep -q .; then
        dc exec diting-nonebot /bin/bash || dc exec diting-nonebot /bin/sh || true
    else
        error "容器未运行! 请先启动容器"
        return 1
    fi
}

cmd_clean() {
    load_env_config
    echo -e "${RED}警告: 这将清理 Docker 资源${NC}"
    echo ""
    echo "1. 清理所有已停止的容器"
    echo "2. 清理所有悬空（dangling）的镜像"
    echo "3. 停止并删除 ${CURRENT_ENV} 环境（容器+网络）"
    echo ""

    read -p "请选择清理方式 [1-3]: " clean_choice

    case $clean_choice in
        1)
            echo "正在清理未使用的容器..."
            docker container prune -f
            success "容器清理完成!"
            ;;
        2)
            echo "正在清理未使用的镜像..."
            docker image prune -f
            success "镜像清理完成!"
            ;;
        3)
            echo -e "${RED}确定要删除 ${CURRENT_ENV} 环境吗?${NC}"
            read -p "确定? (y/N): " confirm
            if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
                cd "$PROJECT_ROOT"
                dc down --volumes
                success "${CURRENT_ENV} 环境已清理"
            else
                echo -e "${YELLOW}已取消${NC}"
            fi
            ;;
        *)
            error "无效选择!"
            return 1
            ;;
    esac
}

# ============================================================
# 帮助信息
# ============================================================
show_help() {
    echo -e "${BLUE}DiTing Docker 管理脚本${NC}"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "说明:"
    echo "  脚本从项目根目录的 .env 读取 ENVIRONMENT 变量"
    echo "  根据 ENVIRONMENT 值 (dev/prod) 推导容器名、端口等"
    echo "  然后将这些变量传入 docker compose"
    echo ""
    echo "命令:"
    echo "  start       启动容器 (docker compose up -d)"
    echo "  stop        停止容器 (docker compose down)"
    echo "  restart     重启容器 (stop + start)"
    echo "  status      查看容器状态"
    echo "  logs        查看容器日志"
    echo "  build       构建镜像"
    echo "  clean       清理 Docker 资源"
    echo "  shell       进入容器内部"
    echo "  help        显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                          # 启动交互式菜单"
    echo "  $0 start                    # 根据 .env 配置启动"
    echo "  $0 logs                     # 查看日志"
    echo "  $0 status                   # 查看状态"
    echo ""
    echo "切换环境:"
    echo "  手动编辑 .env 文件中的 ENVIRONMENT 值"
    echo "  ENVIRONMENT=prod    → 生产环境 (端口 6090/6379)"
    echo "  ENVIRONMENT=dev     → 开发环境 (端口 6095/6380)"
    echo ""
    echo "直接使用 docker compose:"
    echo "  docker compose up -d        # 使用默认值 (prod 配置)"
}

# ============================================================
# 标题
# ============================================================
show_header() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}          ${GREEN}DiTing Docker 管理脚本${NC}                     ${CYAN}║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ============================================================
# 交互式菜单
# ============================================================
interactive_mode() {
    while true; do
        load_env_config
        show_header
        show_env_info
        echo -e "${YELLOW}请选择操作:${NC}"
        echo ""
        echo -e "  ${CYAN}1)${NC} build       - 构建镜像"
        echo -e "  ${CYAN}2)${NC} start       - 启动容器"
        echo -e "  ${CYAN}3)${NC} stop        - 停止容器"
        echo -e "  ${CYAN}4)${NC} restart     - 重启容器"
        echo -e "  ${CYAN}5)${NC} status      - 查看容器状态"
        echo -e "  ${CYAN}6)${NC} logs        - 查看容器日志"
        echo -e "  ${CYAN}7)${NC} shell       - 进入容器内部"
        echo -e "  ${CYAN}8)${NC} clean       - 清理 Docker 资源"
        echo ""
        echo -e "  ${CYAN}9)${NC} help        - 帮助信息"
        echo -e "  ${CYAN}0)${NC} 退出"
        echo ""

        read -p "请输入选项 (0-9): " choice

        case "$choice" in
            1)  cmd_build ;;
            2)  cmd_start ;;
            3)  cmd_stop ;;
            4)  cmd_restart ;;
            5)  cmd_status ;;
            6)  cmd_logs ;;
            7)  cmd_shell ;;
            8)  cmd_clean ;;
            9)  show_help ;;
            0)
                echo -e "${GREEN}再见!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}无效选项，请重新选择${NC}"
                sleep 1
                ;;
        esac

        echo ""
        read -p "按回车键返回菜单..." -n 1 -s
    done
}

# ============================================================
# CLI 命令模式
# ============================================================
run_command() {
    case "$1" in
        start)    cmd_start ;;
        stop)     cmd_stop ;;
        restart)  cmd_restart ;;
        status)   cmd_status ;;
        logs)     shift; cmd_logs "$@" ;;
        build)    cmd_build ;;
        clean)    cmd_clean ;;
        shell)    cmd_shell ;;
        help|-h|--help)
            show_help
            ;;
        *)
            echo -e "${RED}错误: 未知命令 '$1'${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# ============================================================
# 主函数
# ============================================================
main() {
    # 切换到项目根目录
    cd "$PROJECT_ROOT"

    # 检查 docker compose 可用
    if ! docker compose version &> /dev/null; then
        error "Docker Compose 未安装或不可用"
        exit 1
    fi

    if [ $# -eq 0 ]; then
        # 无参数 → 交互菜单模式
        interactive_mode
    else
        # 有参数 → CLI 命令模式
        run_command "$@"
    fi
}

main "$@"
