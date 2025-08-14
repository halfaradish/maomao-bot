from pathlib import Path
import datetime
from nonebot import get_plugin_config, on_regex, logger, Bot, on_command
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, Message, MessageSegment
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

sexy_command = on_command(
    '来点涩图',
    aliases={"来张涩图", "来点色图", "来张色图"},
    priority=config.priority,
)

def is_in_cd(user_id: int, cd_time: int = 30):
    """检查用户是否在冷却时间内"""
    data, _ = JsonUtils.read(config.filename, {"cd": {}})
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
                
def create_image_segment(image_path: str) -> MessageSegment:
    # 获取绝对路径
    abs_path = Path(image_path).absolute().as_posix()

    start_pattern = "/app/data/images"
    start_index = str(abs_path).find(start_pattern)

    if start_index != -1:
        result_path = str(abs_path)[start_index:]
    
    uri = f"file://{result_path}"
    logger.info(f"the pic uri is: {uri}")
    return MessageSegment.image(uri)

async def send_group_msg(event: GroupMessageEvent, bot: Bot, img_path: str) -> None:
    img_msg = create_image_segment(image_path=img_path)

    try:
        await bot.send(event=event, message=img_msg)
    except Exception as e:
        await bot.send(event=event , message="图片发送超时，请稍后再试")
        logger.opt(exception=True).error(f"图片发送失败: {e}")

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
            
    lolicon = Lolicon()

    await bot.send(event=event, message=f"正在响应 {username} 的请求")
    img_save_path = await lolicon.get_img(tags=tags, event=event, bot=bot)

    if img_save_path is None:
        await sexy_command.finish("涩图下载失败，请稍后再试")

    if is_source_img:
        await send_group_msg(event=event, bot=bot, img_path=img_save_path)
        return

    compress_pic = CompressPic()
    try:
        compress_path = await compress_pic.compress_one_image(img_save_path)
    except Exception as e:
        logger.error(f"压缩图片 {img_save_path} 失败: {e}")
        await sexy_command.finish("压缩涩图失败，请稍后再试。")

    if compress_path:
        await send_group_msg(event=event, bot=bot, img_path=compress_path)
        return
