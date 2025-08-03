import requests
import json
import os
import datetime
from urllib.parse import urlparse
from nonebot import get_plugin_config, on_regex, logger, Bot
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, Message
from nonebot.params import CommandArg

from .config import Config
from ...common import CompressPic, JsonUtils
from .lolicon import Lolicon

__plugin_meta__ = PluginMetadata(
    name="spicy_pics",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

sexy_command = on_regex(
    r"^(来点(涩|色)(涩|色)|涩图|色图)$",
    priority=config.priority,
    block=config.block,
)

def is_in_cd(user_id: int, cd_time: int = 30):
    """检查用户是否在冷却时间内"""
    data, _ = JsonUtils.read(config.filename, {})
    old_cd_str = data.get("cd", {}).get(str(user_id), "1970-01-01 00:00:00")
    old_cd = datetime.datetime.strptime(old_cd_str, "%Y-%m-%d %H:%M:%S")
    sec = (datetime.datetime.now() - old_cd).total_seconds()
    if sec <= cd_time:
        # 在冷却时间内
        logger.info(f"用户 {user_id} 在冷却时间内，剩余时间: {cd_time - sec:.2f}秒")
        return True
    else:
        # 更新冷却时间
        data["cd"][str(user_id)] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        JsonUtils.write(config.filename, data)
        return False
                
@sexy_command.handle()
async def handle_sexy_command(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """发涩图了"""
    # 检查是否处于冷却时间
    user_id = event.sender.user_id
    username = event.sender.nickname
    if is_in_cd(user_id):
        await sexy_command.finish(f"{username}, 现在处于30s的贤者时间哦")

    # 接收参数
    raw_args = args.extract_plain_text().strip()
    params: list[str] = raw_args.split() if raw_args else []

    # 是否发送原图
    is_source_img: bool = False
    # 图片要搜索的标签
    tags: list[str] = []

    # 检查参数
    if params:
        for param in params:
            if param == "原图":
                is_source_img = True
                continue
            tags.append(param)

    await bot.send(event=event, message=f"正在处理 {username} 的响应")
    img_save_path = Lolicon.get_img(tags=tags)

    if is_source_img:
        await sexy_command.finish(f"[CQ:image,file={img_save_path}]")

    compress_pic = CompressPic()
    try:
        comperss_path = await compress_pic.compress_one_image(img_save_path)
    except Exception as e:
        logger.error(f"压缩图片 {img_save_path} 失败: {e}")
        await sexy_command.finish("压缩涩图失败，请稍后再试。")

    # 发送图片
    await sexy_command.finish(f"[CQ:image,file={comperss_path}]")
