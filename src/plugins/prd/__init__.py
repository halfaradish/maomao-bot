from typing import Union
import os

from nonebot import (
    get_driver,
    get_plugin_config,
    logger,
    on_command
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    Bot,
    PrivateMessageEvent,
    GroupMessageEvent,
    MessageEvent,
    Message,
    MessageSegment,
)
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from .config import Config
from .html_gen import SimpleHTMLImageGenerator
from . import dao
from nonebot.exception import FinishedException
from src.common.plugin_meta import PluginGroupEnum, PluginBadgeColor
from src.common.permission import check_permission

from . import permissions  # noqa: F401
from src.common.send_forward_msg import send_forward_msg as send_forward_msg_api

__plugin_meta__ = PluginMetadata(
    name="需求管理",
    description="记录需求，拟定需求文档，支持需求的添加、删除、修改、完成、分组管理，以及生成需求图片",
    usage="prd list —— 查看未完成的需求\nprd ok —— 查看已完成的需求\nprd add <内容> —— 添加新需求\nprd rm <编号> —— 删除指定需求\nprd modify <编号> <内容> —— 修改指定需求\nprd complete <编号> —— 标记需求为完成/未完成\nprd group <编号> <组别> —— 为需求分组\nprd <执行人> xxx <编号> —— 为需求分配执行人\nprd img <编号> —— 生成指定需求的图片\nprd img all —— 生成未完成需求的图片\nprd img ok —— 生成已完成需求的图片",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.UTILITY.value,
        "badge_color": PluginBadgeColor.GREEN.value
    }
)

config = get_plugin_config(Config)

# 创建全局图片生成器实例（用于缓存管理）
image_generator = SimpleHTMLImageGenerator(
    config.image_output_dir,
    config.custom_image_path,
    config.enable_cache,
    config.cache_dir,
    config.cache_expire_days
)

prd = on_command(
    "prd",
    block=config.block,
    priority=config.priority
)


@get_driver().on_startup
async def _create_tables():
    """建表（幂等，仅创建缺失表）"""
    from src.common.database import ensure_tables
    from src.common.models.prd_models import PrdTodo

    await ensure_tables(PrdTodo)


async def send_image_forward_msg(bot: Bot, event: MessageEvent, image_paths: list[str], title: str = "图片列表"):
    """发送图片合并转发消息（节点构造与发送委托 common；缓存路径映射为 prd 业务逻辑）"""

    contents: list[Message] = [Message(title)]  # 标题节点

    for i, image_path in enumerate(image_paths):
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                continue

            # 判断是否为缓存图片，构建发送到QQ的路径
            filename = os.path.basename(image_path)

            # 检测是否为缓存图片（检测完整路径中的cache目录）
            if "/cache/" in image_path or "\\cache\\" in image_path:
                # 缓存图片需要根据子目录构建发送到QQ的路径
                if "/cache/single/" in image_path or "\\cache\\single\\" in image_path:
                    # 单个需求缓存图片 - 发送到QQ的相对路径
                    qq_path = f"file:///app/data/prd_images/cache/single/{filename}"
                    logger.info(f"发送单个需求缓存图片: {filename} (本地路径: {image_path})")
                elif "/cache/batch/" in image_path or "\\cache\\batch\\" in image_path:
                    # 批量需求缓存图片 - 发送到QQ的相对路径
                    qq_path = f"file:///app/data/prd_images/cache/batch/{filename}"
                    logger.info(f"发送批量需求缓存图片: {filename} (本地路径: {image_path})")
                else:
                    # 其他缓存图片（兜底处理）
                    qq_path = f"file:///app/data/prd_images/cache/{filename}"
                    logger.info(f"发送其他缓存图片: {filename} (本地路径: {image_path})")
            else:
                # 普通图片使用原路径
                qq_path = f"file:///app/data/prd_images/{filename}"
                logger.info(f"发送普通图片: {filename} (本地路径: {image_path})")

            # 图文混排节点：页码文本 + 图片
            contents.append(Message(f"第{i + 1}页:") + MessageSegment.image(qq_path))

        except Exception as e:
            logger.error(f"处理图片 {image_path} 时出错: {e}")
            continue

    if len(contents) <= 1:  # 只有标题，没有图片
        await prd.send("没有可发送的图片")
        return

    # 发送合并转发消息（目标与节点身份由 common 处理）
    await send_forward_msg_api.by_onebot_api(bot, event, contents)


def build_single_msg(requirement: dict):
    """构建单个需求的语句"""
    res: str = f"\n编号: {requirement['id']}\n是否完成: {requirement['finish']}\n分类：{requirement.get('group', '其他')}\n需求: {requirement['content']}\n创建于 {requirement['create_at']} by {requirement['create_by']}\n"
    if requirement.get('assign_to'):
        res += f"执行人: {requirement['assign_to']} (分配于 {requirement.get('assign_at', '')} by {requirement.get('assign_by', '')})\n"
    if requirement['last_modify_by']:
        res += f"最后修改于 {requirement['last_modify_at']} by {requirement['last_modify_by']}\n"
    if requirement['finish_by'] and requirement['finish']:
        res += f"完成于 {requirement['finish_at']} by {requirement['finish_by']}\n"
    return res


def handle_list(to_do: list[dict] = None, exist_groups: list = []) -> tuple[list, list]:
    """展示目前未完成的需求"""
    # 检查需求列表是否为空
    if not to_do:
        return (["目前无需求"], ["目前无已完成的需求"])

    # 使用存在的组别初始化字典
    finish_msg_dict: dict = {element: "" for element in exist_groups}
    unfinish_msg_dict: dict = {element: "" for element in exist_groups}
    # 保证默认的'其他'组别存在
    finish_msg_dict['其他'] = ''
    unfinish_msg_dict['其他'] = ''

    # 分类
    for requirement in to_do:
        group_name = requirement.get('group', '其他')
        if requirement['finish']:
            finish_msg_dict[group_name if group_name in exist_groups else '其他'] += build_single_msg(
                requirement=requirement)
        else:
            unfinish_msg_dict[group_name if group_name in exist_groups else '其他'] += build_single_msg(
                requirement=requirement)
    # 需要返回的内容
    finish_msg_list = [f"{key}:\n{val if val else '无'}" for key, val in finish_msg_dict.items()]
    unfinish_msg_list = [f"{key}:\n{val if val else '无'}" for key, val in unfinish_msg_dict.items()]
    # 添加初始化内容
    finish_msg_list.insert(0, "已完成的需求如下")
    unfinish_msg_list.insert(0, "未完成的需求如下")

    return (finish_msg_list, unfinish_msg_list)


async def handle_add(operation_params: list[str] = [], create_by: str = None) -> str:
    """增加需求"""
    # 检查是否有足够的参数
    if operation_params:
        content = operation_params[0]
    else:
        return "请输入要添加的内容"
    # 新增需求（编号由数据库自增分配）
    add_info = await dao.add_todo(content=content, create_by=create_by)
    return f"需求已添加，对应编号为 {add_info['id']}" + build_single_msg(requirement=add_info)


async def handle_remove(operation_params: list[str] = []):
    """删除需求"""
    if operation_params and operation_params[0].isdigit():
        index = int(operation_params[0])
    else:
        return "请输入要删除的需求的下标"
    removed = await dao.remove_todo(index)
    if removed is None:
        return f"未找到所指定的编号 {index}"
    # 清除相关缓存
    image_generator._invalidate_cache(index)
    return f"对应编号 {index} 的需求已删除" + build_single_msg(requirement=removed)


async def handle_modify(operation_params: list[str] = [], last_modify_by: str = None):
    """更改需求"""
    # 检查参数
    if len(operation_params) >= 2 and operation_params[0].isdigit():
        index = int(operation_params[0])
        content = operation_params[1]
    else:
        return "请输入正确的下标和修改的内容"
    requirement = await dao.update_content(index, content, last_modify_by)
    if requirement is None:
        return f"未找到所指定的编号 {index}"
    # 清除相关缓存
    image_generator._invalidate_cache(index)
    return f"对应编号 {index} 的需求已修改" + build_single_msg(requirement=requirement)


async def handle_complete(operation_params: list[str] = [], finish_by: str = "未指定"):
    """更改对应下标的需求的状态"""
    if operation_params and operation_params[0].isdigit():
        index = int(operation_params[0])
    else:
        return "请输入正确的下标"
    requirement = await dao.toggle_finish(index, finish_by)
    if requirement is None:
        return f"未找到所指定的编号 {index}"
    # 清除相关缓存
    image_generator._invalidate_cache(index)
    return f"已修改对应编号 {index} 的需求的状态" + build_single_msg(requirement=requirement)


async def handle_grouped(operation_params: list[str] = [], exist_groups: list[str] = []):
    """将对应下标的需求分组"""
    # 展示默认消息
    if not operation_params:
        return f"现有可分类组别：{exist_groups}"
    # 检查参数个数
    if len(operation_params) != 2:
        return f"参数数量错误，参数必须由一个数字和一个存在的组别构成：{operation_params}"
    # 查找下标和组别
    index: int = None
    group_name: str = None
    for opt_param in operation_params:
        if opt_param.isdigit():
            index = int(opt_param)
        else:
            group_name = opt_param
    # 二次检查
    if not index and not group_name:
        return f"参数错误！参数必须由一个数字和一个存在的组别构成：{operation_params}"
    if group_name not in exist_groups:
        return f"修改失败，{group_name} 不在默认组别中：{exist_groups}"
    # 更改分类（编号不存在时与原实现一致：不回复）
    requirement = await dao.set_group(index, group_name)
    if requirement is None:
        return None
    return f"对应下标 {index} 的组别已更改 {group_name}\n" + build_single_msg(requirement=requirement)


async def handle_assign(operation_params: list[str] = [], assign_by: str = None):
    """给需求分配执行人"""
    if len(operation_params) < 2:
        return "参数格式错误，请使用：/prd 执行人名字 xxx 编号"

    # 检查参数格式：["执行人名字", "xxx", "编号"]
    if operation_params[1] != "xxx":
        return "参数格式错误，请使用：/prd 执行人名字 xxx 编号"

    if not operation_params[2].isdigit():
        return "请输入正确的编号"

    assign_to_name = operation_params[0]  # 自定义执行人名字
    index = int(operation_params[2])  # 需求编号

    requirement = await dao.assign(index, assign_to_name, assign_by)
    if requirement is None:
        return f"未找到所指定的编号 {index}"
    # 清除相关缓存
    image_generator._invalidate_cache(index)
    return f"已为编号 {index} 的需求分配执行人: {assign_to_name}\n" + build_single_msg(requirement=requirement)


async def handle_image_generation(bot: Bot, event: MessageEvent, to_do: list[dict] = None,
                                  operation_params: list[str] = []):
    """处理图片生成命令"""
    if not config.enable_image_output:
        await prd.send("图片输出功能已禁用")
        return

    if not operation_params:
        await prd.send("请指定要生成图片的需求编号，或使用 'all' 生成未完成需求，或使用 'ok' 生成已完成需求")
        return

    param = operation_params[0]

    # 使用全局图片生成器实例
    generator = image_generator

    try:
        if param.lower() == "all":
            # 生成未完成需求的图片
            if not to_do:
                await prd.send("当前没有任何需求")
                return

            # 过滤出未完成的需求
            unfinished_requirements = [req for req in to_do if not req.get('finish', False)]

            if not unfinished_requirements:
                await prd.send("当前没有未完成的需求")
                return

            await prd.send("正在生成未完成需求图片，请稍候...")

            # 检查是否启用分页功能
            if config.enable_pagination and len(unfinished_requirements) > config.max_requirements_per_page:
                # 使用分页功能生成多张图片
                result_paths = await generator.generate_requirements_list_paginated(
                    unfinished_requirements,
                    "未完成需求列表",
                    config.max_image_height,
                    config.max_requirements_per_page
                )

                if result_paths:
                    await prd.send(f"未完成需求图片生成成功！共{len(result_paths)}张图片")
                    # 使用合并转发消息发送所有图片
                    await send_image_forward_msg(bot, event, result_paths, f"未完成需求列表 - 共{len(result_paths)}页")
                else:
                    await prd.send("图片生成失败")
            else:
                # 使用原来的单张图片生成
                result_path = await generator.generate_requirements_list(unfinished_requirements, "未完成需求列表")
                if result_path:
                    await prd.send("未完成需求图片生成成功！")
                    # 使用合并转发消息发送单张图片
                    await send_image_forward_msg(bot, event, [result_path], "未完成需求列表")
                else:
                    await prd.send("图片生成失败")

        elif param.lower() == "ok":
            # 生成已完成需求的图片
            if not to_do:
                await prd.send("当前没有任何需求")
                return

            # 过滤出已完成的需求
            finished_requirements = [req for req in to_do if req.get('finish', False)]

            if not finished_requirements:
                await prd.send("当前没有已完成的需求")
                return

            await prd.send("正在生成已完成需求图片，请稍候...")

            # 检查是否启用分页功能
            if config.enable_pagination and len(finished_requirements) > config.max_requirements_per_page:
                # 使用分页功能生成多张图片
                result_paths = await generator.generate_requirements_list_paginated(
                    finished_requirements,
                    "已完成需求列表",
                    config.max_image_height,
                    config.max_requirements_per_page
                )

                if result_paths:
                    await prd.send(f"已完成需求图片生成成功！共{len(result_paths)}张图片")
                    # 使用合并转发消息发送所有图片
                    await send_image_forward_msg(bot, event, result_paths, f"已完成需求列表 - 共{len(result_paths)}页")
                else:
                    await prd.send("图片生成失败")
            else:
                # 使用原来的单张图片生成
                result_path = await generator.generate_requirements_list(finished_requirements, "已完成需求列表")
                if result_path:
                    await prd.send("已完成需求图片生成成功！")
                    # 使用合并转发消息发送单张图片
                    await send_image_forward_msg(bot, event, [result_path], "已完成需求列表")
                else:
                    await prd.send("图片生成失败")

        elif param.isdigit():
            # 生成指定编号的需求图片
            index = int(param)
            requirement = None

            for req in to_do:
                if req["id"] == index:
                    requirement = req
                    break

            if not requirement:
                await prd.send(f"未找到编号为 {index} 的需求")
                return

            await prd.send(f"正在生成需求 #{index} 的图片，请稍候...")
            result_path = await generator.generate_requirement_card(requirement)
            if result_path:
                await prd.send(f"需求 #{index} 图片生成成功！")
                await send_image_message(bot, event, result_path)
            else:
                await prd.send("图片生成失败")

        else:
            await prd.send("参数错误，请使用：/prd img 编号 或 /prd img all 或 /prd img ok")

    except Exception as e:
        logger.error(f"图片生成过程中出错: {e}")
        await prd.send("图片生成过程中出现错误")


async def send_image_message(bot: Bot, event: MessageEvent, image_path: str):
    """发送图片消息"""
    try:
        # 检查文件是否存在
        if not os.path.exists(image_path):
            await prd.send("图片文件不存在")
            return

        # 判断是否为缓存图片，构建发送到QQ的路径
        filename = os.path.basename(image_path)

        # 检测是否为缓存图片（检测完整路径中的cache目录）
        if "/cache/" in image_path or "\\cache\\" in image_path:
            # 缓存图片需要根据子目录构建发送到QQ的路径
            if "/cache/single/" in image_path or "\\cache\\single\\" in image_path:
                # 单个需求缓存图片 - 发送到QQ的相对路径
                qq_path = f"file:///app/data/prd_images/cache/single/{filename}"
                img_msg = MessageSegment.image(qq_path)
                logger.info(f"发送单个需求缓存图片: {filename} (本地路径: {image_path})")
            elif "/cache/batch/" in image_path or "\\cache\\batch\\" in image_path:
                # 批量需求缓存图片 - 发送到QQ的相对路径
                qq_path = f"file:///app/data/prd_images/cache/batch/{filename}"
                img_msg = MessageSegment.image(qq_path)
                logger.info(f"发送批量需求缓存图片: {filename} (本地路径: {image_path})")
            else:
                # 其他缓存图片（兜底处理）
                qq_path = f"file:///app/data/prd_images/cache/{filename}"
                img_msg = MessageSegment.image(qq_path)
                logger.info(f"发送其他缓存图片: {filename} (本地路径: {image_path})")
        else:
            # 普通图片使用原路径
            qq_path = f"file:///app/data/prd_images/{filename}"
            img_msg = MessageSegment.image(qq_path)
            logger.info(f"发送普通图片: {filename} (本地路径: {image_path})")

        # 发送图片
        await prd.send(img_msg)
        logger.info(f"图片发送成功: {image_path}")

    except Exception as e:
        logger.error(f"发送图片失败: {e}")
        await prd.send("图片发送失败")


@prd.handle()
async def _(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], args: Message = CommandArg()):
    raw_args = args.extract_plain_text()
    params = raw_args.split() if raw_args else []

    # 当没有传入参数时
    if not params:
        await prd.finish(config.default_msg)

    if not await check_permission(event, "prd:use"):
        await prd.finish("你没有权限使用这个插件")

    try:
        to_do = await dao.list_todos()
        exist_groups = config.prd_exist_groups
        logger.debug(f"to_do is: {to_do}")

        operation = params[0]
        operation_params = params[1:]
        logger.debug(f"operation is: {operation}")
        logger.debug(f"operation_params is: {operation_params}")

        res_msg = None

        # 检查是否是新的分配执行人命令格式：执行人名字 xxx 编号
        if len(params) >= 3 and params[1] == "xxx":
            res_msg = await handle_assign(operation_params=params, assign_by=event.sender.nickname)
        elif operation in ["list", "ls"]:
            # 只显示未完成的需求
            finish_msg_list, unfinish_msg_list = handle_list(to_do=to_do, exist_groups=exist_groups)
            await send_forward_msg_api(bot, event, unfinish_msg_list)
            return
        elif operation in ["ok"]:
            # 只显示已完成的需求
            finish_msg_list, unfinish_msg_list = handle_list(to_do=to_do, exist_groups=exist_groups)
            await send_forward_msg_api(bot, event, finish_msg_list)
            return
        elif operation in ["add"]:
            res_msg = await handle_add(operation_params=operation_params, create_by=event.sender.nickname)
        elif operation in ["rm", "remove"]:
            res_msg = await handle_remove(operation_params=operation_params)
        elif operation in ["modify", "md"]:
            res_msg = await handle_modify(operation_params=operation_params,
                                          last_modify_by=event.sender.nickname)
        elif operation in ["x", "complete"]:
            res_msg = await handle_complete(operation_params=operation_params, finish_by=event.sender.nickname)
        elif operation in ["group", "分组"]:
            res_msg = await handle_grouped(operation_params=operation_params, exist_groups=exist_groups)
        elif operation in ["img", "image", "图片"]:
            await handle_image_generation(bot, event, to_do=to_do, operation_params=operation_params)
            return
        else:
            return

        logger.debug(f"res_msg is: {res_msg}")
        if res_msg:
            await prd.send(res_msg)
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        logger.error(f"prd插件出错: {e}")
