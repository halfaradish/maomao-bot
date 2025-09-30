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
    Bot
)
from nonebot.exception import FinishedException

import io
import aiohttp
import ssl
from time import time
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
    logger.info("正在请求api获取图片")
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=config.post_url,
                json={'content': text_msg},
                timeout=config.post_timeout,
                ssl=ssl_context
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
async def _(bot: Bot, event: GroupMessageEvent):
    try:
        plugin_start_time = time()
        if not event.reply:
            await clipboard.finish(config.DEFAULT_MSG)

        # 将消息字符串转化为 Message 对象
        message: Message = Message(event.reply.message)
        text_content = message.extract_plain_text()

        if not text_content.strip():
            await clipboard.finish("引用的消息不包含有效文本")

        await clipboard.send("正在调用接口生成图片")
        # 获取图片-开始计时
        picget_start_time = time()
        success, res = await text_to_image_bytes(text_content.replace("\\", "\\\\"))
        if not success:
            await clipboard.finish(res)
        # 获取图片-结束计时
        picget_end_time = time()
        logger.debug(f"图片生成成功: 用时：{picget_end_time - picget_start_time} 秒")
        await clipboard.send("图片生成成功")

        # 生成图片链接
        img_msg = MessageSegment.image(res)
        logger.debug(f"正在发送图片 -> {event.group_id}")
        await clipboard.send(img_msg)
        plugin_end_time = time()
        logger.debug(f"图片发送成功, 用时：{plugin_end_time - plugin_start_time} 秒")
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        clipboard.finish("获取图片失败")
        logger.error(f"发送图片失败: {e}")
