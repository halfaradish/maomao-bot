from nonebot import (
    on_command,
    logger,
    get_plugin_config
)
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    Bot,
    MessageSegment
)
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg

import json
import http.client
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from sqlalchemy import select

from .config import Config
from .image_generator import BsCountImageGenerator
from ...common import JsonUtils
from ...config import QQControlConfig
from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from src.common.permission import check_permission, get_bound_group_ids
from src.common.permission.cache import perm_cache
from src.common.database import async_session_factory
from src.common.permission.models import PermissionGroup, GroupPermBinding

from . import permissions  # noqa: F401

# 加载插件配置
config = get_plugin_config(Config)
bs_count_image_generator = BsCountImageGenerator()

api_host: str = QQControlConfig.QQ_CONTROL_HOST
api_port: int = QQControlConfig.QQ_CONTROL_PORT
api_token: str = 'Bearer ' + QQControlConfig.QQ_CONTROL_TOKEN

# 权限组名称
POST_PG_NAME = "shit_transport_post"
RECEIVE_PG_NAME = "shit_transport_receive"

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="搬史小助手",
    description="用于在多个群组间转发消息的插件，支持配置可发送和可接收的群组",
    usage="搬史 -- 转发引用的消息到所有可接收群组\n搬史 list -- 查看转发群组列表\n搬史 addpost <群号> -- 添加可发送群组（仅超级管理员）\n搬史 addreceive <群号> -- 添加可接收群组（仅超级管理员）\n搬史 rmpost <群号> -- 移除可发送群组（仅超级管理员）\n搬史 rmreceive <群号> -- 移除可接收群组（仅超级管理员）\n搬史 count -- 查看使用次数统计",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)

# 命令处理器
transport_manual = on_command(
    "搬史",
    aliases={"搬屎", "转发", "banshi", "bs"},
    priority=config.bs_priority,
    block=config.bs_block
)

@dataclass
class GroupInfo:
    """群组信息数据类"""
    group_id: int
    group_name: str

class TransportService:
    """消息转发服务类，封装转发相关的核心逻辑"""

    @staticmethod
    def ensure_data_initialized():
        """确保统计数据结构已初始化"""
        JsonUtils.read(config.bs_data_filename, {
            config.banshi_frequency_statistics: {},
            config.postshi_frequency_statistics: {}
        })

    @staticmethod
    def update_frequency_statistics(
        transmit_shit_user_id: str,
        transmit_shit_nickname: str,
        post_shit_user_id: str,
        post_shit_nickname: str
    ):
        """搬史插件使用频率统计更新"""
        TransportService.ensure_data_initialized()
        data, _ = JsonUtils.read(config.bs_data_filename, {
            config.banshi_frequency_statistics: {},
            config.postshi_frequency_statistics: {}
        })

        transmit_freq: Dict[str, Any] = data.get(config.banshi_frequency_statistics, {})
        transmit_user_stats = transmit_freq.get(transmit_shit_user_id, {"count": 0})
        transmit_freq[transmit_shit_user_id] = {
            "count": transmit_user_stats.get("count", 0) + 1,
            "nickname": transmit_shit_nickname
        }

        post_freq: Dict[str, Any] = data.get(config.postshi_frequency_statistics, {})
        post_user_stats = post_freq.get(post_shit_user_id, {"count": 0})
        post_freq[post_shit_user_id] = {
            "count": post_user_stats.get("count", 0) + 1,
            "nickname": post_shit_nickname
        }

        JsonUtils.update(config.bs_data_filename, {
            config.banshi_frequency_statistics: transmit_freq,
            config.postshi_frequency_statistics: post_freq
        })

    @staticmethod
    def forward_group_single_msg(group_id: int, message_id: int) -> bool:
        """转发消息到指定群组"""
        try:
            conn = http.client.HTTPConnection(api_host, api_port)
            headers = {
                'Content-Type': 'application/json',
                'Authorization': api_token
            }
            payload = json.dumps({
                "group_id": group_id,
                "message_id": message_id
            })

            conn.request("POST", "/forward_group_single_msg", payload, headers)
            res = conn.getresponse()
            res_content = res.read().decode()
            logger.info(f"转发消息到群 {group_id} 的结果: {res_content}")
            return res.status < 300

        except Exception as e:
            logger.opt(exception=True).error(f"转发消息到群 {group_id} 时出错: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()

    @staticmethod
    async def add_group_binding(pg_name: str, group_id: int) -> Optional[str]:
        """添加群绑定到指定权限组"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
            )
            pg = result.scalars().first()
            if not pg:
                return f"权限组 {pg_name} 不存在"

            # 检查是否已绑定
            existing = await session.execute(
                select(GroupPermBinding.id).where(
                    GroupPermBinding.permission_group_id == pg.id,
                    GroupPermBinding.qq_group_id == group_id,
                ).limit(1)
            )
            if existing.first() is not None:
                return f"群 {group_id} 已经在列表中"

            session.add(GroupPermBinding(permission_group_id=pg.id, qq_group_id=group_id))
            await session.commit()
            perm_cache.clear_all()
            return None

    @staticmethod
    async def remove_group_binding(pg_name: str, group_id: int) -> Optional[str]:
        """从指定权限组移除群绑定"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
            )
            pg = result.scalars().first()
            if not pg:
                return f"权限组 {pg_name} 不存在"

            result = await session.execute(
                select(GroupPermBinding).where(
                    GroupPermBinding.permission_group_id == pg.id,
                    GroupPermBinding.qq_group_id == group_id,
                )
            )
            bindings = result.scalars().all()
            if not bindings:
                return f"群 {group_id} 不在列表中"

            for binding in bindings:
                await session.delete(binding)
            await session.commit()
            perm_cache.clear_all()
            return None

async def _get_group_name_map(bot: Bot) -> Dict[int, str]:
    """获取 bot 已加入群的 group_id -> group_name 映射"""
    try:
        group_list = await bot.call_api("get_group_list")
        return {g["group_id"]: g.get("group_name", "未知") for g in group_list}
    except Exception as e:
        logger.warning(f"获取群列表失败: {e}")
        return {}

async def handle_forward_operation(bot: Bot, event: GroupMessageEvent, message_id: int) -> str:
    """处理消息转发操作"""
    source_group_id = event.group_id

    # 权限检查：当前群是否允许使用搬史命令
    if not await check_permission(event, "shit_transport:use"):
        logger.warning(f"群组 {source_group_id} 不在可发送列表中")
        return "当前群组没有权限使用搬史功能"

    # 获取接收群组列表
    receive_group_ids = await get_bound_group_ids(RECEIVE_PG_NAME)

    if not receive_group_ids:
        logger.warning(f"空接收群组列表 (用户:{event.user_id} 群组:{event.group_id})")
        return "没有配置可接收的群组"

    # 转发消息
    success_cnt = 0
    error_groups = []

    for group_id in receive_group_ids:
        # 跳过源群组
        if group_id == source_group_id:
            continue

        if TransportService.forward_group_single_msg(group_id=group_id, message_id=message_id):
            success_cnt += 1
        else:
            error_groups.append(str(group_id))

    # 使用频率统计更新
    TransportService.update_frequency_statistics(
        transmit_shit_user_id=str(event.sender.user_id),
        transmit_shit_nickname=event.sender.nickname,
        post_shit_user_id=str(event.reply.sender.user_id),
        post_shit_nickname=event.reply.sender.nickname
    )

    # 构建结果消息
    result_msg = f"已成功转发到 {success_cnt} 个群组"
    if error_groups:
        result_msg += f"\n以下群组发送失败: {', '.join(error_groups)}"

    return result_msg

async def handle_list_operation(bot: Bot) -> str:
    """处理列出转发群组操作"""
    name_map = await _get_group_name_map(bot)

    post_ids = await get_bound_group_ids(POST_PG_NAME)
    receive_ids = await get_bound_group_ids(RECEIVE_PG_NAME)

    post_str = "\n".join(
        f"群号：{gid}  群名：{name_map.get(gid, '未知')}"
        for gid in post_ids
    )
    receive_str = "\n".join(
        f"群号：{gid}  群名：{name_map.get(gid, '未知')}"
        for gid in receive_ids
    )

    result_msg = ""
    result_msg += f"可发送搬史命令的群组 (post_groups):\n"
    result_msg += post_str if post_ids else "无"
    result_msg += "\n\n"
    result_msg += f"可接收转发内容的群组 (receive_groups):\n"
    result_msg += receive_str if receive_ids else "无"

    return result_msg

async def handle_list_post_operation(bot: Bot) -> str:
    """处理列出可发送群组操作"""
    name_map = await _get_group_name_map(bot)
    post_ids = await get_bound_group_ids(POST_PG_NAME)

    if not post_ids:
        return "没有配置可发送的群组"

    group_list = "\n".join(
        f"群号：{gid}  群名：{name_map.get(gid, '未知')}"
        for gid in post_ids
    )

    return f"可发送搬史命令的群组:\n{group_list}"

async def handle_list_receive_operation(bot: Bot) -> str:
    """处理列出可接收群组操作"""
    name_map = await _get_group_name_map(bot)
    receive_ids = await get_bound_group_ids(RECEIVE_PG_NAME)

    if not receive_ids:
        return "没有配置可接收的群组"

    group_list = "\n".join(
        f"群号：{gid}  群名：{name_map.get(gid, '未知')}"
        for gid in receive_ids
    )

    return f"可接收转发内容的群组:\n{group_list}"

def build_count_rows(statistics: Dict[str, Any], action_text: str, is_show_all: bool) -> List[Dict[str, Any]]:
    sorted_items = sorted(statistics.items(), key=lambda x: x[1].get('count', 0), reverse=True)
    rows: List[Dict[str, Any]] = []
    for _, user_info in sorted_items:
        rows.append({
            'nickname': user_info.get('nickname') or '未知用户',
            'count': int(user_info.get('count', 0)),
            'action_text': action_text,
        })
    return rows

async def handle_count_image_operation(is_show_all: bool) -> bytes:
    banshi_freq = TransportService.get_banshi_frequency_statistics()
    postshi_freq = TransportService.get_postshi_frequency_statistics()
    transmit_rows = build_count_rows(banshi_freq, '搬史', is_show_all)
    post_rows = build_count_rows(postshi_freq, '发史', is_show_all)
    return bs_count_image_generator.generate_image(
        transmit_rows=transmit_rows,
        post_rows=post_rows,
        is_show_all=is_show_all,
        max_show_count=config.bs_max_show_cnt,
    )

async def handle_count_operation(is_show_all: bool) -> str:
    """处理使用次数统计操作"""
    banshi_freq = TransportService.get_banshi_frequency_statistics()
    postshi_freq = TransportService.get_postshi_frequency_statistics()
    transmit_rows = build_count_rows(banshi_freq, '搬史', is_show_all)
    post_rows = build_count_rows(postshi_freq, '发史', is_show_all)

    res_msg = "搬史插件使用次数统计(使用bs命令的用户)"
    if not transmit_rows:
        res_msg += "\n无使用记录"
    else:
        for row in transmit_rows:
            res_msg += f"\n{row['nickname']} {row['action_text']} {row['count']} 次"

    res_msg += "\n\n发史数据统计(被bs命名转发消息的用户)"
    if not post_rows:
        res_msg += "\n无使用记录"
    else:
        for row in post_rows:
            res_msg += f"\n{row['nickname']} {row['action_text']} {row['count']} 次"

    return res_msg

@transport_manual.handle()
async def handle_transport(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """处理搬史命令的主函数"""
    raw_args = args.extract_plain_text().strip()
    params = raw_args.split() if raw_args else []

    try:
        # 无参数模式 - 转发消息
        if not params:
            # 检查是否有引用消息
            if not event.reply:
                await bot.send(event=event, message=config.HELP_MSG)
                return

            message_id = event.reply.message_id
            result_msg = await handle_forward_operation(bot, event, message_id)
            await bot.send(event=event, message=result_msg)
            return

        # 命令参数模式
        command = params[0].lower()

        if command in ["list", "ls", "查看", "查询"]:
            # 查看转发群组列表
            result_msg = await handle_list_operation(bot)
            await bot.send(event=event, message=result_msg)
        elif command in ["listpost", "lspost", "查看发送"]:
            # 查看可发送群组列表
            result_msg = await handle_list_post_operation(bot)
            await bot.send(event=event, message=result_msg)
        elif command in ["listreceive", "lsreceive", "查看接收"]:
            # 查看可接收群组列表
            result_msg = await handle_list_receive_operation(bot)
            await bot.send(event=event, message=result_msg)

        elif command in ["addpost", "添加发送"]:
            # 添加可发送群组（仅超级管理员）
            if str(event.user_id) not in bot.config.superusers:
                await bot.send(event=event, message="仅超级管理员可执行此操作")
                return
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return

            group_id = int(params[1])
            # 检查bot是否已加入该群组
            name_map = await _get_group_name_map(bot)
            if group_id not in name_map:
                await bot.send(event=event, message=f"bot 还未加入群组 {group_id} 中")
                return

            error_msg = await TransportService.add_group_binding(POST_PG_NAME, group_id)

            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 添加到可发送列表")

        elif command in ["addreceive", "添加接收"]:
            # 添加可接收群组（仅超级管理员）
            if str(event.user_id) not in bot.config.superusers:
                await bot.send(event=event, message="仅超级管理员可执行此操作")
                return
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return

            group_id = int(params[1])
            name_map = await _get_group_name_map(bot)
            if group_id not in name_map:
                await bot.send(event=event, message=f"bot 还未加入群组 {group_id} 中")
                return

            error_msg = await TransportService.add_group_binding(RECEIVE_PG_NAME, group_id)

            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 添加到可接收列表")

        elif command in ["rmpost", "删除发送", "移除发送"]:
            # 删除可发送群组（仅超级管理员）
            if str(event.user_id) not in bot.config.superusers:
                await bot.send(event=event, message="仅超级管理员可执行此操作")
                return
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return

            group_id = int(params[1])
            error_msg = await TransportService.remove_group_binding(POST_PG_NAME, group_id)

            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 从可发送列表中移除")

        elif command in ["rmreceive", "删除接收", "移除接收"]:
            # 删除可接收群组（仅超级管理员）
            if str(event.user_id) not in bot.config.superusers:
                await bot.send(event=event, message="仅超级管理员可执行此操作")
                return
            if len(params) < 2 or not params[1].isdigit():
                await bot.send(event=event, message="请提供合法的群号")
                return

            group_id = int(params[1])
            error_msg = await TransportService.remove_group_binding(RECEIVE_PG_NAME, group_id)

            if error_msg:
                await bot.send(event=event, message=error_msg)
            else:
                await bot.send(event=event, message=f"已将群 {group_id} 从可接收列表中移除")

        elif command in ["count", "计数", "统计"]:
            # 查看使用次数统计
            is_show_all = True
            image_bytes = await handle_count_image_operation(is_show_all)
            await bot.send(event=event, message=MessageSegment.image(image_bytes))


    except Exception as e:
        logger.opt(exception=True).error(f"搬史小助手发生错误: {e}")
        await bot.send(event=event, message=f"处理请求时发生错误: {str(e)}")
