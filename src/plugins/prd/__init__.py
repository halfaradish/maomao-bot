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
    message_nodes = [to_node(name=name, uin=uin, message=Message(message)) for message in messges]

    if isinstance(event, GroupMessageEvent):
        await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=message_nodes)
    else:
        await bot.call_api("send_private_forward_msg", user_id=event.user_id, messages=message_nodes)

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
    finish_msg_dict: dict = {element:"" for element in exist_groups}
    unfinish_msg_dict: dict = {element:"" for element in exist_groups}
    # 保证默认的'其他'组别存在
    finish_msg_dict['其他'] = ''
    unfinish_msg_dict['其他'] = ''

    # 分类
    for requirement in to_do:
        group_name = requirement.get('group', '其他')
        if requirement['finish']:
            finish_msg_dict[group_name if group_name in exist_groups else '其他'] += build_single_msg(requirement=requirement)
        else:
            unfinish_msg_dict[group_name if group_name in exist_groups else '其他'] += build_single_msg(requirement=requirement)
    # 需要返回的内容
    finish_msg_list = [f"{key}:\n{val if val else '无'}" for key, val in finish_msg_dict.items()]
    unfinish_msg_list = [f"{key}:\n{val if val else '无'}" for key, val in unfinish_msg_dict.items()]
    # 添加初始化内容
    finish_msg_list.insert(0, "已完成的需求如下")
    unfinish_msg_list.insert(0, "未完成的需求如下")

    return (finish_msg_list, unfinish_msg_list)


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
        "group": "其他",
        "content": content,
        "create_by": create_by,
        "create_at": datetime.now().strftime("%Y-%m-%d"),
        "last_modify_by": "",
        "last_modify_at": "",
        "finish_by": "",
        "finish_at": ""
    }
    to_do.append(add_info)
    update_to_do(to_do=to_do)
    return f"需求已添加，对应编号为 {to_do[-1]['id']}" + build_single_msg(requirement=to_do[-1])

def handle_remove(to_do: list[dict] = None, operation_params: list[str] = []):
    """删除需求"""
    if operation_params and operation_params[0].isdigit():
        index = int(operation_params[0])
    else:
        return "请输入要删除的需求的下标"
    for i, requirement in enumerate(to_do):
        if requirement["id"] == index:
            res: str = f"对应编号 {index} 的需求已删除" + build_single_msg(requirement=requirement)
            del to_do[i]
            update_to_do(to_do=to_do)
            return res
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
            return f"对应编号 {index} 的需求已修改" + build_single_msg(requirement=requirement)
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
                "finish_at": datetime.now().strftime("%Y-%m-%d"),
                "finish_by": finish_by
            })
            update_to_do(to_do=to_do)
            return f"已修改对应编号 {index} 的需求的状态" + build_single_msg(requirement=requirement)
    return f"未找到所指定的编号 {index}"

def handle_grouped(to_do: list[dict] = None, operation_params: list[str] = [], exist_groups: list[str] = []):
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
    # 更改分类
    for i, requirement in enumerate(to_do):
        if requirement['id'] == index:
            to_do[i].update({
                "group": group_name
            })
            update_to_do(to_do)
            return f"对应下标 {index} 的组别已更改 {group_name}\n" + build_single_msg(requirement=requirement)

def handle_assign(to_do: list[dict] = None, operation_params: list[str] = [], assign_by: str = None):
    """给需求分配执行人"""
    if len(operation_params) < 2:
        return "参数格式错误，请使用：/prd 执行人名字 xxx 编号"
    
    # 检查参数格式：["执行人名字", "xxx", "编号"]
    if operation_params[1] != "xxx":
        return "参数格式错误，请使用：/prd 执行人名字 xxx 编号"
    
    if not operation_params[2].isdigit():
        return "请输入正确的编号"
    
    assign_to_name = operation_params[0]  # 自定义执行人名字
    index = int(operation_params[2])      # 需求编号
    
    for i, requirement in enumerate(to_do):
        if requirement["id"] == index:
            to_do[i].update({
                "assign_to": assign_to_name,
                "assign_at": datetime.now().strftime("%Y-%m-%d"),
                "assign_by": assign_by
            })
            update_to_do(to_do=to_do)
            return f"已为编号 {index} 的需求分配执行人: {assign_to_name}\n" + build_single_msg(requirement=requirement)
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
            "exist_groups": [],
            "to_do": []
        })
        to_do = data["to_do"]
        exist_groups = data["exist_groups"]
        logger.debug(f"to_do is: {to_do}")

        operation = params[0]
        operation_params = params[1:]
        logger.debug(f"operation is: {operation}")
        logger.debug(f"operation_params is: {operation_params}")

        res_msg = None
        
        # 检查是否是新的分配执行人命令格式：执行人名字 xxx 编号
        if len(params) >= 3 and params[1] == "xxx":
            res_msg = handle_assign(to_do=to_do, operation_params=params, assign_by=event.sender.nickname)
        elif operation in ["list", "ls"]:
            pass
        elif operation in ["add"]:
            res_msg = handle_add(to_do=to_do, operation_params=operation_params, create_by=event.sender.nickname)
        elif operation in ["rm", "remove"]:
            res_msg = handle_remove(to_do=to_do, operation_params=operation_params)
        elif operation in ["modify", "md"]:
            res_msg = handle_modify(to_do=to_do, operation_params=operation_params, last_modify_by=event.sender.nickname)
        elif operation in ["x", "complete"]:
            res_msg = handle_complete(to_do=to_do, operation_params=operation_params, finish_by=event.sender.nickname)
        elif operation in ["group", "分组"]:
            res_msg = handle_grouped(to_do=to_do, operation_params=operation_params, exist_groups=data.get('exist_groups', []))
        else:
            return
        
        logger.debug(f"res_msg is: {res_msg}")
        if res_msg:
            await prd.send(res_msg)

        finish_msg_list, unfinish_msg_list = handle_list(to_do=to_do, exist_groups=exist_groups)
        await send_forward_msg(bot, event, unfinish_msg_list)
        await send_forward_msg(bot, event, finish_msg_list)
    except FinishedException:
        # 让 FinishedException 正常传递，不记录为错误
        raise
    except Exception as e:
        logger.error(f"prd插件出错: {e}")
