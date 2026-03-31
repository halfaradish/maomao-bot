import re
import json
from typing import Union, List, Tuple
from pathlib import Path

from nonebot import logger, on_message
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    PrivateMessageEvent,
    MessageEvent
)
from nonebot.plugin import PluginMetadata, get_driver

from .config import Config, config

__plugin_meta__ = PluginMetadata(
    name="消息伪造",
    description="伪造消息",
    usage="qq+说+内容|qq+说+内容 或 @某人 说+内容",
    config=Config,
    type="application",
    homepage="https://github.com/Cvandia/nonebot-plugin-fakemsg",
    supported_adapters={"~onebot.v11"},
)

driver = get_driver()
superusers = driver.config.superusers

# 配置默认值
user_split = getattr(config, "user_split", "|")
message_split = getattr(config, "message_split", "|")
fakemsg_enable = getattr(config, "fakemsg_enable", True)

# 数据文件路径
DATA_PATH = Path("data/fakemsg/fakemsg.json")


def load_config() -> Tuple[List[str], List[str], List[str]]:
    """加载配置文件"""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        default_data = {
            "fakemsg_user": [],
            "fakemsg_whitelist": [],
            "group_users": []
        }
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        return [], [], []
    
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return (
        data.get("fakemsg_user", []),
        data.get("fakemsg_whitelist", []),
        data.get("group_users", [])
    )


def save_config(fakemsg_user: List[str], whitelist: List[str], group_users: List[str]):
    """保存配置文件"""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "fakemsg_user": fakemsg_user,
        "fakemsg_whitelist": whitelist,
        "group_users": group_users
    }
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_permission(event: Union[GroupMessageEvent, PrivateMessageEvent], fakemsg_user: List[str], group_users: List[str]) -> bool:
    """检查用户是否有使用权限"""
    if not fakemsg_enable:
        return False
    user_id = str(event.user_id)
    if user_id in superusers:
        return True
    if user_id in fakemsg_user:
        return True
    if isinstance(event, GroupMessageEvent) and str(event.group_id) in group_users:
        return True
    return False


async def send_forward_msg(
    bot: Bot,
    event: MessageEvent,
    user_message: List[Tuple[str, str, Message]],
):
    """发送 forward 消息"""
    def to_json(info: Tuple[str, str, Message]):
        return {
            "type": "node",
            "data": {"name": info[0], "uin": info[1], "content": info[2]},
        }

    messages = [to_json(info) for info in user_message]

    if isinstance(event, GroupMessageEvent):
        await bot.call_api(
            "send_group_forward_msg", group_id=event.group_id, messages=messages
        )
    else:
        await bot.call_api(
            "send_private_forward_msg", user_id=event.user_id, messages=messages
        )


# 使用 on_message 监听普通消息
fakemsg_handler = on_message(priority=5, block=False)


@fakemsg_handler.handle()
async def handle_fakemsg(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent]):
    """处理伪造消息"""
    fakemsg_user, whitelist, group_users = load_config()
    
    # 检查权限
    if not check_permission(event, fakemsg_user, group_users):
        return
    
    # 检查消息是否包含 @
    has_at = any(seg.type == "at" for seg in event.original_message)
    
    fake_msg_list = []
    
    # 解析消息
    if has_at:
        # 处理 @ 格式: @某人 说内容
        at_qqs = []
        text_parts = []
        
        for seg in event.original_message:
            if seg.type == "at":
                at_qqs.append(seg.data.get("qq", ""))
            elif seg.type == "text":
                text_parts.append(seg.data.get("text", ""))
        
        full_text = "".join(text_parts).strip()
        
        # 检查是否包含"说"
        if "说" not in full_text:
            return
        
        # 分割多条消息
        user_msgs = full_text.split(user_split)
        
        for i, user_msg in enumerate(user_msgs):
            user_msg = user_msg.strip()
            if not user_msg or not user_msg.startswith("说"):
                continue
            
            content = user_msg[1:]  # 去掉"说"
            
            if i < len(at_qqs):
                user_qq = at_qqs[i]
            else:
                await fakemsg_handler.finish("QQ号与消息数量不匹配")
            
            # 白名单检测
            if user_qq in whitelist and str(event.user_id) not in superusers:
                await fakemsg_handler.finish(f"你没有权限伪造该用户（{user_qq}）的消息。")
            
            try:
                user_info = await bot.get_stranger_info(user_id=int(user_qq))
                user_name = user_info["nickname"]
            except Exception as e:
                logger.warning(f"获取用户信息失败: {e}")
                user_name = f"用户{user_qq}"
            
            # 支持多条消息分割
            for msg in content.split(message_split):
                if msg.strip():
                    fake_msg_list.append((user_name, user_qq, msg.strip()))
    
    else:
        # 处理 qq号说内容 格式
        full_text = event.original_message.extract_plain_text().strip()
        
        if "说" not in full_text:
            return
        
        # 分割多条消息
        user_msgs = full_text.split(user_split)
        
        for user_msg in user_msgs:
            user_msg = user_msg.strip()
            if not user_msg:
                continue
            
            # 匹配 qq号说内容 格式
            match = re.match(r"^(\d{6,10})说(.+)$", user_msg)
            if not match:
                continue
            
            user_qq = match.group(1)
            content = match.group(2)
            
            # 白名单检测
            if user_qq in whitelist and str(event.user_id) not in superusers:
                await fakemsg_handler.finish(f"你没有权限伪造该用户（{user_qq}）的消息。")
            
            try:
                user_info = await bot.get_stranger_info(user_id=int(user_qq))
                user_name = user_info["nickname"]
            except Exception as e:
                logger.warning(f"获取用户信息失败: {e}")
                user_name = f"用户{user_qq}"
            
            # 支持多条消息分割
            for msg in content.split(message_split):
                if msg.strip():
                    fake_msg_list.append((user_name, user_qq, msg.strip()))
    
    if not fake_msg_list:
        return
    
    try:
        await send_forward_msg(bot, event, fake_msg_list)
    except Exception as e:
        logger.error(f"发送伪造消息失败: {e}")
        await fakemsg_handler.finish(f"发送失败: {e}")


# 管理命令 (仅超级用户)
fakemsg_admin = on_command("伪消息管理", aliases={"fakemsg"}, priority=10, block=True, permission=SUPERUSER)


@fakemsg_admin.handle()
async def handle_admin(bot: Bot, event: MessageEvent, args: Message = None):
    """管理伪造消息权限"""
    if args:
        raw_args = args.extract_plain_text().strip().split()
    else:
        raw_args = []
    
    fakemsg_user, whitelist, group_users = load_config()
    
    if not raw_args:
        await fakemsg_admin.finish(
            "伪消息管理命令:\n"
            "ls - 查看白名单\n"
            "add user/group [id] - 添加用户/群组权限\n"
            "rm user/group [id] - 移除用户/群组权限\n"
            "whitelist add/rm [qq] - 管理保护白名单"
        )
    
    operation = raw_args[0].lower()
    
    if operation in ["ls", "list"]:
        res_msg = (
            f"已添加的个人用户: {fakemsg_user}\n"
            f"已添加的群组: {group_users}\n"
            f"保护白名单: {whitelist}"
        )
        await fakemsg_admin.finish(res_msg)
    
    elif operation in ["add", "rm", "remove"]:
        if len(raw_args) < 3:
            await fakemsg_admin.finish("请输入 user/group 和 ID\n例如: add user 123456")
        
        add = operation == "add"
        target_type = raw_args[1].lower()
        target_id = raw_args[2]
        
        if target_type in ["user", "person"]:
            if add and target_id not in fakemsg_user:
                fakemsg_user.append(target_id)
            elif not add and target_id in fakemsg_user:
                fakemsg_user.remove(target_id)
            save_config(fakemsg_user, whitelist, group_users)
            await fakemsg_admin.finish(f"{'添加' if add else '移除'}用户 {target_id} {'成功' if add else '成功'}")
        
        elif target_type == "group":
            if add and target_id not in group_users:
                group_users.append(target_id)
            elif not add and target_id in group_users:
                group_users.remove(target_id)
            save_config(fakemsg_user, whitelist, group_users)
            await fakemsg_admin.finish(f"{'添加' if add else '移除'}群组 {target_id} {'成功' if add else '成功'}")
        
        else:
            await fakemsg_admin.finish("请输入正确的类型: user 或 group")
    
    elif operation == "whitelist":
        if len(raw_args) < 3:
            await fakemsg_admin.finish("请输入 whitelist add/rm [qq]")
        
        sub_op = raw_args[1].lower()
        qq = raw_args[2]
        
        if sub_op == "add" and qq not in whitelist:
            whitelist.append(qq)
        elif sub_op == "rm" and qq in whitelist:
            whitelist.remove(qq)
        else:
            await fakemsg_admin.finish("操作失败或已存在/不存在")
        
        save_config(fakemsg_user, whitelist, group_users)
        await fakemsg_admin.finish(f"白名单{sub_op}成功")
    
    else:
        await fakemsg_admin.finish("未知命令")