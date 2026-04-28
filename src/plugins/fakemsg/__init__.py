from nonebot import logger, on_command, get_bot
from nonebot.plugin import PluginMetadata, require
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment, Bot
from typing import List, Optional, cast
import re
import datetime

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from ...common.send_forward_msg import send_forward_msg, SenderInfo
from ...common.json_utils import JsonUtils
from .config import config

__plugin_meta__ = PluginMetadata(
    name="",
    description="",
    usage="",
    extra={

    }
)

MAX_DAILY_TIME = config.fakemsg_max_daily_time
MESSAGE_SEPARATOR = config.fakemsg_user_split
FAKEMSG_CMD = config.fakemsg_cmd
bot_info: Optional[SenderInfo] = None

fakemsg = on_command(
    cmd=FAKEMSG_CMD,
    priority=30,
    block=False
)

def _get_plugin_config():
    data, _ = JsonUtils.read("fakemsg.json", {
        "person_users": [],
        "group_users": [],
        "daily_times_log": {}
    })
    if not isinstance(data, dict):
        logger.warning("无法正确读取文件，使用默认值")
        return {}
    return (
        data.get("person_users", []),
        data.get("group_users", []),
        data.get('daily_times_log', {})
    )

def _daily_times_addone(user_id: str) -> dict:
    """增加使用次数并返回更新后的字典"""
    _, _, daily_times_log = _get_plugin_config()
    current_times = daily_times_log.get(user_id, 0)
    current_times += 1
    daily_times_log[user_id] = current_times
    # 保存到文件
    JsonUtils.update("fakemsg.json", updates={"daily_times_log": daily_times_log})
    return daily_times_log

async def _get_bot_info() -> SenderInfo:
    global bot_info
    if bot_info is None:
        bot: Bot = cast(Bot, get_bot())

        info = await bot.get_login_info()
        self_id = bot.self_id
        nickname = info['nickname']

        bot_info = SenderInfo(user_id=self_id, nickname=nickname, message=Message())

    return bot_info

def process_command(raw_message: str, user_id: str) -> Optional[str]:
    """
    处理用户管理命令：返回处理结果消息（None表示未处理命令）
    :param raw_message: 原始消息内容
    :param user_id: 操作者QQ号（用于权限验证）
    :return: 命令处理结果消息 / None
    """
    # 仅允许管理员执行命令（复用现有权限逻辑）
    person_users, _, _ = _get_plugin_config()
    person_users = [str(person) for person in person_users]
    if str(user_id) not in person_users:
        logger.info(f"{user_id}没有权限使用增删查命令")
        return None

    add_pattern = r"(?:^|\b|\s)-add\s+(\d{6,10})(?!\d)"
    rm_pattern = r"(?:^|\b|\s)-rm\s+(\d{6,10})(?!\d)"
    ls_pattern = r"(?:^|\b|\s)(-ls|-list)\b"

    # 优先处理 -ls/-list
    if re.search(ls_pattern, raw_message):
        if not person_users:
            return "当前person_users列表为空"
        return "当前person_users列表：\n" + "\n".join(f"• {qq}" for qq in sorted(person_users))

    # 处理 -add 命令
    if add_match := re.search(add_pattern, raw_message):
        qq_number = add_match.group(1)
        if qq_number in person_users:
            return f"QQ {qq_number} 已在person_users列表中"
        person_users.append(qq_number)
        JsonUtils.update("fakemsg.json", updates={"person_users": person_users})
        return f"已添加 QQ {qq_number} 到person_users列表"

    # 处理 -rm 命令
    if rm_match := re.search(rm_pattern, raw_message):
        qq_number = rm_match.group(1)
        if qq_number not in person_users:
            return f"QQ {qq_number} 不在person_users列表中"
        person_users.remove(qq_number)
        JsonUtils.update("fakemsg.json", updates={"person_users": person_users})
        return f"已移除 QQ {qq_number} 从person_users列表"

    logger.info("无匹配命令")
    return "无匹配命令"

@fakemsg.handle()
async def _(event: GroupMessageEvent, bot: Bot):
    raw_message = event.raw_message

    if '说' not in raw_message:
        cmd_result = process_command(raw_message, str(event.user_id))
        logger.info(cmd_result)
        if cmd_result is not None:
            await fakemsg.finish(cmd_result)
        return

    # 标记是否实际使用了额度
    should_consume_quota = False
    
    try:
        # 使用前检查日期，确保额度已刷新（防范24:00掉线未更新）
        _check_and_refresh_on_demand()
        
        person_users, group_users, daily_times_log = _get_plugin_config()
        person_users = [str(person_id) for person_id in person_users]
        group_users = [str(group_id) for group_id in group_users]
        logger.info(f"用户 {event.user_id} 在群 {event.group_id} 使用伪消息功能")
        
        is_plugin_user = False
        if str(event.group_id) in group_users or str(event.user_id) in person_users:
            is_plugin_user = True

        # 先检查额度，但不立即增加
        if not is_plugin_user:
            times = daily_times_log.get(str(event.user_id), 0)

            logger.info(f"用户 {event.user_id} 今日已使用 {times}/{MAX_DAILY_TIME} 次")
            if times >= MAX_DAILY_TIME:
                await fakemsg.finish(f"您已超过额度使用上限: {times}/{MAX_DAILY_TIME}")
            # 记录当前次数，用于后续显示
            current_times = times

        await fakemsg.send("正在伪造消息...")

        original_message = event.original_message
        messages = extract_fake_messages(original_message)
        if not messages:
            logger.error("伪造消息失败")
            await fakemsg.finish(
                "伪造消息失败，请检查格式\n"
                "正确格式:\n"
                "• 伪消息 123456789 说内容\n"
                "• 伪消息 @用户 说内容\n"
                f"• 多条消息用 {MESSAGE_SEPARATOR} 分隔"
            )

        # 如果没有权限，需要添加水印消息
        if not is_plugin_user:
            bot_info = await _get_bot_info()
            bot_info.message = Message(
                f"本消息由 {MessageSegment.at(event.user_id)}({event.user_id}) 通过 Bot 生成\n"
                f"Bot 对消息内容概不负责\n"
                f"今日剩余额度: {MAX_DAILY_TIME - current_times - 1}/{MAX_DAILY_TIME}"
            )
            messages.append(bot_info)
            logger.info(f"伪造消息插件使用者: {event.sender.nickname}({event.sender.user_id}) 没有使用权限，将限制ta的使用次数，并自动插入默认消息")

        # 尝试发送消息
        await send_forward_msg.custom_sender_by_onebot_api(bot=bot, event=event, senders_info=messages, group_id=str(event.group_id))
        
        # 发送成功后，标记需要消耗额度
        should_consume_quota = True

    except FinishedException:
        # 如果是主动 finish，不消耗额度
        pass
    except Exception as e:
        logger.error(f"伪消息插件报错：{e}")
        # 发生异常，不消耗额度
        await fakemsg.finish(f"发送失败：{str(e)}")
    finally:
        # 只在成功发送后才消耗额度
        if should_consume_quota and not is_plugin_user:
            _daily_times_addone(user_id=str(event.user_id))

def extract_fake_messages(message: Message) -> List[SenderInfo]:
    """
    从 message 中提取伪造消息。
    
    起始规则：
      - 6-10位数字 + "说"
      - at消息段 + 后续文本以"说"开头（允许前面有空白）
    
    终止规则：
      - 遇到 "MESSAGE_SEPARATOR" 字符
      
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
            m = re.search(r'(\d{6,10})\s*说', text)
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
                    
                    if MESSAGE_SEPARATOR in text:
                        idx = text.index(MESSAGE_SEPARATOR)
                        # MESSAGE_SEPARATOR前面的内容加入正文
                        if idx > 0:
                            content.append(MessageSegment.text(text[:idx]))
                        
                        # 保存当前伪造消息
                        result.append(SenderInfo(user_id=qq, nickname=None, message=Message(content) if content else Message()))
                        
                        # MESSAGE_SEPARATOR后面的内容作为新段继续处理
                        after = text[idx + 1:]
                        if after:
                            segs[i] = MessageSegment.text(after)
                            # 不增加i，外层循环继续处理这段
                        else:
                            i += 1
                        break  # 跳出收集，外层while继续寻找下一个起始
                    
                    else:
                        # 没有MESSAGE_SEPARATOR，整段加入正文
                        content.append(seg)
                        i += 1
                
                else:
                    # 非文本段原样保留
                    content.append(seg)
                    i += 1
            
            else:
                # while正常结束（没有break，即到达消息末尾也没有遇到|）
                # 根据规则，末尾没有MESSAGE_SEPARATOR也保存
                result.append(SenderInfo(user_id=qq, nickname=None, message=Message(content) if content else Message()))
        
        else:
            i += 1
    
    return result

# ========== 每日刷新功能 ==========

def _get_last_refresh_date() -> str:
    """获取上次刷新日期"""
    data, _ = JsonUtils.read("fakemsg.json", {})
    return data.get("last_refresh_date", "")

def _set_last_refresh_date(date_str: str) -> bool:
    """设置上次刷新日期"""
    return JsonUtils.update("fakemsg.json", updates={"last_refresh_date": date_str})

def _refresh_daily_times_log() -> bool:
    """
    刷新daily_times_log，将所有用户的使用次数重置为0
    考虑数据一致性和并发安全问题
    """
    try:
        logger.info("[fakemsg] 开始执行每日额度刷新任务")
        
        # 获取当前日期
        today = datetime.date.today().strftime("%Y-%m-%d")
        
        # 清空daily_times_log
        success = JsonUtils.update("fakemsg.json", updates={"daily_times_log": {}, "last_refresh_date": today})
        
        if success:
            logger.info(f"[fakemsg] 每日额度刷新成功，日期: {today}")
        else:
            logger.error("[fakemsg] 每日额度刷新失败")
        
        return success
    except Exception as e:
        logger.error(f"[fakemsg] 每日额度刷新发生异常: {e}", exc_info=True)
        return False

def _check_and_refresh_on_demand() -> bool:
    """
    按需检查并刷新daily_times_log
    用于防范24:00时bot掉线导致未更新的情况
    """
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        last_refresh = _get_last_refresh_date()
        
        # 如果上次刷新日期不是今天，则需要刷新
        if last_refresh != today:
            logger.info(f"[fakemsg] 检测到日期变更，上次刷新日期: {last_refresh}，当前日期: {today}，需要执行刷新")
            return _refresh_daily_times_log()
        return True
    except Exception as e:
        logger.error(f"[fakemsg] 按需检查刷新发生异常: {e}", exc_info=True)
        return False

# ========== 定时任务 ==========

if config.fakemsg_schedule_enable:
    @scheduler.scheduled_job(
        "cron",
        hour=config.fakemsg_schedule_hour,
        minute=config.fakemsg_schedule_minute,
        second=config.fakemsg_schedule_second,
        id="fakemsg_daily_refresh"
    )
    async def _fakemsg_daily_refresh():
        """每日定时刷新额度"""
        _refresh_daily_times_log()

# 插件加载时执行一次日期检查，处理bot重启后可能遗漏的刷新
_check_and_refresh_on_demand()
