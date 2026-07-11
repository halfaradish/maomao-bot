"""
DiTing-NoneBot 启动入口。

使用 ``python bot.py`` 替代 ``nb run`` 启动项目。

启动方式：
  本地开发：HOT_RELOAD=true python bot.py      → watcher 监视 src/ + bot.py，变更自动重启
  正常启动：python bot.py                       → 直接初始化运行
  Docker：  entrypoint.sh → exec python bot.py  → 同上，HOT_RELOAD 由 .env 控制

启动流程（worker）：
  1. 加载 .env 环境变量（通过 src.config 的模块级副作用）
  2. nonebot.init() — 初始化 Driver、Config
  3. 导入 src.api — 注册 FastAPI 路由（内部调用 get_app()）
  4. 注册 OneBot V11 适配器
  5. 从 pyproject.toml 加载所有插件
  6. 加载内置插件 echo
  7. nonebot.run() — 启动服务
"""

import os
import sys

from nonebot import get_driver, init, load_builtin_plugin, load_from_toml, run
from nonebot.log import default_format, logger

# ── 加载 .env 文件 ──────────────────────────────────────────
# src.config.__init__ 导入 local_config 模块，触发以下副作用：
#   load_dotenv(".env")           → 加载基础配置
#   load_dotenv(f".env.{ENV}")    → 加载环境特定配置
# 这必须在 nonebot.init() 之前完成
import src.config  # noqa: E402, F401

# ── 配置文件日志 ────────────────────────────────────────────
# watcher 和 worker 是独立的 Python 进程（通过 subprocess.Popen），
# 各自导入 bot.py 一次，logger.add() 各执行一次，不存在 handler 冲突
from src.config import LogConfig

logger.add(
    LogConfig.LOG_FILE_PATH,
    rotation=LogConfig.LOG_FILE_ROTATION,
    retention=LogConfig.LOG_FILE_RETENTION,
    level=LogConfig.LOG_FILE_LEVEL,
    encoding=LogConfig.LOG_FILE_ENCODING,
    format=default_format,
    enqueue=LogConfig.LOG_FILE_ENQUEUE,
    compression=LogConfig.LOG_FILE_COMPRESSION,
)


def start():
    """初始化并启动 NoneBot。仅 worker 进程调用，watcher 进程不调此函数。"""

    # ── 初始化 NoneBot ──────────────────────────────────────────
    # 从 os.environ 读取 DRIVER、HOST、PORT、SUPERUSERS、COMMAND_START 等
    init()

    # ── 注册 API 路由 ───────────────────────────────────────────
    # src/api/__init__.py 在模块级别调用 get_app() 和 get_driver()
    # 必须在 nonebot.init() 之后导入
    import src.api  # noqa: E402, F401

    # ── 注册 OneBot V11 适配器 ──────────────────────────────────
    from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

    get_driver().register_adapter(OneBotV11Adapter)

    # ── 从 pyproject.toml 加载插件 ──────────────────────────────
    # 处理 [tool.nonebot] 中的 plugins 和 plugin_dirs
    # 包括：nonebot_plugin_apscheduler, nonebot_plugin_prometheus,
    #       nonebot_plugin_alconna, src/plugins/ 下所有插件
    load_from_toml("pyproject.toml")

    # ── 加载内置插件 ────────────────────────────────────────────
    # pyproject.toml 声明: builtin_plugins = ["echo"]
    load_builtin_plugin("echo")

    # ── 启动 ────────────────────────────────────────────────────
    run()


# ═══════════════════════════════════════════════════════════════
# 主入口：watcher / worker 分流
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if (
        os.getenv("HOT_RELOAD", "").lower() == "true"
        and os.getenv("_HOT_RELOAD_WORKER") != "true"
    ):
        # ── Watcher 进程 ──
        # 监视 src/ 和 bot.py 的变更，发现变更后重启 worker 子进程
        import subprocess
        from watchfiles import watch

        env = os.environ.copy()
        env["_HOT_RELOAD_WORKER"] = "true"

        proc = subprocess.Popen([sys.executable, __file__], env=env)

        try:
            for changes in watch(
                "src", __file__, debounce=500, step=200, recursive=True
            ):
                for change, path in changes:
                    logger.info(f"[reload] {change.name}: {path}")
                proc.terminate()
                proc.wait()
                proc = subprocess.Popen([sys.executable, __file__], env=env)
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
    else:
        # ── Worker 进程或普通启动 ──
        try:
            start()
        except KeyboardInterrupt:
            pass