import base64
from math import ceil

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import MessageSegment

from .config import Config
from .repository import ImageRepository
from .storage import ImageStorageService

_HELP = """图片收藏命令：
/图片 保存 + 同条消息附图 - 收藏图片
/图片 发送 <编号> - 发送指定图片
/图片 列表 [页码] - 查看最近收藏
/图片 搜索 <关键词> - 按编号、标签或备注搜索
/图片 标签 <编号> <标签1,标签2> - 设置标签
/图片 删除 <编号> - 删除指定图片
/图片 帮助 - 显示本帮助

仅管理员可使用；可在私聊或群聊中执行。"""


def is_admin(user_id: str) -> bool:
    return user_id in get_driver().config.superusers


async def execute_command(
    raw_argument: str, repository: ImageRepository, storage: ImageStorageService, config: Config
) -> str | MessageSegment:
    parts = raw_argument.strip().split(maxsplit=2)
    if not parts or parts[0] in {"帮助", "help"}:
        return _HELP

    action = parts[0]
    
    if action == "发送":
        if len(parts) < 2:
            return "用法：/图片 发送 <编号>"
        image = repository.get(parts[1])
        if image is None or not image.file_path.is_file():
            return "未找到该图片，或本地图片文件已丢失。"
        image_data = base64.b64encode(image.file_path.read_bytes()).decode("ascii")
        return MessageSegment.image(f"base64://{image_data}")

    if action == "列表":
        page = 1
        if len(parts) >= 2:
            try:
                page = int(parts[1])
                if page < 1:
                    raise ValueError
            except ValueError:
                return "页码必须是正整数。"
        images, total = repository.list_recent(page, config.image_collection_list_page_size)
        if not images:
            return "没有图片记录。" if total == 0 else "该页没有图片记录。"
        total_pages = ceil(total / config.image_collection_list_page_size)
        lines = [f"图片列表（第 {page}/{total_pages} 页，共 {total} 张）："]
        lines.extend(_format_image(image) for image in images)
        return "\n".join(lines)

    if action == "搜索":
        if len(parts) < 2:
            return "用法：/图片 搜索 <关键词>"
        images = repository.search(parts[1])
        if not images:
            return "没有找到匹配的图片。"
        return "\n".join([f"搜索结果（{len(images)} 张）：", *(_format_image(image) for image in images)])

    if action == "标签":
        if len(parts) < 3:
            return "用法：/图片 标签 <编号> <标签1,标签2>"
        tags = tuple(dict.fromkeys(tag.strip() for tag in parts[2].replace("，", ",").split(",") if tag.strip()))
        if not tags:
            return "请提供至少一个有效标签。"
        if not repository.update_tags(parts[1], tags):
            return "未找到该图片。"
        return f"已更新 {parts[1]} 的标签：{', '.join(tags)}"

    if action == "删除":
        if len(parts) < 2:
            return "用法：/图片 删除 <编号>"
        image = repository.get(parts[1])
        if image is None:
            return "未找到该图片。"
        storage.remove(image)
        return f"已删除图片：{image.id}"

    return f"未知操作：{action}\n\n{_HELP}"


def _format_image(image) -> str:
    return f"{image.id} | {image.created_at:%Y-%m-%d %H:%M} | 标签：{image.formatted_tags}"
