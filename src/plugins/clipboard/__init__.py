from nonebot import (
    get_plugin_config,
    on_command,
    logger
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageSegment
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
async def _(event: GroupMessageEvent):
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
        logger.debug(f"正在发送图片 -> {event.group_id}")
        await clipboard.send(img_msg)
        logger.debug(f"图片发送成功")
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        clipboard.finish("获取图片失败")
        logger.error(f"发送图片失败: {e}")
