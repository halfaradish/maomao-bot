from nonebot import on_message, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, Message
from nonebot.exception import FinishedException
import json
import random
from datetime import datetime
from pathlib import Path

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

SAVE_KEYWORDS = ["内推", "内推码"]
GET_KEYWORDS = ["查内推", "获取内推", "我要内推", "求内推", "内推码求一份"]

plugin_data_dir = store.get_plugin_data_dir()
IMAGE_SAVE_DIR = plugin_data_dir / "saved_images"
IMAGE_SAVE_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = plugin_data_dir / "referral_records.json"

matcher = on_message(priority=10, block=False)

@matcher.handle()
async def handle_referral(bot: Bot, event: MessageEvent):
    raw_msg = str(event.get_message()).strip()
    
    if any(keyword in raw_msg for keyword in GET_KEYWORDS):
        await handle_get_referral(bot, event, raw_msg)
        return

    if any(keyword in raw_msg for keyword in SAVE_KEYWORDS):
        await handle_save_referral(bot, event, raw_msg)
        return

    return

async def handle_get_referral(bot: Bot, event: MessageEvent, raw_msg: str):
    data_list = load_data()
    
    if not data_list:
        await matcher.finish("📭 暂无内推码记录，快去群里发一张带内推码的图片吧！", at_sender=True)

    valid_records = [r for r in data_list if Path(r["saved_file"]).exists()]
    
    if not valid_records:
        await matcher.finish("⚠️ 数据库有记录，但图片文件似乎丢失了，请联系管理员。", at_sender=True)

    is_group = getattr(event, 'group_id', None) is not None
    
    
    if is_group:
        record = random.choice(valid_records)
        tip = f"🎲 群内随机掉落一个内推码（共收录 {len(valid_records)} 个）："
    else:
        record = valid_records[-1]
        tip = f"📥 这是最新收录的内推码（共收录 {len(valid_records)} 个）："

    try:
        img_path = record["saved_file"]
        sender_info = record.get("sender_id", "未知用户")
        time_info = record.get("time", "未知时间").split("T")[0]
        
        msg_text = (
            f"{tip}\n"
            f"👤 提供者: {sender_info}\n"
            f"📅 收录时间: {time_info}\n"
            f"👇 图片如下："
        )
        
        await bot.send(
            event, 
            Message(msg_text) + MessageSegment.image(f"file://{img_path}")
        )
        
        await matcher.finish("✨ 内推码已送达，祝面试顺利！🍀", at_sender=True)
        
    except FinishedException:
        raise
        
    except Exception as e:
        print(f"❌ 发送内推码失败: {e}")
        await matcher.finish(f"❌ 提取内推码时出错：{str(e)}", at_sender=True)

async def handle_save_referral(bot: Bot, event: MessageEvent, raw_msg: str):
    msg = event.get_message()
    image_found = False
    
    for seg in msg:
        if seg.type == "image":
            image_found = True
            file_id = seg.data.get("file")
            
            if not file_id:
                continue

            try:
                print(f"🔍 [流程] 检测到关键词，开始处理图片... (ID: {file_id[:8]}...)")

                result = await bot.call_api("get_image", file_id=file_id)
                data_content = result
                if isinstance(result, dict) and "data" in result:
                    data_content = result["data"]
                
                local_path_str = data_content.get("file")
                
                if not local_path_str:
                    raise ValueError("API 未返回 file 路径")

                if local_path_str.startswith("file://"):
                    local_path_str = local_path_str[7:]
                
                source_path = Path(local_path_str)
                if not source_path.exists():
                    raise FileNotFoundError(f"源文件不存在: {source_path}")

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                sender_id = event.get_user_id()
                filename = f"{timestamp}_{sender_id}.jpg"
                dest_path = IMAGE_SAVE_DIR / filename

                content = source_path.read_bytes()
                dest_path.write_bytes(content)

                print(f"✅ [成功] 图片已保存至: {dest_path}")

                record = {
                    "saved_file": str(dest_path),
                    "cache_file": str(source_path),
                    "file_size": len(content),
                    "sender_id": sender_id,
                    "group_id": getattr(event, 'group_id', None),
                    "keyword": raw_msg,
                    "time": datetime.now().isoformat()
                }
                
                data_list = load_data()
                data_list.append(record)
                save_data(data_list)
                
                await matcher.finish(f"✨ 内推图片捕获成功！\n已保存 ({len(content)} bytes)", at_sender=True)
                return 

            except FinishedException:
                raise 
            except Exception as e:
                print(f"❌ [异常] 图片处理失败: {type(e).__name__}: {e}")
                await matcher.finish(f"❌ 图片处理失败: {str(e)}", at_sender=True)
                return
    
    if not image_found:
        pass

def load_data():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("⚠️ JSON 文件损坏，重置数据列表")
            return []
    return []

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"❌ 保存 JSON 失败: {e}")