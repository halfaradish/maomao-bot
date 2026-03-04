=# DiTing-NoneBot

**谛听bot**基于 **NoneBot** + **NapCat**开发，目前功能大多为定制功能。

## Docker 部署

### 基本步骤

1. 把`data`目录和`.env`文件复制到项目根目录

2. 根据docker-compose.yml或docker-compose.dev.yml,按需求修改端口（注意：Windows系统docker可能无法连接外部）

3. 启动Docker Compose：
   
   **方式一：使用Docker管理脚本（推荐）**
   - 确保Docker Desktop已启动（Windows系统下Docker命令需要Docker Desktop运行）
   - 打开命令提示符（CMD）或PowerShell，导航到项目根目录
   - 运行管理脚本：
     ```bash
     # 生产环境（默认）
     ./scripts/docker-manager.sh
     
     # 开发环境
     ./scripts/docker-manager.sh dev
     ```
   - 脚本将显示交互式菜单，您可以选择：
     - 构建镜像
     - 启动容器
     - 停止容器
     - 查看容器状态
     - 查看日志
     - 进入容器
     - 清理环境
     - 切换环境
     - 查看帮助信息
   
   **方式二：通过Docker Desktop图形界面**
   - 打开Docker Desktop，启动服务
   - 在IDE的"服务"面板查看Docker连接情况，成功后运行相应的docker-compose文件中的服务，自动安装镜像和容器内依赖
   
   **方式三：通过命令行启动（传统方式）**
   - **生产环境**：
     - 确保Docker Desktop已启动（Windows系统下Docker命令需要Docker Desktop运行）
     - 打开命令提示符（CMD）或PowerShell，导航到项目根目录
     - 运行以下命令启动服务：
       ```bash
       docker compose up -d
       ```
       （参数`-d`表示在后台运行服务）
     - 查看服务状态：
       ```bash
       docker compose ps
       ```
     - 查看服务日志（可选）：
       ```bash
       docker compose logs -f
       ```
       （参数`-f`表示实时跟踪日志输出）
   
   **开发环境**：
   - 确保Docker Desktop已启动（Windows系统下Docker命令需要Docker Desktop运行）
   - 打开命令提示符（CMD）或PowerShell，导航到项目根目录
   - 运行以下命令启动服务：
     ```bash
     docker compose -f docker-compose.dev.yml up -d
     ```
     （参数`-d`表示在后台运行服务）
   - 查看服务状态：
     ```bash
     docker compose -f docker-compose.dev.yml ps
     ```
   - 查看服务日志（可选）：
     ```bash
     docker compose -f docker-compose.dev.yml logs -f
     ```
     （参数`-f`表示实时跟踪日志输出）

4. 进入Napcat Webui进行配置：http://localhost:6099，开发时，可将ws心跳和重连频率调高

5. 登录WebUI：访问WebUI页面输入`token`，token可在napcat日志查询，扫码登录QQ

6. 代码更改后，重新**构建**nonebot容器即可

### Docker管理脚本使用指南

我们提供了一个便捷的Docker管理脚本，可以简化Docker操作：

#### 快速开始
```bash
# 进入项目根目录
cd ~/path/to/DiTing-NoneBot

# 运行管理脚本（生产环境）
./scripts/docker-manager.sh

# 运行管理脚本（开发环境）
./scripts/docker-manager.sh dev
```

#### 脚本功能
脚本提供了以下功能：
- **构建镜像**：重新构建Docker镜像
- **启动容器**：启动Docker容器服务
- **停止容器**：停止并清理Docker容器
- **查看状态**：显示容器运行状态
- **查看日志**：支持查看历史日志和实时跟踪日志
- **进入容器**：进入运行中的容器内部进行调试
- **清理环境**：清理未使用的Docker资源
- **切换环境**：在开发环境和生产环境之间切换
- **帮助信息**：显示详细的使用说明

#### 使用示例
```bash
# 启动生产环境
./scripts/docker-manager.sh
# 选择选项2启动容器

# 启动开发环境
./scripts/docker-manager.sh dev
# 选择选项2启动容器

# 查看实时日志
./scripts/docker-manager.sh
# 选择选项5，然后选择2实时跟踪日志
```

#### 注意事项
- 脚本需要在项目根目录下运行
- 确保已安装Docker和Docker Compose
- Windows系统需要先启动Docker Desktop
- 脚本会自动检测并切换到正确的环境配置

### 提示

容器内通信使用的前缀分别为mysql, redis, nonebot, napcat (容器名)，例：
`ws://nonebot:6090/onebot/v11/ws`

### 可能遇到的问题

1. 一些镜像安装失败（如：mysql）
   - 原因：可能是`latest`标签问题
   - 解决方式：更改`docker-compose.yml`中的配置，将`latest`改为具体版本号，例：
     ```yaml
     service:
         ...
         mysql:
             ...
             image: library/mysql:8.0.32
     ```

2. 运行某些容器时报错（如Redis容器报错：`exec /usr/local/bin/docker-entrypoint.sh: exec format error`）
   - 解决方式：尝试在配置中更改版本号（同上），卸载已安装的镜像，重装指定版本号的镜像；若无法解决，可能是系统与Docker的镜像架构不一致（如ARM和x86_64）

## 文档

- [NoneBot](https://nonebot.dev/)
- [NapCat](https://www.napcat.wiki/guide/install)