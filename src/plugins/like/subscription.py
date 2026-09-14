"""订阅状态判定

把「永久订阅 / 七天试用订阅」的覆盖优先级从数据库读写中拆出来，
便于在无 bot、无数据库的环境下直接校验（见 test/like_subscribe_precedence.py）。
"""
from datetime import datetime

ACTION_ALLOW = "allow"                    # 按请求写入
ACTION_KEEP_PERMANENT = "keep_permanent"  # 已是永久订阅，试用请求不得降级
ACTION_TRIAL_ACTIVE = "trial_active"      # 试用期未到期，不重复发放


def resolve_subscribe_action(
    *,
    is_trial: bool,
    exists: bool,
    is_following: bool,
    trial_expires_at: datetime | None,
    now: datetime,
) -> str:
    """判定本次订阅请求该如何落库

    规则：永久订阅优先于试用订阅（试用请求不得降级进行中的永久订阅），
    试用期内不重复发放（避免反复发 /订阅赞 无限续期）。

    Args:
        is_trial: 本次请求是否为试用订阅
        exists: 是否已有 LikeRecord
        is_following: 已有记录的订阅状态
        trial_expires_at: 已有记录的试用到期时间，None 表示永久订阅
        now: 当前时间
    """
    # 只有「试用请求命中一条进行中的订阅」才需要判定
    if not (is_trial and exists and is_following):
        return ACTION_ALLOW
    if trial_expires_at is None:
        return ACTION_KEEP_PERMANENT
    if trial_expires_at > now:
        return ACTION_TRIAL_ACTIVE
    # 试用已过期（清理任务每天 5:00 才跑，此处可能仍是 is_following=True）→ 允许重新发放
    return ACTION_ALLOW
