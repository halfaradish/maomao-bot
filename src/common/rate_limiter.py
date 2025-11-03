"""
令牌桶限速器实现
使用令牌桶算法控制消息发送速率
"""
import asyncio
import time
from typing import Optional
from collections import defaultdict


class TokenBucketLimiter:
    """
    令牌桶限速器

    原理：
    - 桶中有固定数量的令牌（capacity）
    - 按固定速率补充令牌（refill_rate 个/秒）
    - 每次发送消耗1个令牌
    - 无令牌时等待直到有令牌可用
    """

    def __init__(self, capacity: int = 5, refill_rate: float = 2.0):
        """
        初始化令牌桶

        Args:
            capacity: 桶容量（允许突发发送的最大数量）
            refill_rate: 令牌补充速率（个/秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity  # 当前令牌数
        self.last_refill = time.time()  # 上次补充时间
        self._lock = asyncio.Lock()  # 异步锁

    async def acquire(self, tokens: int = 1):
        """
        获取令牌，如果无令牌则等待

        Args:
            tokens: 需要获取的令牌数量（默认1）
        """
        async with self._lock:
            # 补充令牌
            await self._refill()

            # 检查是否有足够的令牌
            if self.tokens >= tokens:
                self.tokens -= tokens
                return

            # 计算需要等待的时间
            needed = tokens - self.tokens
            wait_time = needed / self.refill_rate

            # 等待并补充令牌
            await asyncio.sleep(wait_time)
            await self._refill()
            self.tokens -= tokens

    async def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_refill

        if elapsed > 0:
            # 计算应该补充的令牌数
            tokens_to_add = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now


class GroupRateLimiter:
    """
    按群组分别限速的限速器
    每个群组使用独立的令牌桶
    """

    def __init__(self, capacity: int = 5, refill_rate: float = 2.0):
        """
        初始化群组限速器

        Args:
            capacity: 每个群的桶容量
            refill_rate: 每个群的令牌补充速率（个/秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.limiters: dict[int, TokenBucketLimiter] = defaultdict(
            lambda: TokenBucketLimiter(capacity, refill_rate)
        )

    async def acquire(self, group_id: Optional[int] = None):
        """
        获取令牌（按群组）

        Args:
            group_id: 群组ID，如果为None则使用全局限速
        """
        if group_id is None:
            # 全局限速（使用默认limiter）
            if not hasattr(self, '_global_limiter'):
                self._global_limiter = TokenBucketLimiter(self.capacity, self.refill_rate)
            await self._global_limiter.acquire()
        else:
            # 按群限速
            await self.limiters[group_id].acquire()

