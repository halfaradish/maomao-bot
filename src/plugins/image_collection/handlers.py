from nonebot.adapters.onebot.v11 import Message
from nonebot.log import logger

from .config import Config
from .storage import ImageStorageService


async def save_images_from_message(
    message: Message, config: Config, storage: ImageStorageService, sender_qq: int
) -> str:
    """Save image segments attached to a validated save command."""
    results: list[str] = []
    for segment in message:
        if segment.type != "image":
            continue
        url = segment.data.get("url")
        if not url:
            results.append("收到图片，但 NapCat 未提供可下载的图片地址。")
            continue
        try:
            image, created = await storage.save_from_url(
                url=url,
                sender_qq=sender_qq,
                original_name=segment.data.get("file"),
            )
            if created:
                results.append(f"已保存图片：{image.id}")
            else:
                results.append(f"图片已收藏过，编号：{image.id}")
        except (OSError, ValueError) as error:
            logger.warning("Unable to save QQ image: %s", error)
            results.append(f"图片保存失败：{error}")
        except Exception:
            logger.exception("Unexpected error while saving QQ image")
            results.append("图片保存失败：发生未知错误，请查看 NoneBot 日志。")
    return "\n".join(results) if results else "请在同一条消息中附上一张或多张图片。"
