from nonebot import get_plugin_config
from nonebot import logger
import http.client
import json

from .config import Config
from ...common import JsonUtils

plugin_config = get_plugin_config(Config)

def get_forward_msg(message_id: str) -> list[dict]:
    """
    获取合并转发消息

    Args:
        message_id: (str) 消息 ID

    Returns:
        messages: list[dict] 合并转发消息列表
    """
    try:
        if not message_id:
            logger.warning("[搬史] 获取合并转发消息时, message_id 不能为空")
            return []
        # 创建 HTTP 连接
        conn =http.client.HTTPConnection(plugin_config.api_host, plugin_config.api_port)
        payload = json.dumps({
            "message_id": message_id
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': plugin_config.api_tokne
        }
        # 发送 POST 请求
        conn.request("POST", "/get_forward_msg", payload, headers)
        res = conn.getresponse()
        data = res.read()
        return json.loads(data.decode('utf-8')).get("data", []).get("messages", [])
    except Exception as e:
        logger.opt(exception=True).error(f"[搬史] 获取合并转发消息失败: {e}")
        return []

def get_content(message: dict) -> list[dict]:
    """获取转发消息内容"""
    if not message:
        logger.warning("[搬史] 获取转发消息内容时, message 不能为空")
        return []
    message_type = message.get("type", "")
    if message_type == "text":
        return [{"type": "text", "data": {"text": message.get("data", {}).get("text", "")}}]
    elif message_type == "face":
        return [{"type": "face", "data": {"id": message.get("data", {}).get("id", 0)}}]
    elif message_type == "image":
        return [{"type": "image", "data": {"file": message.get("data", {}).get("file", ""), "summary": message.get("data", {}).get("summary", "")}}]
    elif message_type == "reply":
        return [{"type": "reply", "data": {"id": message.get("data", {}).get("id", 0)}}]
    elif message_type == "json":
        return [{"type": "json", "data": {"data": message.get("data", {}).get("data", {})}}]
    elif message_type == "video":
        return [{"type": "video", "data": {"file": message.get("data", {}).get("file", "")}}]
    elif message_type == "file":
        return [{"type": "file", "data": {"file": message.get("data", {}).get("file_id", ""), "name": message.get("data", {}).get("file", "")}}]
    elif message_type == "record":
        return [{"type": "record", "data": {"content": message.get("data", {}).get("content", "")}}]
    elif message_type == "forward":
        return [{"type": "forward", "data": {"content": message.get("data", {}).get("data", {}).get("content", [])}}]
    else:
        logger.warning(f"[搬史] 未知消息类型: {message_type}")
        return [{"type": "text", "data": {"text": "未知消息类型"}}]

def build_forward_node(msg: dict) -> dict:
    """
    构建转发消息的节点

    Args:
        msg: dict 消息内容

    Returns:
        node: dict 转发消息节点
    """
    return {
        "type": "node",
        "data": {
            "nickname": msg.get("sender", {}).get("nickname", "未知用户"),
            "user_id": str(msg.get("sender", {}).get("user_id", "")),
            "content": get_content(msg.get("message", [])[0])
        }
    }

def build_forward_msg(messages: list[dict]) -> list[dict]:
    """
    构建转发消息的格式

    Args:
        messages: list[dict] 消息列表

    Returns:
        forward_messages: list[dict] 转发消息列表
    """
    forward_messages = []
    for msg in messages:
        if "sender" in msg and "message" in msg:
            if msg["message"][0].get("type") == "forward":
                forward_messages.append({
                    "type": "node",
                    "data": {
                        "nickname": msg["sender"].get("nickname", "未知用户"),
                        "user_id": str(msg["sender"].get("user_id", "")),
                        "content": build_forward_msg(
                            msg["message"][0].get("data", {}).get("content", [])
                        )
                    }
                })
                continue
            forward_messages.append(
                build_forward_node(msg)
            )
    return forward_messages

def get_forward_groups() -> list[int]:
    """
    获取转发的群列表

    Returns:
        forward_groups: list[int] 转发群列表
    """
    try:
        filename = plugin_config.data_filename
        content = []
        content, _ = JsonUtils.read(filename, {})

        return content.get('forward_groups', [])
    except Exception as e:
        logger.opt(exception=True).error(f"[搬史] 获取转发群列表失败: {e}")
        return []
    
def send_group_forward_msg(group_id: int, payload: dict) -> None:
    """
    发送群转发消息

    Args:
        group_id: (int) 群 ID
        forward_msg: dict 转发消息中除了群号的内容
    """
    try:
        conn = http.client.HTTPConnection(plugin_config.api_host, plugin_config.api_port)
        headers = {
            'Content-Type': 'application/json',
            'Authorization': plugin_config.api_tokne
        }
        payload = json.dumps({**payload, "group_id": group_id})
        #region
        # payload = json.dumps({
        #     "group_id": group_id,
        #     "messages": forward_msg,
        #     "news": [],
        #     "prompt": "",
        #     "summary": "",
        #     "source": ""
        # })
        #endregion
        conn.request("POST", "/send_group_forward_msg", payload, headers)
        res = conn.getresponse()
        data = res.read()
        logger.info(f"转发消息到群 {group_id} 响应: {data.decode('utf-8')}")
    except Exception as e:
        logger.opt(exception=True).error(f"[搬史] 发送群转发消息失败: {e}")
