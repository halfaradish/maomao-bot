"""
DiTing-NoneBot 启动入口。

使用 ``python bot.py`` 替代 ``nb run`` 启动项目。

启动流程：
  1. 加载 .env 环境变量（通过 src.config 的模块级副作用）
  2. nonebot.init() — 初始化 Driver、Config
  3. 导入 src.api — 注册 FastAPI 路由（内部调用 get_app()）
  4. 注册 OneBot V11 适配器
  5. 从 pyproject.toml 加载所有插件
  6. 加载内置插件 echo
  7. nonebot.run() — 启动服务
"""

from nonebot import get_driver, init, load_builtin_plugin, load_from_toml, run

# ── 加载 .env 文件 ──────────────────────────────────────────
# src.config.__init__ 导入 local_config 模块，触发以下副作用：
#   load_dotenv(".env")           → 加载基础配置
#   load_dotenv(f".env.{ENV}")    → 加载环境特定配置
# 这必须在 nonebot.init() 之前完成
import src.config  # noqa: E402, F401

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

# ── Step 7: 启动 ────────────────────────────────────────────────────
run()
