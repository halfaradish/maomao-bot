"""
消息发送限速中间件插件
"""
from nonebot.plugin import PluginMetadata
from . import middleware
from src.common.model.model import PluginGroupEnum, PluginBadgeColor

__plugin_meta__ = PluginMetadata(
    name="消息发送限速中间件",
    description="使用令牌桶算法对消息发送进行限速，支持按群限速和全局限速",
    usage="限速器启用 —— 启用消息发送限速\n限速器禁用 —— 禁用消息发送限速\n限速器模式 全局 —— 启用全局限速模式\n限速器模式 群 —— 启用按群限速模式",
    type="application",
    supported_adapters={"~onebot.v11"},
    extra={
        "group": PluginGroupEnum.BASE.value,
        "badge_color": PluginBadgeColor.BLUE.value,
        "author": "移植自其他bot",
        "version": "1.0.0",
    },
)

# 导入所有内容以确保命令处理器被注册

__all__ = [
    "middleware",
]

