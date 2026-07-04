"""入群审核逻辑

当前为占位实现，统一返回 True（全部放行）。
后续可接入：
- 关键词/正则过滤
- AI 模型审核
- 用户画像/行为分析
- 外部 API 审核
"""
from typing import Optional

from nonebot import logger


async def audit_join_request(
    comment: Optional[str],
    user_id: int,
    group_id: int,
) -> bool:
    """审核入群请求。

    Args:
        comment: 用户填写的入群验证信息（可能为 None）
        user_id: 申请入群的 QQ 号
        group_id: 目标群号

    Returns:
        bool: True 批准入群，False 拒绝入群
    """
    logger.debug(
        f"[group_sentinel] 审核: user={user_id}, group={group_id}, "
        f"comment={comment!r}"
    )

    # === TODO: 实现实际审核逻辑 ===
    # 当前为占位实现，所有请求默认通过
    return True
