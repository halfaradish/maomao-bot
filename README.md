# DiTing-NoneBot

**谛听bot**基于 **NoneBot** + **NapCat**开发，目前功能大多为定制功能。

## Docker 部署

### 基本步骤

1. 把`data`目录和`.env`文件复制到项目根目录，安装`requirements.txt`内的依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 部署docker compose，yml中的端口穿透按需求修改（注意：Windows系统docker可能无法连接外部）

3. 启动Docker Compose：
   
   **方式一：通过Docker Desktop图形界面**
   - 打开Docker Desktop，启动服务
   - 在IDE的"服务"面板查看Docker连接情况，成功后运行 docker-compose.yml 中的服务，自动安装镜像和容器内依赖
   
   **方式二：通过命令行启动**
   - 确保Docker Desktop已启动（Windows系统下Docker命令需要Docker Desktop运行）
   - 打开命令提示符（CMD）或PowerShell，导航到项目根目录
   - 运行以下命令启动服务：
     ```bash
     docker-compose up -d
     ```
     （参数`-d`表示在后台运行服务）
   - 查看服务状态：
     ```bash
     docker-compose ps
     ```
   - 查看服务日志（可选）：
     ```bash
     docker-compose logs -f
     ```
     （参数`-f`表示实时跟踪日志输出）

4. 进入Napcat Webui进行配置（http://localhost:6099），开发时，可将ws心跳和重连频率调高

5. 登录WebUI：访问WebUI页面输入`token`，token可在napcat日志查询，扫码登录QQ

6. 代码更改后，重新**构建**nonebot容器即可

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