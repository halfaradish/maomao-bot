# DiTing-NoneBot

**谛听bot**基于 **NoneBot** + **NapCat**开发，目前功能大多为定制功能。

## Docker 部署

### 基本步骤

1. 把`data`目录和`.env`文件复制到项目根目录

2. 根据`docker-compose.yml`按需求修改端口（注意：Windows系统docker可能无法连接外部）

3. 启动Docker Compose：
   
   **方式一：使用Docker管理脚本（推荐）**

   [Docker管理脚本使用指南](#docker脚本使用指南)
   
   **方式二：通过Docker Desktop图形界面**
   - 打开Docker Desktop，启动服务
   - 在IDE的"服务"面板查看Docker连接情况，成功后运行相应的docker-compose文件中的服务，自动安装镜像和容器内依赖
   
   **方式三：通过命令行启动**
   - 确保Docker Desktop已启动（Windows系统下Docker命令需要Docker Desktop运行）
   - 编辑 `.env` 文件，设置 `ENVIRONMENT=prod`（生产环境）或 `ENVIRONMENT=dev`（开发环境）
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

   也可以通过脚本启动（自动读取 `.env` 中的 `ENVIRONMENT`）：
     ```bash
     ./scripts/docker-manager.sh start
     ```

4. 进入Napcat Webui进行配置：http://localhost:6099，开发时，可将ws心跳和重连频率调高

5. 登录WebUI：访问WebUI页面输入`token`，token可在napcat日志查询，扫码登录QQ

6. 代码更改后，重新**构建**nonebot容器即可

### Docker管理脚本使用指南<a id="docker脚本使用指南"></a>
我们提供了一个便捷的Docker管理脚本，可以简化Docker操作：

#### 快速开始
```bash
# CLI 命令模式（推荐）
./scripts/docker-manager.sh start    # 启动
./scripts/docker-manager.sh stop     # 停止
./scripts/docker-manager.sh restart  # 重启
./scripts/docker-manager.sh status   # 查看状态
./scripts/docker-manager.sh logs     # 查看日志
./scripts/docker-manager.sh build    # 构建镜像
./scripts/docker-manager.sh shell    # 进入容器
./scripts/docker-manager.sh clean    # 清理资源

# 或交互菜单模式
./scripts/docker-manager.sh
```

#### 脚本功能
脚本提供了以下功能：
- **构建镜像**：重新构建Docker镜像
- **启动容器**：启动Docker容器服务
- **停止容器**：停止并清理Docker容器
- **重启容器**：停止后重新启动
- **查看状态**：显示容器运行状态和镜像列表
- **查看日志**：支持查看历史日志和实时跟踪日志
- **进入容器**：进入运行中的容器内部进行调试
- **清理环境**：清理未使用的Docker资源
- **帮助信息**：显示详细的使用说明

#### 使用示例
```bash
# 启动（.env 中 ENVIRONMENT=prod 为生产环境）
./scripts/docker-manager.sh start

# 启动（.env 中 ENVIRONMENT=dev 为开发环境）
./scripts/docker-manager.sh start

# 查看实时日志
./scripts/docker-manager.sh logs

# 进入交互菜单
./scripts/docker-manager.sh
```

#### 注意事项
- 脚本需要在项目根目录下运行
- 确保已安装Docker和Docker Compose
- Windows系统需要先启动Docker Desktop
- **切换环境**：编辑 `.env` 文件，修改 `ENVIRONMENT=prod` 或 `ENVIRONMENT=dev`，然后重启容器

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