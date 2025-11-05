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

import io
import aiohttp
from typing import Tuple, Union, BinaryIO

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="clipboard",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

clipboard = on_command(
    cmd="cv",
    aliases={"剪切板"},
    priority=config.priority
)

async def text_to_image_bytes(text_msg: str) -> Tuple[bool, Union[str, BinaryIO]]:
    # 请求api生成图片
    logger.info("正在请求api获取图片")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=config.post_url,
                json={'content': text_msg},
                timeout=config.post_timeout,
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
                        return (False, f"图片生成失败")
                    except:
                        logger.error(f"图片生成失败，HTTP状态码：{res.status}")
                        return (False, f"图片生成失败")
    except aiohttp.ClientError as e:
        logger.error(f"网络请求异常：{e}")
        return (False, f"网络请求异常")

@clipboard.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    try:
        if not event.reply:
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
        logger.debug(f"图片生成成功")

        img_msg = MessageSegment.image(res)
        # 发送图片
        if isinstance(event, GroupMessageEvent):
            logger.debug(f"正在发送图片 -> 群聊 {event.group_id}")
        else:
            logger.debug(f"正在发送图片 -> 私聊 {event.sender.user_id}")
        
        try:
            await clipboard.send(img_msg)
            logger.debug(f"图片发送成功")
        except Exception as e:
            # 图片发送失败，这是真正的错误
            logger.error(f"发送图片失败: {e}")
            await clipboard.finish("发送图片失败")
            return

        # 只在群聊中执行权限检查和消息删除操作
        # 这些操作的失败不应该影响主流程，静默处理或记录日志即可
        if isinstance(event, GroupMessageEvent):
            try:
                # 检查bot是否有管理员权限
                member_info = await bot.get_group_member_info(
                    group_id=event.group_id,
                    user_id=bot.self_id
                )
                bot_role = member_info.get('role', 'member')
                if bot_role not in ['owner', 'admin']:
                    logger.debug(f"bot 在群组 {event.group_id} 中没有管理权限，无法撤回消息")
                    return

                # 如果bot有管理员权限，删除原消息
                await bot.delete_msg(message_id=event.reply.message_id)
                # 发送提示消息并at发送消息的人
                at_source_msg_user = MessageSegment.at(user_id=event.reply.sender.user_id)
                await clipboard.send("图片剪贴板的消息由 " + at_source_msg_user + f"({event.reply.sender.user_id}) 提供")
            except Exception as e:
                # 后续操作失败不影响主流程，只记录日志
                logger.warning(f"群聊后续操作失败（图片已发送成功）: {e}")

        return
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        # 只有在图片发送之前的错误才应该显示为"发送图片失败"
        logger.error(f"处理剪切板请求时出错: {e}")
        await clipboard.finish("处理失败")
