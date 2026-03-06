import io
import os
import platform
from PIL import Image, ImageDraw, ImageFont
from nonebot import get_plugin_config, Bot, on_command, logger
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.adapters import Message
from nonebot.params import CommandArg

from .config import Config

plugin_config = get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="cmd_list",
    description="",
    usage="",
    config=Config,
    supported_adapters={"~onebot.v11"}
)

config = get_plugin_config(Config)

cmd_list = on_command(
    "cmd",
    aliases={"命令", "help", "帮助"},
    priority=plugin_config.priority,
    block=plugin_config.block
)


def _get_font(size):
    font_paths = []
    system = platform.system().lower()
    if system == "windows":
        font_paths = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]
    elif system == "linux":
        font_paths = ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]
    for font_path in font_paths:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size, encoding='utf-8')
        except:
            continue
    return ImageFont.load_default()


def _draw_rounded_rect(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)


def _generate_cmd_list_image():
    all_commands = [
        {"category": " 基础命令", "commands": ["/cmd  /命令  /help  /帮助 --- 查看所有命令"]},
        {"category": " 实用功能",
         "commands": ["/考勤 --- 查看考勤情况", "/clipboard --- 剪贴板功能", "/cvmd --- Markdown剪贴板功能",
                      "/赞我 --- 给QQ资料卡点赞", "/伪造消息 · 伪消息 --- 生成假消息"]},
        {"category": " 竞赛相关", "commands": ["/contest --- 查看竞赛信息", "/duel --- CF推题",
                                               "/开始监控 · monitor · 取消监控 · stop · 监控 --- ICPC过题监控",
                                               "/赛时过题 · 过题情况 --- 查询赛时过题情况",
                                               "/过题^ · 过题 --- 记录过题", "/过题积分榜 · 积分榜 --- 查看过题排行榜",
                                               "/检查过题 · 过题统计 --- 实时过题查询"]},
        {"category": " 群管理",
         "commands": ["/ban · unban · kick --- 群成员管理", "/group --- 群管理功能", "/group_pull --- 群消息转发",
                      "/群统计 --- 群统计功能", "/一键退群 --- 批量退群"]},
        {"category": " 技术功能",
         "commands": ["/sum · summary --- LLM对话记录", "/prd --- PRD功能", "/搬史 · 搬屎 · 转发 --- 搬史功能",
                      "/来点涩图 · 来张涩图 · 来张色图 --- 发送涩图", "/测表格 --- 测试表格生成"]},
        {"category": " 系统管理", "commands": [
            "/rate · 限速启用 · 限速禁用 · 限速紧急停止 · 限速恢复 · 限速状态 · 限速全局 · 限速按群 --- 限速管理",
            "/todo --- 待办提醒", "/清除缓存 --- 清除群成员缓存"]}
    ]

    padding = 15
    category_spacing = 10
    item_spacing = 8
    content_width = 700
    total_width = content_width + padding * 2

    header_height = 60
    footer_height = 35
    category_header_height = 35
    item_height = 40

    items_per_row = 2
    item_gap = 10
    item_width = (content_width - item_gap) // 2

    total_rows = 0
    for cat in all_commands:
        cmd_count = len(cat["commands"])
        total_rows += (cmd_count + items_per_row - 1) // items_per_row

    total_categories = len(all_commands)

    content_height = (
            header_height +
            total_categories * category_header_height +
            total_rows * item_height +
            (total_categories - 1) * category_spacing +
            total_rows * item_spacing +
            footer_height
    )

    img = Image.new('RGB', (total_width, content_height + padding * 2), '#ffffff')
    draw = ImageDraw.Draw(img)

    for y in range(content_height + padding * 2):
        ratio = y / (content_height + padding * 2)
        r = int(255 + (240 - 255) * ratio)
        g = int(255 + (245 - 255) * ratio)
        b = int(255 + (250 - 255) * ratio)
        draw.line([(0, y), (total_width, y)], fill=(r, g, b))

    font_title = _get_font(26)
    font_subtitle = _get_font(14)
    font_category = _get_font(18)
    font_command = _get_font(12)
    font_desc = _get_font(10)

    title = "谛听bot命令帮助"
    draw.text((padding + 20, padding + 12), title, fill='#000000', font=font_title)

    subtitle = ""
    draw.text((padding + 20, padding + 40), subtitle, fill='#444444', font=font_subtitle)

    line_y = padding + header_height - 5
    draw.line([padding, line_y, total_width - padding, line_y], fill='#000000', width=3)

    current_y = padding + header_height + 8

    for category in all_commands:
        _draw_rounded_rect(draw, [padding, current_y, padding + content_width, current_y + category_header_height], 8,
                           '#e8e8e8')
        draw.text((padding + 15, current_y + 6), category["category"], fill='#000000', font=font_category)
        current_y += category_header_height + item_spacing

        commands = category["commands"]
        for i in range(0, len(commands), items_per_row):
            for j in range(items_per_row):
                if i + j >= len(commands):
                    continue
                cmd = commands[i + j]
                x = padding + j * (item_width + item_gap)
                _draw_rounded_rect(draw, [x, current_y, x + item_width, current_y + item_height], 12, '#ffffff')
                draw.rectangle([x + 2, current_y + 2, x + item_width - 2, current_y + item_height - 2],
                               outline='#000000', width=2)

                parts = cmd.split('---', 1)
                if len(parts) == 2:
                    commands_text = parts[0].strip()
                    desc = parts[1].strip()
                    draw.text((x + 12, current_y + 6), commands_text, fill='#0055cc', font=font_command)
                    draw.text((x + 12, current_y + 24), desc, fill='#222222', font=font_desc)
                else:
                    draw.text((x + 12, current_y + 12), cmd, fill='#000000', font=font_command)
            current_y += item_height + item_spacing

        current_y += category_spacing - item_spacing

    footer_text = ""
    draw.text((padding + 20, content_height + padding - 20), footer_text, fill='#444444', font=font_subtitle)

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG', optimize=True)
    img_bytes.seek(0)

    return img_bytes.getvalue()


@cmd_list.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    try:
        img_bytes = _generate_cmd_list_image()
        await bot.send(event=event, message=MessageSegment.image(img_bytes))
    except Exception as e:
        logger.opt(exception=True).warning("[cmd_list]响应失败")
        await bot.send(event=event, message=f"响应失败:\n{e}")
