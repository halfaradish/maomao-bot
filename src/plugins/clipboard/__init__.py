from nonebot import (
    get_plugin_config,
    on_command,
    logger
)
from nonebot.plugin import PluginMetadata
from nonebot.matcher import Matcher
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
from ..cmd_list.model import PluginGroupEnum

__plugin_meta__ = PluginMetadata(
    name="剪切板",
    description="将文本转换为图片，支持普通文本和Markdown格式",
    usage="/cv —— 回复消息使用普通文本剪切板\n/cvmd —— 回复消息使用Markdown剪切板",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": "green"
    }
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
    cmd=config.clip_cmd,
    aliases={"剪切板"},
    rule=exact_command(["cmd", "剪切板"]),
    priority=config.clip_priority
)

clipboard_md = on_command(
    cmd="cvmd",
    aliases={"markdown剪切板"},
    rule=exact_command(["cvmd", "markdown剪切板"]),
    priority=config.clip_priority
)

async def text_to_image_bytes(text_msg: str, api_url: str) -> Tuple[bool, Union[str, BinaryIO]]:
    # 请求api生成图片
    logger.info(f"正在请求API获取图片，URL: {api_url}, 超时: {config.clip_post_timeout}秒")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=api_url,
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
@clipboard_md.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], matcher: Matcher):
    try:
        event_type = "群聊" if isinstance(event, GroupMessageEvent) else "私聊"
        
        # 判断是哪个命令触发的
        cmd = event.get_plaintext().strip().lower()
        is_markdown = "cvmd" in cmd or "markdown" in cmd
        
        logger.info(f"收到{event_type}{'Markdown' if is_markdown else '普通'}剪切板命令请求，用户ID: {event.sender.user_id}")
        
        if not event.reply:
            logger.info("未检测到回复消息，返回默认提示")
            await matcher.finish(config.DEFAULT_MSG)

        # 将消息字符串转化为 Message 对象
        message: Message = Message(event.reply.message)
        
        text_content = ""
        
        # 检查是否包含文件 (仅 cvmd 支持)
        file_segments = [seg for seg in message if seg.type == "file"]
        is_file_msg = False
        if is_markdown and file_segments:
            is_file_msg = True
            file_seg = file_segments[0]
            file_url = file_seg.data.get("url")
            file_name = file_seg.data.get("file") or "unknown"
            
            if not file_url:
                await matcher.finish("无法获取文件下载链接，请确保文件未过期。")
            
            logger.info(f"检测到引用文件: {file_name}, URL: {file_url}")
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(file_url) as resp:
                        if resp.status != 200:
                            await matcher.finish(f"文件下载失败，状态码: {resp.status}")
                        
                        file_bytes = await resp.read()
                        try:
                            text_content = file_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            try:
                                text_content = file_bytes.decode("gbk")
                            except UnicodeDecodeError:
                                await matcher.finish("文件编码格式不支持，仅支持 UTF-8 或 GBK 编码的文本文件。")
            except Exception as e:
                logger.error(f"下载或读取文件失败: {e}")
                await matcher.finish(f"读取文件失败: {e}")
        else:
            text_content = message.extract_plain_text()

        if not text_content.strip():
            await matcher.finish("引用的消息不包含有效文本")

        # 获取图片
        target_url = config.clip_md_post_url if is_markdown else config.clip_post_url
        success, res = await text_to_image_bytes(text_content.replace("\\", "\\\\"), target_url)
        if not success:
            await matcher.finish(res)
        logger.debug("图片生成成功")

        # 发送图片
        if isinstance(event, GroupMessageEvent):
            logger.debug(f"正在发送图片 -> 群聊 {event.group_id}")
        else:
            logger.debug(f"正在发送图片 -> 私聊 {event.sender.user_id}")
        
        message = Message.template("图片文本来自 {}\n{}命令由 {} 触发\n{}").format(
            MessageSegment.at(user_id=event.reply.sender.user_id),
            "cvmd" if is_markdown else "cv",
            MessageSegment.at(user_id=event.sender.user_id),
            MessageSegment.image(res)
        )
        try:
            await matcher.send(message)
            logger.debug("图片发送成功")
        except Exception as e:
            # 图片发送失败，这是真正的错误
            logger.error(f"发送图片失败: {e}")
            await matcher.finish("发送图片失败")
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
                        # 如果是文件消息，则不撤回
                        if not is_file_msg:
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

        return
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        # 只有在图片发送之前的错误才应该显示为"发送图片失败"
        logger.error(f"处理剪切板请求时出错: {e}")
        await clipboard.finish("处理失败")
