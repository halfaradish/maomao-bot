from nonebot import (
    get_plugin_config,
    on_notice,
    logger,
    on_message,
    get_driver,
    on_command,
)
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11.permission import GROUP
from nonebot.adapters.onebot.v11 import (
    GroupIncreaseNoticeEvent,
    GroupDecreaseNoticeEvent,
    Message,
    MessageSegment,
    GroupMessageEvent,
    Bot,
    ActionFailed,
    MessageEvent,
)
from nonebot.params import CommandArg
from nonebot.utils import run_sync  # 引入 run_sync 用于在异步中运行同步的模型推理

from datetime import datetime, timedelta
import asyncio
import threading
import time

from sqlalchemy import select

from .config import Config
from ...common.send_forward_msg import send_forward_msg
from ..logging_info.message_dao import message_dao
from ...common.utils import QQAvatarLoader
from src.common.model.model import PluginGroupEnum, PluginBadgeColor
from src.common.database import async_session_factory
from src.common.permission.models import (
    PermissionGroup,
    PermissionGroupPerm,
    GroupPermBinding,
)
from src.common.permission.cache import perm_cache
from src.common.permission.supervisor import is_superuser
from .group_checker import is_group_feature_enabled, get_ban_word_log_targets
from . import permissions  # noqa: F401 — 注册权限点到权限系统

# 假设你的 predict.py 在同级目录下，如果不是，请修改 import 路径
# 例如：from src.plugins.ai_train.predict import predict
from .predict import predict
__plugin_meta__ = PluginMetadata(
    name="群管理助手",
    description="自动管理群成员，包括欢迎新成员、处理离开成员以及检测违禁词",
    usage="自动运行，无需手动操作",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.GROUP_MANAGE.value,
        "badge_color": PluginBadgeColor.BLUE.value
    }
)

plugin_config = get_plugin_config(Config)

def is_group_increase(event) -> bool:
    return isinstance(event, GroupIncreaseNoticeEvent)
def is_group_decrease(event) -> bool:
    return isinstance(event, GroupDecreaseNoticeEvent)

group_increase = on_notice(rule=Rule(is_group_increase), priority=5, block=False)
group_decrease = on_notice(rule=Rule(is_group_decrease), priority=5, block=False)

# get_monitored_groups() 已废弃 — 群列表已迁移到权限系统的 GroupPermBinding。
# 请使用 is_group_feature_enabled(group_id, perm_key) 替代。
# 迁移脚本: migrate.py

@group_increase.handle()
async def _(event: GroupIncreaseNoticeEvent):
    if not plugin_config.auto_manage_increase:
        return
    # 获取信息
    user_id: str = str(event.user_id)
    operator_id: str = str(event.operator_id)
    group_id: int = event.group_id
    sub_type: str = event.sub_type

    if not await is_group_feature_enabled(group_id, "auto_manage_group:increase"):
        return

    increase_user: Message = Message([MessageSegment.at(user_id=user_id)])
    operator: Message = Message([MessageSegment.at(user_id=operator_id)])
    if sub_type == 'invite':
        await group_increase.finish("欢迎新成员 " + increase_user + f"({user_id}) 加入本群\n邀请人: " + operator + f"({operator_id})")
    else:
        await group_increase.finish("欢迎新成员 " + increase_user + f"({user_id}) 通过群号或二维码加入本群\n处理人: " + operator + f"({operator_id})")

@group_decrease.handle()
async def _(event: GroupDecreaseNoticeEvent):
    if not plugin_config.auto_manage_decrease:
        return
    user_id: str = str(event.user_id)
    operator_id: str = str(event.operator_id)
    group_id: int = event.group_id
    sub_type: str = event.sub_type

    if not await is_group_feature_enabled(group_id, "auto_manage_group:decrease"):
        return

    decrease_user: Message = Message([MessageSegment.at(user_id=user_id)])
    operator: Message = Message([MessageSegment.at(user_id=operator_id)])
    if sub_type == 'leave':
        await group_decrease.finish(decrease_user + f"({user_id}) 主动离开了本群")
    elif sub_type == 'kick':
        await group_decrease.finish(decrease_user + f"({user_id}) 被踢出了本群\n处理人：" + operator + f"({operator_id})")


# 临时功能
@run_sync
def async_predict(text: str):
    return predict(text)


async def contains_banned_word(event: GroupMessageEvent) -> bool:
    """
    使用模型判断是否包含违禁内容
    """
    if not plugin_config.auto_manage_banned_word_enable:
        return False
    # 1. 检查群是否开启了违禁词检测功能（权限系统）
    group_id = event.group_id
    if not await is_group_feature_enabled(group_id, "auto_manage_group:ban_word_detect"):
        return False

    # 2. 检查发送者权限 (管理员/群主免检)
    sender_role = event.sender.role
    if sender_role in ["admin", "owner"]:
        return False

    # 3. 检查群等级 (等级 >= 3 免检)
    user_level = event.sender.level or 0
    if user_level >= 3:
        return False

    # 4. 获取纯文本消息
    message_txt = event.get_message().extract_plain_text().strip()
    if not message_txt:
        return False

    # 5. 调用模型进行预测
    try:
        result = await async_predict(message_txt)
        if result.get("is_malicious"):
            logger.info(f"模型拦截消息: {message_txt} | 标签: {result.get('label')}")
            return True
        return False

    except Exception as e:
        logger.error(f"模型预测出错: {e}")
        return False


# 注册 Matcher
banned_word_detector = on_message(
    rule=Rule(contains_banned_word),  # Rule 支持 async 函数
    permission=GROUP,
    priority=20,
    block=False  # 建议设为 False，避免拦截其他插件，除非你确定要截断
)

async def context_erase_messages(bot: Bot, user_id: int, group_id: int, base_time: int, base_message_id: int):
    """上下文撤回消息"""
    try:
        # 等待延迟时间，确保logging_info插件完成消息存储
        await asyncio.sleep(plugin_config.context_erase_delay)
        
        # 计算时间范围
        start_time = base_time - plugin_config.context_erase_time_range
        end_time = base_time + plugin_config.context_erase_time_range
        
        logger.info(f"开始上下文撤回: 用户{user_id}, 群组{group_id}, 时间范围{start_time}-{end_time}")
        
        # 从数据库查询该用户在指定时间范围内的所有消息
        from sqlalchemy import select, and_
        from src.common.database import async_session_factory
        from src.common.models.botdb_models import MessageEventLog

        async with async_session_factory() as session:
            stmt = select(MessageEventLog).where(
                and_(
                    MessageEventLog.user_id == user_id,
                    MessageEventLog.group_id == group_id,
                    MessageEventLog.time >= start_time,
                    MessageEventLog.time <= end_time,
                    MessageEventLog.message_id != base_message_id,
                )
            ).order_by(MessageEventLog.time)
            result = await session.execute(stmt)
            messages = list(result.scalars().all())
        
        # 调试日志：显示查询到的消息详情
        if messages:
            logger.info(f"查询到 {len(messages)} 条消息，时间范围: {start_time} - {end_time}")
            for i, msg in enumerate(messages[:5]):  # 只显示前5条消息的详情
                logger.info(f"消息{i+1}: ID={msg.message_id}, 时间={msg.time}, 内容长度={len(msg.raw_message)}")
        
        if not messages:
            logger.info("未找到需要撤回的上下文消息")
            return {"total": 0, "success": 0, "failed": 0, "messages": []}
            
        logger.info(f"找到 {len(messages)} 条需要撤回的上下文消息")
        
        # 批量撤回消息
        success_count = 0
        fail_count = 0
        successful_erased_messages = []  # 存储成功撤回的消息
        failed_erased_messages = []  # 存储撤回失败的消息
        
        # 创建异步撤回函数
        async def delete_message(msg):
            try:
                await bot.delete_msg(message_id=msg.message_id)
                return {"status": "success", "message_id": msg.message_id, "msg": msg}
            except ActionFailed as e:
                return {"status": "failed", "message_id": msg.message_id, "error": e, "msg": msg}
            except Exception as e:
                return {"status": "error", "message_id": msg.message_id, "error": e, "msg": msg}
        
        # 按顺序执行撤回任务，每次撤回前添加间隔延迟
        results = []
        for msg in messages:
            # 在每次撤回前添加配置的间隔延迟
            await asyncio.sleep(plugin_config.context_erase_retry_delay)
            
            # 执行撤回任务
            result = await delete_message(msg)
            results.append(result)
        
        # 统计结果
        for result in results:
            if isinstance(result, dict):
                if result["status"] == "success":
                    success_count += 1
                    successful_erased_messages.append(result["msg"])  # 记录成功撤回的消息
                    logger.info(f"成功撤回消息: {result['message_id']}")
                else:
                    fail_count += 1
                    failed_erased_messages.append(result["msg"])  # 记录撤回失败的消息
                    if result["status"] == "failed":
                        logger.warning(f"撤回消息失败: {result['message_id']}, 错误: {result.get('error', 'Unknown')}")
                    else:
                        logger.error(f"撤回消息异常: {result['message_id']}, 错误: {result.get('error', 'Unknown')}")
        
        logger.info(f"上下文撤回完成: 成功{success_count}条, 失败{fail_count}条")
        
        # 返回撤回统计信息和消息内容
        return {
            "total": len(messages),
            "success": success_count,
            "failed": fail_count,
            "messages": [{
                "message_id": msg.message_id,
                "time": msg.time,
                "content": msg.raw_message
            } for msg in successful_erased_messages],
            "failed_messages": [{
                "message_id": msg.message_id,
                "time": msg.time,
                "content": msg.raw_message
            } for msg in failed_erased_messages]
        }
        
    except Exception as e:
        logger.error(f"上下文撤回过程异常: {e}")
        return {"total": 0, "success": 0, "failed": 0, "messages": []}


@banned_word_detector.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    user_id = event.user_id
    user_group_card = event.sender.card or event.sender.nickname
    group_id = event.group_id
    message_id = event.message_id
    current_time = event.time

    # 获取群信息
    try:
        group_info = await bot.get_group_info(group_id=group_id)
        group_name = group_info.get('group_name', '???')
    except Exception as e:
        logger.error(f"获取群信息失败: {e}")
        group_name = '???'
    # 获取用户头像
    try:
        user_avatar = await QQAvatarLoader.download_avatar(user_id=user_id, size=40)
    except Exception as e:
        logger.error(f"下载头像失败: {e}")
        user_avatar = None  # 或默认头像路径
    try:
        # 禁言用户
        await bot.set_group_ban(
            group_id=group_id,
            user_id=user_id,
            duration=3600
        )

        # 撤回当前消息
        await bot.delete_msg(message_id=message_id)

        user_segment = MessageSegment.at(user_id=user_id)
        await banned_word_detector.send("检测到消息包含违规词，已对 " + user_segment + f"({user_id})禁言 1 小时")

        # 启动上下文撤回任务并获取结果
        erase_result = await context_erase_messages(bot, user_id, group_id, current_time, message_id)

        # 构建日志消息
        remind_msgs = []
        base_msg = f"在群组：{group_name}({group_id}) 检测到违禁消息\n违禁用户：{user_group_card}({user_id})\n"
        if user_avatar:
            base_msg += MessageSegment.image(user_avatar) + "\n"
        base_msg += f"时间：{datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}"
        remind_msgs.append(base_msg)
        remind_msgs.append("违禁消息如下")
        remind_msgs.append(str(event.get_message()))
        
        # 添加上下文撤回统计信息
        if erase_result:
            total_messages = erase_result["total"]
            success_count = erase_result["success"]
            failed_count = erase_result["failed"]
            
            if total_messages == 0:
                remind_msgs.append(f"上下文撤回统计：\n共{total_messages}条消息")
            else:
                remind_msgs.append(f"上下文撤回统计：\n共{total_messages}条消息\n成功撤回{success_count}条\n失败{failed_count}条")
            
            # 展示被撤回的消息内容
            if erase_result["messages"]:
                remind_msgs.append("被撤回的消息内容：")
                for i, msg_info in enumerate(erase_result["messages"], 1):
                    msg_time = datetime.fromtimestamp(msg_info["time"]).strftime('%Y-%m-%d %H:%M:%S')
                    remind_msgs.append(f"{i}. [{msg_time}] {msg_info['content']}")
            
            # 展示撤回失败的消息内容
            if erase_result.get("failed_messages"):
                remind_msgs.append("撤回失败的消息内容：")
                for i, msg_info in enumerate(erase_result["failed_messages"], 1):
                    msg_time = datetime.fromtimestamp(msg_info["time"]).strftime('%Y-%m-%d %H:%M:%S')
                    remind_msgs.append(f"{i}. [{msg_time}] {msg_info['content']}")
        else:
            remind_msgs.append("上下文撤回机制已启动")

        # 发送告警日志到所有绑定了告警日志权限的群
        ban_words_remind_groups = await get_ban_word_log_targets()
        for remind_group in ban_words_remind_groups:
            await send_forward_msg.by_onebot_api(bot=bot, event=event, messges=remind_msgs, group_id=str(remind_group))

    except ActionFailed as e:
        logger.error(f"操作失败: {e}")
    except Exception as e:
        logger.error(f"未知错误: {e}")


# ============================================================
# 启动钩子：自动创建 auto_manage_group 的默认权限组
# ============================================================

@get_driver().on_startup
async def _ensure_default_perm_groups():
    """确保 auto_manage_group 的默认权限组存在

    自动创建 4 个权限组，每个组包含对应的权限点。
    已存在的权限组不会被重复创建。
    """
    default_groups = [
        ("auto_manage_increase", "auto_manage_group:increase", "入群欢迎"),
        ("auto_manage_decrease", "auto_manage_group:decrease", "离群通知"),
        ("auto_manage_ban_word", "auto_manage_group:ban_word_detect", "违禁词检测"),
        ("auto_manage_ban_word_log", "auto_manage_group:ban_word_log_target", "违禁词告警日志"),
    ]
    async with async_session_factory() as session:
        for group_name, perm_key, display_name in default_groups:
            existing = (await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == group_name)
            )).scalars().first()
            if not existing:
                pg = PermissionGroup(
                    name=group_name,
                    display_name=display_name,
                    description=f"自动创建：{display_name}功能权限组",
                    created_by=0,  # 系统自动创建
                )
                session.add(pg)
                await session.flush()
                session.add(PermissionGroupPerm(group_id=pg.id, perm_key=perm_key))
                logger.info(f"[auto_manage_group] 自动创建权限组: {group_name} (perm_key={perm_key})")
        await session.commit()


# ============================================================
# 管理命令：群管理 监控 / 取消监控 / 列表 / 告警日志目标
# ============================================================

FEATURE_MAP = {
    "入群欢迎": ("auto_manage_group:increase", "auto_manage_increase"),
    "离群通知": ("auto_manage_group:decrease", "auto_manage_decrease"),
    "违禁词检测": ("auto_manage_group:ban_word_detect", "auto_manage_ban_word"),
    "告警日志": ("auto_manage_group:ban_word_log_target", "auto_manage_ban_word_log"),
}

manage_cmd = on_command(
    "群管理",
    aliases={"group_manage"},
    priority=10,
    block=True,
)


@manage_cmd.handle()
async def _manage_help(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """群管理命令入口

    用法：
      群管理 监控 <群号> [功能]     — 将群加入监控（功能: 入群欢迎/离群通知/违禁词检测/告警日志/全部）
      群管理 取消监控 <群号> [功能]  — 将群移出监控
      群管理 列表 [群号]             — 查看群的监控状态
      群管理 告警日志目标 添加 <群号> — 添加告警日志接收群
      群管理 告警日志目标 移除 <群号> — 移除告警日志接收群
      群管理 告警日志目标 列表       — 查看所有告警日志接收群
    """
    if not is_superuser(event.user_id):
        await manage_cmd.finish("仅超级管理员可使用群管理命令")
        return

    text = args.extract_plain_text().strip()
    if not text:
        await manage_cmd.finish(
            "群管理 用法：\n"
            "  群管理 监控 <群号> [功能]    — 将群加入监控\n"
            "  群管理 取消监控 <群号> [功能] — 将群移出监控\n"
            "  群管理 列表 [群号]            — 查看监控状态\n"
            "  群管理 告警日志目标 添加 <群号> — 添加告警日志接收群\n"
            "  群管理 告警日志目标 移除 <群号> — 移除告警日志接收群\n"
            "  群管理 告警日志目标 列表      — 查看所有告警日志接收群\n"
            "功能: 入群欢迎 / 离群通知 / 违禁词检测 / 告警日志 / 全部"
        )
        return

    parts = text.split()
    sub_cmd = parts[0] if parts else ""

    if sub_cmd == "监控":
        await _handle_monitor_add(event, parts[1:])
    elif sub_cmd == "取消监控":
        await _handle_monitor_remove(event, parts[1:])
    elif sub_cmd == "列表":
        await _handle_monitor_list(event, parts[1:])
    elif sub_cmd == "告警日志目标":
        await _handle_log_target(event, parts[1:])
    else:
        await manage_cmd.finish(f"未知子命令: {sub_cmd}")


async def _parse_group_and_feature(parts: list[str]) -> tuple[int | None, str | None]:
    """解析群号和功能名"""
    group_id = None
    feature = None
    for part in parts:
        if part.isdigit():
            group_id = int(part)
        elif part in FEATURE_MAP:
            feature = part
        elif part == "全部":
            feature = "全部"
    return group_id, feature


async def _handle_monitor_add(event: MessageEvent, parts: list[str]):
    """将群加入监控"""
    group_id, feature = await _parse_group_and_feature(parts)
    if group_id is None:
        await manage_cmd.finish("请指定群号，用法: 群管理 监控 <群号> [功能]")
        return

    features = list(FEATURE_MAP.keys()) if not feature or feature == "全部" else [feature]
    unknown = [f for f in features if f not in FEATURE_MAP and f != "全部"]
    if unknown:
        await manage_cmd.finish(f"未知功能: {', '.join(unknown)}。可用: {', '.join(FEATURE_MAP.keys())} / 全部")
        return
    if feature == "全部":
        features = list(FEATURE_MAP.keys())

    async with async_session_factory() as session:
        for feat in features:
            perm_key, pg_name = FEATURE_MAP[feat]
            # 查找或创建权限组
            result = await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
            )
            pg = result.scalars().first()
            if not pg:
                pg = PermissionGroup(
                    name=pg_name,
                    display_name=feat,
                    description=f"自动创建：{feat}功能权限组",
                    created_by=0,
                )
                session.add(pg)
                await session.flush()
                session.add(PermissionGroupPerm(group_id=pg.id, perm_key=perm_key))

            # 检查是否已绑定
            existing = await session.execute(
                select(GroupPermBinding.id).where(
                    GroupPermBinding.qq_group_id == group_id,
                    GroupPermBinding.permission_group_id == pg.id,
                ).limit(1)
            )
            if existing.first() is None:
                session.add(GroupPermBinding(qq_group_id=group_id, permission_group_id=pg.id))
                # 清除该群的缓存
                perm_cache.delete(f"group_feature:{group_id}:{perm_key}")
                logger.info(f"[群管理] 群 {group_id} 已开启功能: {feat}")
            else:
                logger.info(f"[群管理] 群 {group_id} 已开启功能 {feat}，跳过")

        await session.commit()

    # 清除告警日志目标缓存（如果添加了告警日志）
    if "告警日志" in features:
        perm_cache.delete("ban_word_log_targets")

    await manage_cmd.finish(f"群 {group_id} 已开启功能: {', '.join(features)}")


async def _handle_monitor_remove(event: MessageEvent, parts: list[str]):
    """将群移出监控"""
    group_id, feature = await _parse_group_and_feature(parts)
    if group_id is None:
        await manage_cmd.finish("请指定群号，用法: 群管理 取消监控 <群号> [功能]")
        return

    features = list(FEATURE_MAP.keys()) if not feature or feature == "全部" else [feature]
    if feature == "全部":
        features = list(FEATURE_MAP.keys())

    async with async_session_factory() as session:
        for feat in features:
            perm_key, pg_name = FEATURE_MAP[feat]
            # 查找权限组
            result = await session.execute(
                select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
            )
            pg = result.scalars().first()
            if not pg:
                continue

            # 删除绑定
            result = await session.execute(
                select(GroupPermBinding).where(
                    GroupPermBinding.qq_group_id == group_id,
                    GroupPermBinding.permission_group_id == pg.id,
                )
            )
            bindings = result.scalars().all()
            for binding in bindings:
                await session.delete(binding)
            if bindings:
                # 清除缓存
                perm_cache.delete(f"group_feature:{group_id}:{perm_key}")
                logger.info(f"[群管理] 群 {group_id} 已关闭功能: {feat}")

        await session.commit()

    # 清除告警日志目标缓存
    if "告警日志" in features:
        perm_cache.delete("ban_word_log_targets")

    await manage_cmd.finish(f"群 {group_id} 已关闭功能: {', '.join(features)}")


async def _handle_monitor_list(event: MessageEvent, parts: list[str]):
    """查看群的监控状态"""
    group_id, _ = await _parse_group_and_feature(parts)

    async with async_session_factory() as session:
        if group_id:
            # 查看指定群
            lines = [f"群 {group_id} 监控状态："]
            for feat, (perm_key, pg_name) in FEATURE_MAP.items():
                result = await session.execute(
                    select(GroupPermBinding.id)
                    .join(
                        PermissionGroup,
                        GroupPermBinding.permission_group_id == PermissionGroup.id,
                    )
                    .join(
                        PermissionGroupPerm,
                        PermissionGroupPerm.group_id == PermissionGroup.id,
                    )
                    .where(
                        GroupPermBinding.qq_group_id == group_id,
                        PermissionGroupPerm.perm_key == perm_key,
                    )
                    .limit(1)
                )
                status = "✅ 已开启" if result.first() else "❌ 未开启"
                lines.append(f"  {feat}: {status}")
            await manage_cmd.finish("\n".join(lines))
        else:
            # 查看所有被监控的群（取并集）
            group_sets: dict[int, set[str]] = {}
            for feat, (perm_key, pg_name) in FEATURE_MAP.items():
                result = await session.execute(
                    select(GroupPermBinding.qq_group_id)
                    .join(
                        PermissionGroup,
                        GroupPermBinding.permission_group_id == PermissionGroup.id,
                    )
                    .join(
                        PermissionGroupPerm,
                        PermissionGroupPerm.group_id == PermissionGroup.id,
                    )
                    .where(PermissionGroupPerm.perm_key == perm_key)
                )
                for row in result.all():
                    gid = row[0]
                    if gid not in group_sets:
                        group_sets[gid] = set()
                    group_sets[gid].add(feat)

            if not group_sets:
                await manage_cmd.finish("当前没有任何群被监控")
                return

            lines = ["所有被监控的群："]
            for gid, feats in sorted(group_sets.items()):
                lines.append(f"  群 {gid}: {', '.join(sorted(feats))}")
            lines.append(f"\n共 {len(group_sets)} 个群")
            await manage_cmd.finish("\n".join(lines))


async def _handle_log_target(event: MessageEvent, parts: list[str]):
    """管理告警日志目标群"""
    perm_key = "auto_manage_group:ban_word_log_target"
    pg_name = "auto_manage_ban_word_log"

    async with async_session_factory() as session:
        # 确保权限组存在
        result = await session.execute(
            select(PermissionGroup).where(PermissionGroup.name == pg_name).limit(1)
        )
        pg = result.scalars().first()
        if not pg:
            pg = PermissionGroup(
                name=pg_name,
                display_name="违禁词告警日志",
                description="自动创建：违禁词告警日志功能权限组",
                created_by=0,
            )
            session.add(pg)
            await session.flush()
            session.add(PermissionGroupPerm(group_id=pg.id, perm_key=perm_key))
            await session.commit()

        sub = parts[0] if parts else ""

        if sub == "添加":
            gid_str = parts[1] if len(parts) > 1 else ""
            if not gid_str.isdigit():
                await manage_cmd.finish("用法: 群管理 告警日志目标 添加 <群号>")
                return
            gid = int(gid_str)
            existing = await session.execute(
                select(GroupPermBinding.id).where(
                    GroupPermBinding.qq_group_id == gid,
                    GroupPermBinding.permission_group_id == pg.id,
                ).limit(1)
            )
            if existing.first() is None:
                session.add(GroupPermBinding(qq_group_id=gid, permission_group_id=pg.id))
                await session.commit()
                perm_cache.delete("ban_word_log_targets")
                await manage_cmd.finish(f"群 {gid} 已添加为告警日志接收群")
            else:
                await manage_cmd.finish(f"群 {gid} 已是告警日志接收群")

        elif sub == "移除":
            gid_str = parts[1] if len(parts) > 1 else ""
            if not gid_str.isdigit():
                await manage_cmd.finish("用法: 群管理 告警日志目标 移除 <群号>")
                return
            gid = int(gid_str)
            result = await session.execute(
                select(GroupPermBinding).where(
                    GroupPermBinding.qq_group_id == gid,
                    GroupPermBinding.permission_group_id == pg.id,
                )
            )
            bindings = result.scalars().all()
            for b in bindings:
                await session.delete(b)
            await session.commit()
            perm_cache.delete("ban_word_log_targets")
            await manage_cmd.finish(f"群 {gid} 已从告警日志接收群中移除")

        elif sub == "列表":
            targets = await get_ban_word_log_targets()
            if targets:
                await manage_cmd.finish(
                    f"告警日志接收群（共 {len(targets)} 个）：\n"
                    + "\n".join(f"  群 {t}" for t in targets)
                )
            else:
                await manage_cmd.finish("当前没有告警日志接收群")

        else:
            await manage_cmd.finish(
                "告警日志目标 用法：\n"
                "  群管理 告警日志目标 添加 <群号>\n"
                "  群管理 告警日志目标 移除 <群号>\n"
                "  群管理 告警日志目标 列表"
            )
