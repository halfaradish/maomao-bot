from nonebot import (
    get_plugin_config,
    on_command,
    logger
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageSegment,
    Bot,
    PrivateMessageEvent
)
from nonebot.exception import FinishedException
from nonebot.rule import Rule
from nonebot.params import CommandArg

import io
import aiohttp
from typing import Tuple, Union, BinaryIO, List

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="clipboard",
    description="",
    usage="",
    config=Config,
)

config: Config = get_plugin_config(Config)

def exact_command(cmds: List[str]):
    async def _rule(args: Message = CommandArg()):
        arg = args.extract_plain_text().strip()
        if arg:
            return False
        return True
    return Rule(_rule)


clipboard = on_command(
    cmd="cv",
    aliases={"剪切板"},
    rule=exact_command(["cmd", "剪切板"]),
    priority=config.clip_priority
)

async def text_to_image_bytes(text_msg: str) -> Tuple[bool, Union[str, BinaryIO]]:
    # 请求api生成图片
    logger.info(f"正在请求API获取图片，URL: {config.clip_post_url}, 超时: {config.clip_post_timeout}秒")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=config.clip_post_url,
                json={'content': text_msg},
                timeout=config.clip_post_timeout,
            ) as res:
                logger.debug("成功接收返回信息")

                if res.status == 200:
                    logger.success("成功接收剪切板生成图片")
                    content = await res.read()
                    img_bytes = io.BytesIO(content)
                    return (True, img_bytes)
                else:
                    # 尝试解析错误信息
                    try:
                        error_data = await res.json()
                        logger.error(f"图片生成失败：{error_data.get('error', '未知错误')}")
                        return (False, "图片生成失败")
                    except Exception:
                        logger.error(f"图片生成失败，HTTP状态码：{res.status}")
                        return (False, "图片生成失败")
    except aiohttp.ClientError as e:
        logger.error(f"网络请求异常：{type(e).__name__}: {e}")
        return (False, f"网络请求异常：{type(e).__name__}")

@clipboard.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    try:
        event_type = "群聊" if isinstance(event, GroupMessageEvent) else "私聊"
        logger.info(f"收到{event_type}cv命令请求，用户ID: {event.sender.user_id}")
        
        if not event.reply:
            logger.info("未检测到回复消息，返回默认提示")
            await clipboard.finish(config.DEFAULT_MSG)

        # 将消息字符串转化为 Message 对象
        message: Message = Message(event.reply.message)
        text_content = message.extract_plain_text()

        if not text_content.strip():
            await clipboard.finish("引用的消息不包含有效文本")

        # 获取图片
        success, res = await text_to_image_bytes(text_content.replace("\\", "\\\\"))
        if not success:
            await clipboard.finish(res)
        logger.debug("图片生成成功")

        # 发送图片
        if isinstance(event, GroupMessageEvent):
            logger.debug(f"正在发送图片 -> 群聊 {event.group_id}")
        else:
            logger.debug(f"正在发送图片 -> 私聊 {event.sender.user_id}")
        
        message = Message.template("图片文本来自 {}\ncv命令由 {} 触发\n{}").format(
            MessageSegment.at(user_id=event.reply.sender.user_id),
            MessageSegment.at(user_id=event.sender.user_id),
            MessageSegment.image(res)
        )
        try:
            await clipboard.send(message)
            logger.debug("图片发送成功")
        except Exception as e:
            # 图片发送失败，这是真正的错误
            logger.error(f"发送图片失败: {e}")
            await clipboard.finish("发送图片失败")
            return

        # 只在群聊中执行权限检查和消息删除操作
        # 这些操作的失败不应该影响主流程，静默处理或记录日志即可
        if isinstance(event, GroupMessageEvent):
            # 获取被回复消息发送者的群名片或群昵称信息（无论是否有权限都要获取）
            source_user_id = event.reply.sender.user_id
            source_user_name = None
            try:
                source_member_info = await bot.get_group_member_info(
                    group_id=event.group_id,
                    user_id=source_user_id
                )
                # 优先使用群名片（card），如果没有则使用群昵称（nickname）
                source_user_card = source_member_info.get('card', '').strip()
                if source_user_card:
                    source_user_name = source_user_card
                else:
                    source_user_name = source_member_info.get('nickname', '').strip()
            except Exception as e:
                logger.warning(f"获取群成员信息失败: {e}，将不显示用户信息")

            # 尝试撤回消息（如果有权限的话），但失败不影响后续提示消息的发送
            try:
                # 检查bot是否有管理员权限
                bot_member_info = await bot.get_group_member_info(
                    group_id=event.group_id,
                    user_id=bot.self_id
                )
                bot_role = bot_member_info.get('role', 'member')
                if bot_role in ['owner', 'admin']:
                    # 如果bot有管理员权限，尝试删除原消息和当前命令消息
                    try:
                        await bot.delete_msg(message_id=event.reply.message_id)
                    except Exception as e:
                        logger.debug(f"撤回被回复消息失败: {e}")
                    
                    try:
                        await bot.delete_msg(message_id=event.message_id)
                    except Exception as e:
                        logger.debug(f"撤回命令消息失败: {e}")
                else:
                    logger.debug(f"bot 在群组 {event.group_id} 中没有管理权限，无法撤回消息")
            except Exception as e:
                logger.debug(f"检查权限或撤回消息时出错: {e}")
            
            # 无论如何都发送提示消息，优先显示群名片，如果没有则显示群昵称（QQ名）
            try:
                if source_user_name:
                    await clipboard.send(f"图片剪贴板的消息由 {source_user_name} 提供")
                else:
                    await clipboard.send("图片剪贴板的消息已添加")
            except Exception as e:
                logger.warning(f"发送提示消息失败: {e}")

        return
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        # 只有在图片发送之前的错误才应该显示为"发送图片失败"
        logger.error(f"处理剪切板请求时出错: {e}")
        await clipboard.finish("处理失败")
