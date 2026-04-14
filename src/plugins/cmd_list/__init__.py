from nonebot import get_plugin_config, on_command, logger
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import  MessageSegment, MessageEvent
from pathlib import Path

from .config import Config
from .get_plugin_usage import get_help_usage, get_plugin_detail
from .img_generator import get_img, get_detail_img
from .model import PluginGroupEnum

config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="帮助菜单",
    description="生成插件帮助菜单",
    usage="/help 查看已加载插件列表\n/help -n 插件名 查看插件详情",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.BASE.value,
        "badge_color": "green"
    }
)

help_cmd = on_command("help")

TEMPLATE_PATH = Path(__file__).parent
TEMPLATE_FILENAME = "help_template.html"

@help_cmd.handle()
async def _(event: MessageEvent):
    text = event.raw_message
    _, _, result = text.partition('help')
    args = result.split()
    # 指定插件名
    assign_name = None
    for idx, arg in enumerate(args):
        if arg in ['-n', '-name', '--name']:
            assign_name = args[idx + 1]
            break

    if assign_name:
        await generate_detail(help_cmd, assign_name)
    else:
        await generate_all_plugins(help_cmd)

async def generate_detail(matcher: type[Matcher], plugin_name: str):
    plugin_data = get_plugin_detail(plugin_name)
    if not plugin_data:
        await matcher.finish(f"未找到插件: {plugin_name}")

    logger.info(f"正在生成插件详情: {plugin_name}")

    try:
        img = await get_detail_img(plugin_data)
        if not img:
            await matcher.finish("详情图片生成失败")

        await matcher.finish(MessageSegment.image(img))
    except FinishedException:
        return
    except Exception as e:
        logger.error(f"生成插件详情失败: {e}")
        await matcher.finish("生成插件详情时发生错误")

async def generate_all_plugins(matcher: type[Matcher]):
    plugins_data = get_help_usage()
    if not plugins_data:
        await matcher.finish("没有插件信息")

    logger.info(f"正在生成帮助菜单，共 {len(plugins_data)} 个插件")

    try:
        img = await get_img(plugins_data)
        if not img:
            await matcher.finish("图片生成失败")

        await matcher.finish(MessageSegment.image(img))
    except FinishedException:
        return
    except Exception as e:
        logger.error(f"生成帮助菜单失败: {e}")
        await matcher.finish("生成帮助菜单时发生错误")
