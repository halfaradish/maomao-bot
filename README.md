# DiTing-NoneBot

**谛听bot**基于 **NoneBot** + **NapCat**开发

目前功能大多为定制功能

## docker启动
1. 部署docker compose，yml中的端口穿透按需求改（win系统docker无法连接外部）
2. 添加data文件夹和.env文件，其中Redis的配置需要根据实际情况改
3. 进入Napcat Webui进行配置(http://localhost:6099)，开发时，可以将ws心跳和重连频率调高
4. 代码更改后，重新 **构建** nonebot容器即可

Tips: 容器内通信使用的前缀分别为mysql, redis, nonebot, napcat (容器名)，例：ws://nonebot:6090/onebot/v11/ws

## Documentation

See

[NoneBot](https://nonebot.dev/)

[NapCat](https://www.napcat.wiki/guide/install)
