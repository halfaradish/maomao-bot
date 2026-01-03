"""
消息发送限速中间件插件
"""
from nonebot.plugin import PluginMetadata
from . import middleware

__plugin_meta__ = PluginMetadata(
    name="消息发送限速中间件",
    description="使用令牌桶算法对消息发送进行限速，支持按群限速和全局限速",
    usage="通过命令控制限速器的启用/禁用和模式切换",
    type="application",
    supported_adapters={"~onebot.v11"},
    extra={
        "author": "移植自其他bot",
        "version": "1.0.0",
    },
)

# 导入所有内容以确保命令处理器被注册

__all__ = [
    "middleware",
]

