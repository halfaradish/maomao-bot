"""llm_scribe 权限点注册

注册权限点到权限系统，支持 WebUI 管理面板可视化和 GroupPermBinding 群绑定。
"""
from src.common.permission import register_perm_point

register_perm_point(
    "llm_scribe:sum",
    "生成群聊摘要",
    "允许使用 sum/summary 命令生成群聊摘要（会调用 LLM，消耗额度）",
    plugin_name="llm_scribe",
)
