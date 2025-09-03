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

def get_whitelist():
    """获取白名单"""
    data, _ = JsonUtils.read(config.data_filename, {
        "whitelist_person": [],
        "whitelist_groups": []
    })
    return data.get("whitelist_person"), data.get("whitelist_groups")

def update_to_do(to_do: list[dict]):
    JsonUtils.update(config.data_filename, {
        "to_do": to_do
    })

async def send_forward_msg(bot: Bot, event: MessageEvent, messges: list[str]):
    """发送合并转发消息"""
    def to_node(name: str, uin: str, message: Message):
        """构建统一的格式"""
        return {
            "type": "node",
            "data": {"name": name, "uin": uin, "content": message},
        }
    
    info = await bot.get_login_info()
    name = info['nickname']
    uin = bot.self_id
    
    # 构建消息节点
    message_nodes = [to_node(name=name, uin=uin, message=message) for message in messges]

    if isinstance(event, GroupMessageEvent):
        await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=message_nodes)
    else:
        await bot.call_api("send_private_forward_msg", user_id=event.user_id, messages=message_nodes)

def handle_list(to_do: list[dict] = None) -> tuple[str, str]:
    """展示目前未完成的需求"""
    # 检查需求列表是否为空
    if not to_do:
        return ("目前无需求", "目前无已完成的需求")
    # 初始化返回的内容
    finish_msg: str = ""
    unfinish_msg: str = ""

    def build_single_msg(requirement: dict):
        """构建单个需求的语句"""
        res: str = f"\n编号: {requirement['id']}\n是否完成: {requirement['finish']}\n需求: {requirement['content']}\n创建于 {requirement['create_at']} by {requirement['create_by']}\n"
        if requirement['last_modify_by']:
            res += f"最后修改于 {requirement['last_modify_at']} by {requirement['last_modify_by']}\n"
        if requirement['finish_by'] and requirement['finish']:
            res += f"finish_by: {requirement['finish_by']}\n"
        return res

    # 将存储的需求转化为str
    for requirement in to_do:
        if requirement['finish']:
            finish_msg += build_single_msg(requirement=requirement)
        else:
            unfinish_msg += build_single_msg(requirement=requirement)
    # 返回已完成和未完成的需求
    return (f"未完成的需求如下：{unfinish_msg}" if unfinish_msg else "目前无需求",
            f"已完成的需求如下：{finish_msg}" if finish_msg else "目前无已完成的需求")

def handle_add(to_do: list[dict] = None, operation_params: list[str] = [], create_by: str = None) -> str:
    """增加需求"""
    # 检查是否有足够的参数
    if operation_params:
        content = operation_params[0]
    else:
        return "请输入要添加的内容"
    # 添加需求到列表
    add_info: dict = {
        "id": to_do[-1]["id"] + 1 if to_do else 1,
        "finish": False,
        "content": content,
        "create_by": create_by,
        "create_at": datetime.now().strftime("%Y-%m-%d"),
        "last_modify_by": "",
        "last_modify_at": "",
        "finish_by": ""
    }
    to_do.append(add_info)
    update_to_do(to_do=to_do)
    return f"需求已添加，对应编号为 {to_do[-1]['id']}"

def handle_remove(to_do: list[dict] = None, operation_params: list[str] = []):
    """删除需求"""
    if operation_params and operation_params[0].isdigit():
        index = int(operation_params[0])
    else:
        return "请输入要删除的需求的下标"
    for i, requirement in enumerate(to_do):
        if requirement["id"] == index:
            del to_do[i]
            update_to_do(to_do=to_do)
            return f"对应编号 {index} 的需求已删除"
    return f"未找到所指定的编号 {index}"

def handle_modify(to_do:list[dict] = None, operation_params: list[str] = [], last_modify_by: str = None):
    """更改需求"""
    # 检查参数
    if len(operation_params) >= 2 and operation_params[0].isdigit():
        index = int(operation_params[0])
        content = operation_params[1]
    else:
        return "请输入正确的下标和修改的内容"
    for i, requirement in enumerate(to_do):
        if requirement["id"] == index:
            to_do[i].update({
                "content": content,
                "last_modify_by": last_modify_by,
                "last_modify_at": datetime.now().strftime("%Y-%m-%d")
            })
            update_to_do(to_do=to_do)
            return f"对应编号 {index} 的需求已修改"
    return f"未找到所指定的编号 {index}"
    
def handle_complete(to_do: list[dict] = None, operation_params: list[str] = [], finish_by: str = "未指定"):
    """更改对应下标的需求的状态"""
    if operation_params and operation_params[0].isdigit():
        index = int(operation_params[0])
    else:
        return "请输入正确的下标"
    for i, requirement in enumerate(to_do):
        if requirement["id"] == index:
            to_do[i].update({
                "finish": not to_do[i]["finish"],
                "finish_by": finish_by
            })
            update_to_do(to_do=to_do)
            return f"已修改对应编号 {index} 的需求的状态"
    return f"未找到所指定的编号 {index}"

@prd.handle()
async def _(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], args: Message = CommandArg()):
    raw_args = args.extract_plain_text()
    params = raw_args.split() if raw_args else []

    # 当没有传入参数时
    if not params:
        await prd.finish(config.default_msg)

    whitelist_person, whitelist_groups = get_whitelist()
    user_id = event.sender.user_id
    group_id = event.group_id
    if str(user_id) not in whitelist_person and str(group_id) not in whitelist_groups:
        await prd.finish("你没有权限使用这个插件")

    try:
        data, _ =JsonUtils.read(config.data_filename, {
            "to_do": []
        })
        to_do = data["to_do"]
        logger.debug(f"to_do is: {to_do}")

        operation = params[0]
        operation_params = params[1:]
        logger.debug(f"operation is: {operation}")
        logger.debug(f"operation_params is: {operation_params}")

        res_msg = None
        if operation in ["list", "ls"]:
            pass
        elif operation in ["add"]:
            res_msg = handle_add(to_do=to_do, operation_params=operation_params, create_by=event.sender.nickname)
        elif operation in ["rm", "remove"]:
            res_msg = handle_remove(to_do=to_do, operation_params=operation_params)
        elif operation in ["modify", "md"]:
            res_msg = handle_modify(to_do=to_do, operation_params=operation_params, last_modify_by=event.sender.nickname)
        elif operation in ["x", "complete"]:
            res_msg = handle_complete(to_do=to_do, operation_params=operation_params, finish_by=event.sender.nickname)
        else:
            return
        
        logger.debug(f"res_msg is: {res_msg}")
        if res_msg:
            await prd.send(res_msg)

        unfinish_msg, finish_msg = handle_list(to_do=to_do)
        await send_forward_msg(bot, event, [unfinish_msg, finish_msg])
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        logger.error(f"prd插件出错: {e}")
