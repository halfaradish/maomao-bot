from typing import Union
from datetime import datetime

from nonebot import(
    get_plugin_config,
    logger,
    on_command
)
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import(
    Bot,
    PrivateMessageEvent,
    GroupMessageEvent,
    MessageEvent,
    Message,
)
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from .config import Config
from ...common import JsonUtils
from nonebot.exception import FinishedException

__plugin_meta__ = PluginMetadata(
    name="prd",
    description="记录需求，拟定一份需求文档",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

prd = on_command(
    "prd",
    block=config.block,
    priority=config.priority
)

def update_to_do(to_do: list[dict]):
    JsonUtils.update(config.data_filename, {
        "to_do": to_do
    })

def handle_list(to_do: list[dict] = None, operation_params: list[str] = []) -> str:
    """展示目前未完成的需求"""
    # 检查需求列表是否为空
    if not to_do:
        return "目前无需求"
    # 检查是否需要列出全部需求
    list_all = False
    if operation_params and operation_params[0] in ["all", "a"]:
        list_all = True
    # 初始化返回消息
    res_msg = ""
    for i, requirement in enumerate(to_do):
        # 修复逻辑：如果不要求显示全部且需求已完成，则跳过
        if not list_all and requirement["finish"]:
            continue
        res_msg += f"\n编号 {i} :\n" + f"是否完成: {requirement['finish']}\n" + f"需求: {requirement['content']}" + f"\n创建于 {requirement['create_at']} by {requirement['creator']}\n"
        if requirement["last_modifyor"]:
            res_msg += f"最后修改于 {requirement['last_modify_at']} by {requirement['last_modifyor']}\n"
    return res_msg.strip('\n\r') if res_msg else "目前所有需求都已完成"

def handle_add(to_do: list[dict] = None, operation_params: list[str] = [], creator: str = None) -> str:
    """增加需求"""
    # 检查是否有足够的参数
    if operation_params:
        content = operation_params[0]
    else:
        return "请输入要添加的内容"
    # 添加需求到列表
    add_info: dict = {
        "finish": False,
        "content": content,
        "creator": creator,
        "create_at": datetime.now().strftime("%Y-%m-%d"),
        "last_modifyor": "",
        "last_modify_at": ""
    }
    to_do.append(add_info)
    update_to_do(to_do=to_do)
    to_do_list_msg = handle_list(to_do=to_do)
    return f"需求已添加，对应编号为 {len(to_do) - 1}\n" + to_do_list_msg

def handle_remove(to_do: list[dict] = None, operation_params: list[str] = []):
    """删除需求"""
    if operation_params and operation_params[0].isdigit():
        index = int(operation_params[0])
    else:
        return "请输入要删除的需求的下标"
    if index >= len(to_do) or index < 0:
        return "输入的下标超出范围"
    del to_do[index]
    update_to_do(to_do=to_do)
    to_do_list_msg = handle_list(to_do=to_do)
    return f"对应编号 {index} 的需求已删除\n" + to_do_list_msg

def handle_modify(to_do:list[dict] = None, operation_params: list[str] = [], last_modifyor: str = None):
    """更改需求"""
    # 检查参数
    if len(operation_params) >= 2 and operation_params[0].isdigit():
        index = int(operation_params[0])
        content = operation_params[1]
    else:
        return "请输入正确的下标和修改的内容"
    if index >= len(to_do) or index < 0:
        return "输入的下标超出范围"
    to_do[index].update({
        "content": content,
        "last_modifyor": last_modifyor,
        "last_modify_at": datetime.now().strftime("%Y-%m-%d")
    })
    update_to_do(to_do=to_do)
    to_do_list_msg = handle_list(to_do=to_do)
    return f"对应编号 {index} 的需求已修改\n" + to_do_list_msg
    
def handle_complete(to_do: list[dict] = None, operation_params: list[str] = []):
    """更改对应下标的需求的状态"""
    if operation_params and operation_params[0].isdigit():
        index = int(operation_params[0])
    else:
        return "请输入正确的下标"
    if index >= len(to_do) or index < 0:
        return "输入的下标超出范围"
    to_do[index].update({
        "finish": not to_do[index]["finish"]
    })
    update_to_do(to_do=to_do)
    to_do_list_msg = handle_list(to_do=to_do)
    return f"已修改应编号 {index} 的需求的状态\n" + to_do_list_msg


@prd.handle()
async def _(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], args: Message = CommandArg()):
    raw_args = args.extract_plain_text()
    params = raw_args.split() if raw_args else []

    # 当没有传入参数时
    if not params:
        await prd.finish(config.default_msg)
    try:
        data, _ =JsonUtils.read(config.data_filename, {
            "to_do": []
        })
        to_do = data["to_do"]
        logger.info(f"to_do is: {to_do}")

        operation = params[0]
        operation_params = params[1:]
        logger.info(f"operation is: {operation}")
        logger.info(f"operation_params is: {operation_params}")

        res_msg = None
        if operation in ["list", "ls"]:
            res_msg = handle_list(to_do=to_do, operation_params=operation_params)
        elif operation in ["add"]:
            res_msg = handle_add(to_do=to_do, operation_params=operation_params, creator=event.sender.nickname)
        elif operation in ["rm", "remove"]:
            res_msg = handle_remove(to_do=to_do, operation_params=operation_params)
        elif operation in ["modify", "md"]:
            res_msg = handle_modify(to_do=to_do, operation_params=operation_params, last_modifyor=event.sender.nickname)
        elif operation in ["x", "complete"]:
            res_msg = handle_complete(to_do=to_do, operation_params=operation_params)
        else:
            return
        
        logger.info(f"res_msg is: {res_msg}")
        await prd.finish(res_msg)
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        logger.error(f"prd插件出错: {e}")
