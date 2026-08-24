from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.params import CommandArg

from .commands import execute_command, is_admin
from .config import plugin_config
from .handlers import save_images_from_message
from .repository import ImageRepository
from .storage import ImageStorageService

repository = ImageRepository(plugin_config.database_path)
storage = ImageStorageService(plugin_config, repository)


@get_driver().on_startup
async def initialize_image_collection() -> None:
    repository.initialize()
    plugin_config.images_dir.mkdir(parents=True, exist_ok=True)


image_command = on_command("图片", aliases={"图片库"}, priority=5, block=True)


@image_command.handle()
async def handle_image_command(event: MessageEvent, argument: Message = CommandArg()) -> None:
    if not is_admin(event.get_user_id()):
        await image_command.finish("无权限：此图片库仅允许管理员使用。")

    action = argument.extract_plain_text().strip()
    if action == "保存":
        result = await save_images_from_message(
            argument, plugin_config, storage, int(event.get_user_id())
        )
    else:
        result = await execute_command(action, repository, storage, plugin_config)
    await image_command.finish(result)
