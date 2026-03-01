from nonebot import get_plugin_config, Bot, on_command, logger 
from nonebot.plugin import PluginMetadata 
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent 
from nonebot.adapters import Message 
from nonebot.params import CommandArg 

from .config import Config 
from ...common.send_forward_msg import SendForwardMsg 

# global_config = get_driver().config 
# plugin_config = Config.parse_obj(global_config.dict()) 
plugin_config = get_plugin_config(Config) 

__plugin_meta__ = PluginMetadata( 
    name="cmd_list", 
    description="", 
    usage="", 
    config=Config, 
    supported_adapters={"~onebot.v11"} 
) 

config = get_plugin_config(Config) 

cmd_list = on_command( 
    "cmd", 
    aliases={"命令", "help", "帮助"}, 
    priority=plugin_config.priority, 
    block=plugin_config.block 
) 


@cmd_list.handle() 
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()): 
    try: 
        # 美化排版的命令列表，按功能分组 
        all_commands = [ 
            # 基础命令组 
            "**基础命令**", 
            "/cmd  /命令  /help  /帮助 --- 查看所有命令", 
            "", 
            
            # 实用功能组 
            "**实用功能**", 
            "/考勤 --- 查看考勤情况", 
            "/clipboard --- 剪贴板功能", 
            "/clipboard_md --- Markdown剪贴板功能", 
            "/赞我 --- 给QQ资料卡点赞", 
            "/伪造消息 · 伪消息 --- 生成假消息", 
            "", 
            
            # 竞赛相关组 
            "**竞赛相关**", 
            "/contest --- 查看竞赛信息", 
            "/duel --- CF推题", 
            "/开始监控 · monitor · 取消监控 · stop · 监控 --- ICPC过题监控", 
            "/赛时过题 · 过题情况 --- 查询赛时过题情况", 
            "/过题^ · 过题 --- 记录过题", 
            "/过题积分榜 · 积分榜 --- 查看过题排行榜", 
            "/检查过题 · 过题统计 --- 实时过题查询", 
            "", 
            
            # 群管理组 
            "**群管理**", 
            "/ban · unban · kick --- 群成员管理", 
            "/group --- 群管理功能", 
            "/group_pull --- 群消息转发", 
            "/群统计 --- 群统计功能", 
            "/一键退群 --- 批量退群", 
            "", 
            
            # 技术功能组 
            "**技术功能**", 
            "/sum · summary --- LLM对话记录", 
            "/prd --- PRD功能", 
            "/搬史 · 搬屎 · 转发 --- 搬史功能", 
            "/来点涩图 · 来张涩图 · 来张色图 --- 发送涩图", 
            "/测表格 --- 测试表格生成", 
            "", 
            
            # 系统管理组 
            "**系统管理**", 
            "/rate · 限速启用 · 限速禁用 · 限速紧急停止 · 限速恢复 · 限速状态 · 限速全局 · 限速按群 --- 限速管理", 
            "/todo --- 待办提醒", 
            "/清除缓存 --- 清除群成员缓存" 
        ] 
        
        # 构建美化后的聊天记录消息 
        messages = [ 
            "\n".join(all_commands) 
        ] 
        
        # 根据事件类型选择发送方式 
        if isinstance(event, GroupMessageEvent): 
            await SendForwardMsg.by_onebot_api( 
                bot=bot, 
                event=event, 
                messges=messages, 
                group_id=str(event.group_id) 
            ) 
        elif isinstance(event, PrivateMessageEvent): 
            await SendForwardMsg.by_onebot_api( 
                bot=bot, 
                event=event, 
                messges=messages, 
                user_id=str(event.user_id) 
            ) 
        else: 
            # 其他类型事件使用普通发送 
            cmd_info = messages[0] 
            await bot.send(event=event, message=cmd_info) 
    except Exception as e: 
        logger.opt(exception=True).warning("[cmd_list]响应失败") 
        await bot.send(event=event, message=f"响应失败:\n{e}")
