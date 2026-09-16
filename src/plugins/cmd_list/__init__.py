import asyncio

from nonebot import get_driver, get_plugin_config, on_command, logger
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageSegment, MessageEvent
from typing import Optional

from .config import Config
from .get_plugin_usage import get_help_usage, get_plugin_detail
from .img_generator import get_img, get_detail_img, refresh_img, preheat, shutdown_browser
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor
from src.common.permission import ADMIN_PERM_KEY, check_permission

config = get_plugin_config(Config)
driver = get_driver()

__plugin_meta__ = PluginMetadata(
    name="帮助菜单",
    description="生成插件帮助菜单",
    usage="/help 查看已加载插件列表\n/help -n 插件名 查看插件详情\n/help -id 插件ID 查看插件详情\n/help -refresh 管理员强制刷新帮助图缓存",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.BASE.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)

help_cmd = on_command("help", priority=config.priority, block=config.block)


@driver.on_startup
async def _preheat_help_cache():
    # 后台预热，不阻塞启动
    asyncio.create_task(preheat())


@driver.on_shutdown
async def _close_help_browser():
    await shutdown_browser()


@help_cmd.handle()
async def _(event: MessageEvent):
    text = event.raw_message
    _, _, result = text.partition('help')
    args = result.split()

    if any(arg in ('-refresh', '--refresh') for arg in args):
        if not await check_permission(event, ADMIN_PERM_KEY):
            await help_cmd.finish("仅管理员可刷新帮助图缓存")
        await generate_all_plugins(help_cmd, force=True)
        return

    # 指定插件名
    assign_name = None
    for idx, arg in enumerate(args):
        if arg in ['-n', '-name', '--name']:
            assign_name = args[idx + 1]
            break

    assign_id = None
    for idx, arg in enumerate(args):
        if arg in ['-id']:
            assign_id = args[idx + 1]
            break

    if assign_name:
        await generate_detail(help_cmd, assign_name)
    elif assign_id:
        try:
            await generate_detail(help_cmd, plugin_id=int(assign_id))
        except ValueError:
            await help_cmd.finish(f"无效的插件ID: {assign_id}")
    else:
        await generate_all_plugins(help_cmd)

async def generate_detail(matcher: type[Matcher], plugin_name: Optional[str] = None, plugin_id: Optional[int] = None):
    if plugin_name:
        plugin_data = get_plugin_detail(plugin_name=plugin_name)
    elif plugin_id:
        plugin_data = get_plugin_detail(plugin_id=plugin_id)
    if not plugin_data:
        identifier = plugin_name if plugin_name else f"ID:{plugin_id}"
        await matcher.finish(f"未找到插件: {identifier}")

    identifier = plugin_name if plugin_name else f"ID:{plugin_id}"
    logger.info(f"正在生成插件详情: {identifier}")

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

async def generate_all_plugins(matcher: type[Matcher], force: bool = False):
    plugins_data = get_help_usage()
    if not plugins_data:
        await matcher.finish("没有插件信息")

    if force:
        logger.info(f"管理员强制刷新帮助菜单，共 {len(plugins_data)} 个插件")
    else:
        logger.info(f"正在生成帮助菜单，共 {len(plugins_data)} 个插件")

    try:
        if force:
            img = await refresh_img(plugins_data)
            if not img:
                await matcher.finish("帮助图缓存刷新失败，请查看日志")
        else:
            img = await get_img(plugins_data)
            if not img:
                await matcher.finish("图片生成失败")

        await matcher.finish(MessageSegment.image(img))
    except FinishedException:
        return
    except Exception as e:
        logger.error(f"生成帮助菜单失败: {e}")
        await matcher.finish("生成帮助菜单时发生错误")
