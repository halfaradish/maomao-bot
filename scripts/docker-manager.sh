#!/bin/bash

# 默认环境配置
ENVIRONMENT="prod"
PROJECT_NAME="diting-nonebot"
SERVICE_NAME="diting-nonebot"
COMPOSE_FILE="docker-compose.yml"
DOCKER_SERVICE_NAME="diting-nonebot"  # Docker Compose服务名

# 环境配置函数
set_environment() {
    case "$1" in
        "dev"|"development")
            ENVIRONMENT="dev"
            SERVICE_NAME="diting-nonebot-dev"
            COMPOSE_FILE="docker-compose.dev.yml"
            DOCKER_SERVICE_NAME="diting-nonebot-dev"
            ;;
        "prod"|"production")
            ENVIRONMENT="prod"
            SERVICE_NAME="diting-nonebot"
            COMPOSE_FILE="docker-compose.yml"
            DOCKER_SERVICE_NAME="diting-nonebot"
            ;;
        *)
            error "无效的环境参数: $1"
            error "支持的环境: dev, prod"
            exit 1
            ;;
    esac
    info "当前环境: ${ENVIRONMENT} (服务名: ${SERVICE_NAME}, 配置文件: ${COMPOSE_FILE}, Docker服务名: ${DOCKER_SERVICE_NAME})"
}

# 解决路径兼容性问题
SCRIPT_PATH=$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # 重置颜色

# 日志格式化
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 显示菜单
show_menu() {
    clear
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${CYAN} Docker 管理工具${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${PURPLE} 当前环境: ${ENVIRONMENT} ${NC}"
    echo -e "${PURPLE} 服务名: ${SERVICE_NAME} ${NC}"
    echo -e "${PURPLE} 配置文件: ${COMPOSE_FILE} ${NC}"
    echo -e "${PURPLE} Docker服务名: ${DOCKER_SERVICE_NAME} ${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${YELLOW}1. 构建镜像${NC}"
    echo -e "${YELLOW}2. 启动容器${NC}"
    echo -e "${YELLOW}3. 停止容器${NC}"
    echo -e "${YELLOW}4. 查看容器状态${NC}"
    echo -e "${YELLOW}5. 查看日志${NC}"
    echo -e "${YELLOW}6. 进入容器${NC}"
    echo -e "${YELLOW}7. 清理环境${NC}"
    echo -e "${YELLOW}8. 切换环境(dev/prod)${NC}"
    echo -e "${YELLOW}9. 帮助信息${NC}"
    echo -e "${YELLOW}10. 退出${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo
}

# 检查依赖（兼容docker-compose和docker compose）
check_dependencies() {
    info "检查 Docker 和 Docker Compose 是否安装..."
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装，请先安装Docker"
        exit 1
    fi
    # 兼容新版docker compose（v2）和旧版docker compose（v1）
    if ! docker compose version &> /dev/null; then
        error "Docker Compose 未安装，请先安装Docker Compose"
        exit 1
    fi
    success "Docker 和 Docker Compose 已安装"
}

# 构建镜像
build_image() {
    info "开始构建 Docker 镜像..."
    if docker compose -f "${COMPOSE_FILE}" build; then
        info "清理悬空镜像..."
        docker image prune -f --filter "dangling=true"
        success "镜像构建成功!"
    else
        error "镜像构建失败!"
        return 1
    fi
}

# 启动容器
start_container() {
    info "开始启动 Docker 容器..."
    if docker compose -f "${COMPOSE_FILE}" up -d; then
        success "容器启动成功!"
    else
        error "容器启动失败!"
        return 1
    fi
}

# 停止容器
stop_container() {
    info "开始停止 Docker 容器..."
    if docker compose -f "${COMPOSE_FILE}" down; then
        success "容器停止成功!"
    else
        error "容器停止失败!"
        return 1
    fi
}

# 查看容器状态
check_container_status() {
    info "检查 Docker 容器状态..."
    echo -e "\n${CYAN}=== Compose 容器状态 ===${NC}"
    docker compose -f "${COMPOSE_FILE}" ps "${DOCKER_SERVICE_NAME}"
    echo -e "\n${CYAN}=== Docker 容器详细状态 ===${NC}"
    docker ps --filter "name=${PROJECT_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    success "容器状态检查完成!"
}

# 查看日志
view_logs() {
    echo -e "${CYAN} 查看容器日志${NC}"
    echo "1. 查看最近100行日志"
    echo "2. 实时跟踪日志"
    echo
    
    read -p "请选择日志查看方式 [1-2]: " log_choice
    
    case $log_choice in
        1)
            docker compose -f "${COMPOSE_FILE}" logs -n 100 "${DOCKER_SERVICE_NAME}"
            ;;
        2)
            echo -e "${YELLOW} 实时跟踪日志，按 Ctrl+C 退出...${NC}"
            docker compose -f "${COMPOSE_FILE}" logs -f "${DOCKER_SERVICE_NAME}"
            ;;
        *)
            error "无效选择!"
            ;;
    esac
}

# 进入容器函数
enter_container() {
    info "尝试进入容器: ${SERVICE_NAME}"
    # 检查容器是否运行
    if docker compose -f "${COMPOSE_FILE}" ps -q "${DOCKER_SERVICE_NAME}" | grep -q .; then
        docker compose -f "${COMPOSE_FILE}" exec "${DOCKER_SERVICE_NAME}" /bin/bash || \
        docker compose -f "${COMPOSE_FILE}" exec "${DOCKER_SERVICE_NAME}" /bin/sh
    else
        error "容器未运行! 请先启动容器"
        return 1
    fi
}

# 切换环境
switch_environment() {
    clear
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${CYAN} 切换环境${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${YELLOW}1.  开发环境 (dev)${NC}"
    echo -e "${YELLOW}2.  生产环境 (prod)${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo
    
    read -p "请选择环境 [1-2]: " env_choice
    
    case $env_choice in
        1)
            set_environment "dev"
            success "已切换到开发环境"
            ;;
        2)
            set_environment "prod"
            success "已切换到生产环境"
            ;;
        *)
            error "无效选择! 请输入 1 或 2"
            return 1
            ;;
    esac
}

# 清理环境
clean_environment() {
    info "${CYAN} 正在清理 Docker 环境...${NC}"
    echo "1. 清理所有已停止的容器"
    echo "2. 清理所有悬空（dangling）的镜像"
    
    read -p "请选择清理方式 [1-2]: " clean_choice
    
    case $clean_choice in
        1)
            echo "正在清理未使用的容器..."
            docker container prune -f
            ;;
        2)
            echo "正在清理未使用的镜像..."
            docker image prune -f
            ;;
        *)
            error "无效选择! 请输入 1 或 2"
            return 1
            ;;
    esac
    
    if [ $? -eq 0 ]; then
        success "清理完成!"
    else
        error "清理失败!"
    fi
}

# 帮助信息
show_help() {
    clear
    echo -e "${BLUE}===============================================${NC}"
    info    "${CYAN} Docker 管理工具 - 帮助信息${NC}"
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${YELLOW}  项目配置:${NC}"
    echo -e "   - 项目名称: $PROJECT_NAME"
    echo -e "   - 服务名: $SERVICE_NAME"
    echo -e "   - Compose文件: $COMPOSE_FILE"
    echo -e "   - Docker服务名: $DOCKER_SERVICE_NAME"
    echo
    info "${YELLOW}  脚本功能:${NC}"
    echo -e "   1. 构建镜像: 使用 docker compose build 构建服务镜像"
    echo -e "   2. 启动容器: 使用 docker compose up -d 启动服务"
    echo -e "   3. 停止容器: 使用 docker compose down 停止并清理容器"
    echo -e "   4. 查看状态: 显示容器运行状态"
    echo -e "   5. 查看日志: 支持查看历史日志和实时日志"
    echo -e "   6. 进入容器: 进入运行中的容器内部（优先bash，备用sh）"
    echo -e "   7. 清理环境: 清理未使用的 Docker 资源"
    echo -e "   8. 切换环境: 在开发环境和生产环境之间切换"
    echo
    info "${YELLOW}  环境要求:${NC}"
    echo -e "   - Docker 20.10+"
    echo -e "   - Docker Compose 1.29+ (兼容v1/v2)"
    echo
    info "${YELLOW}  使用说明:${NC}"
    echo -e "   - 在包含 docker-compose.yml 和 docker-compose.dev.yml 的目录下运行此脚本"
    echo -e "   - 首次运行默认使用生产环境，可以通过菜单选项8切换环境"
    echo -e "   - 也可以直接指定环境参数: $0 [dev|prod]"
    echo -e "   - 根据菜单选择需要的操作"
    echo -e "   - 按 Enter 键返回菜单"
}

# 退出脚本
exit_script() {
    info "${CYAN} 谢谢使用 Docker 管理工具!${NC}"
    exit 0
}

# 检查命令行参数，支持直接指定环境
if [ $# -gt 0 ]; then
    set_environment "$1"
fi

# 确保compose文件存在
if [ ! -f "${COMPOSE_FILE}" ]; then
    error "Compose 文件不存在: ${COMPOSE_FILE}"
    info "当前目录: $(pwd)"
    info "请确保在包含 docker-compose.yml 和 docker-compose.dev.yml 的目录下运行此脚本"
    exit 1
fi

# 加载环境变量（可选，避免依赖bashrc）
[ -f ~/.bashrc ] && source ~/.bashrc

check_dependencies

while true; do
    show_menu
    read -p "请输入您的选择 [1-10]: " choice

    case $choice in
        1) build_image ;;
        2) start_container ;;
        3) stop_container ;;
        4) check_container_status ;;
        5) view_logs ;;
        6) enter_container ;;
        7) clean_environment ;;
        8) switch_environment ;;
        9) show_help ;;
        10) exit_script ;;
        *) error "无效选择! 请输入 1-10" ;;
    esac

    echo
    read -p "按 Enter 键返回菜单..." -n 1 -s
done