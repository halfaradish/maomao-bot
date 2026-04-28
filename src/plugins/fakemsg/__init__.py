from nonebot import logger, on_command, get_bot
from nonebot.plugin import PluginMetadata
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment, Bot
from typing import List, Optional, cast
import re

from ...common.send_forward_msg import send_forward_msg, SenderInfo
from ...common.json_utils import JsonUtils

__plugin_meta__ = PluginMetadata(
    name="",
    description="",
    usage="",
    extra={

    }
)

fakemsg = on_command(
    cmd="伪消息",
    priority=30,
    block=False
)

def _get_plugin_config():
    data, _ = JsonUtils.read("fakemsg.json", {
        "person_users": [],
        "group_users": []
    })
    return (
        data.get("person_users", []),
        data.get("group_users", [])
    )

bot_info: Optional[SenderInfo] = None
async def _get_bot_info() -> SenderInfo:
    global bot_info
    if bot_info is None:
        bot: Bot = cast(Bot, get_bot())

        info = await bot.get_login_info()
        self_id = bot.self_id
        nickname = info['nickname']

        bot_info = SenderInfo(user_id=self_id, nickname=nickname, message=Message())

    return bot_info

def remove_until_pseudo_message(s: str) -> str:
    """
    删除第一个 '伪消息' 及其之前的所有内容
    """
    index = s.find("伪消息")
    if index == -1:
        return s  # 未找到则返回原字符串
    return s[index + len("伪消息"):]

@fakemsg.handle()
async def _(event: GroupMessageEvent, bot: Bot):

    await fakemsg.send("正在伪造消息...")

    try:
        person_users, group_users = _get_plugin_config()
        person_users = [str(person_id) for person_id in person_users]
        group_users = [str(group_id) for group_id in group_users]
        logger.info(f"用户id: {event.self_id}, 用户所在群组: {event.group_id}")
        logger.info(f"白名单群组: {group_users}")
        logger.info(f"白名单用户: {person_users}")
        
        is_plugin_user = False
        if str(event.group_id) in group_users or str(event.user_id) in person_users:
            is_plugin_user = True
    except Exception as e:
        logger.error(f"伪消息插件权限检测失败: {e}")
        await fakemsg.finish("权限检测失败...")

    try:
        original_message = event.original_message
        messages = extract_fake_messages(original_message)
        if not messages:
            logger.error("伪造消息失败")
            await fakemsg.finish("请检查消息是否符合生成规则")

        if not is_plugin_user:
            bot_info = await _get_bot_info()
            bot_info.message = Message("本消息由 " + MessageSegment.at(event.user_id) + f"({event.user_id}) 使用{bot_info.nickname} bot生成，{bot_info.nickname} bot对本消息概不负责")
            messages.append(bot_info)
            logger.info(f"伪造消息插件使用者: {event.sender.nickname}({event.sender.user_id}) 没有使用权限，将限制ta的使用次数，并自动插入默认消息")

        await send_forward_msg.custom_sender_by_onebot_api(bot=bot, event=event, senders_info=messages, group_id=str(event.group_id))

    except FinishedException:
        pass
    except Exception as e:
        logger.error(f"伪消息插件报错：{e}")

def extract_fake_messages(message: Message) -> List[SenderInfo]:
    """
    从 message 中提取伪造消息。
    
    起始规则：
      - 6-10位数字 + "说"
      - at消息段 + 后续文本以"说"开头（允许前面有空白）
    
    终止规则：
      - 遇到 "|" 字符
      
    非文本段原样保留在正文中。
    
    返回: [SenderInfo]
    """
    if not message:
        return []
    
    # 转为可变列表
    segs = list(message)
    result: List[SenderInfo] = []
    i = 0
    
    while i < len(segs):
        qq: Optional[str] = None
        
        # ========== 模式1: at + "说" ==========
        if (
            segs[i].type == "at"
            and i + 1 < len(segs)
            and segs[i + 1].type == "text"
        ):
            at_qq = str(segs[i].data.get("qq", ""))
            text = segs[i + 1].data.get("text", "")
            # 匹配: 可选空白 + "说" + 剩余所有内容
            m = re.match(r'^(\s*)说([\s\S]*)$', text)
            if m:
                qq = at_qq
                # 去掉"说"前缀，保留后续内容
                prefix_len = len(m.group(1)) + 1  # 空白长度 + "说"字
                segs[i + 1] = MessageSegment.text(text[prefix_len:])
                i += 1  # i现在指向修改后的文本段
        
        # ========== 模式2: 数字 + "说" ==========
        elif segs[i].type == "text":
            text = segs[i].data.get("text", "")
            m = re.search(r'(\d{6,10})说', text)
            if m:
                qq = m.group(1)
                # 保留"说"之后的内容，之前的内容丢弃
                segs[i] = MessageSegment.text(text[m.end():])
                # i不变，下面从当前段开始收集
        
        # ========== 收集正文 ==========
        if qq is not None:
            content: List[MessageSegment] = []
            
            while i < len(segs):
                seg = segs[i]
                
                if seg.type == "text":
                    text = seg.data.get("text", "")
                    
                    if '|' in text:
                        idx = text.index('|')
                        # |前面的内容加入正文
                        if idx > 0:
                            content.append(MessageSegment.text(text[:idx]))
                        
                        # 保存当前伪造消息
                        result.append(SenderInfo(user_id=qq, nickname=None, message=Message(content) if content else Message()))
                        
                        # |后面的内容作为新段继续处理
                        after = text[idx + 1:]
                        if after:
                            segs[i] = MessageSegment.text(after)
                            # 不增加i，外层循环继续处理这段
                        else:
                            i += 1
                        break  # 跳出收集，外层while继续寻找下一个起始
                    
                    else:
                        # 没有|，整段加入正文
                        content.append(seg)
                        i += 1
                
                else:
                    # 非文本段原样保留
                    content.append(seg)
                    i += 1
            
            else:
                # while正常结束（没有break，即到达消息末尾也没有遇到|）
                # 根据规则，末尾没有|也保存（见例子2）
                result.append(SenderInfo(user_id=qq, nickname=None, message=Message(content) if content else Message()))
        
        else:
            i += 1
    
    return result
