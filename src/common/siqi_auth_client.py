"""
司契权限系统 HTTP 客户端

通过 HTTP 调用 Auth Server / Auth Agent 的 AuthService/Check 接口进行权限检查。
支持故障降级、开关控制。
使用持久化连接池复用 TCP 连接，避免每次请求重新握手。

使用方式:
    from ..common.siqi_auth_client import siqi_auth

    allowed, reason = await siqi_auth.check("member:ban", user_id="123456")
"""

import random
import time
from typing import Any, List, Optional, Tuple

import aiohttp
from nonebot import get_driver, logger

from ..config import SiqiAuthConfig

# 从配置读取参数
_BASE_URL = f"http://{SiqiAuthConfig.HOST}:{SiqiAuthConfig.PORT}"
_APP_CODE = SiqiAuthConfig.APP_CODE
_TIMEOUT = SiqiAuthConfig.TIMEOUT
_ENABLED = SiqiAuthConfig.ENABLED

logger.info(f"[siqi_auth] 初始化: enabled={_ENABLED}, url={_BASE_URL}, app_code={_APP_CODE}")


class SiqiAuthClient:
    """司契权限系统客户端（带连接池复用）"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    def _build_check_payload(self, perm_key: str, user_id: str, app_code: Optional[str] = None) -> dict[str, str]:
        return {
            "app_code": app_code or _APP_CODE,
            "user_id": str(user_id),
            "perm_key": perm_key,
        }

    async def _request_check(self, perm_key: str, user_id: str, app_code: Optional[str] = None) -> Tuple[dict[str, Any], float]:
        url = f"{_BASE_URL}/AuthService/Check"
        payload = self._build_check_payload(perm_key, user_id, app_code)
        session = await self._get_session()
        start_time = time.perf_counter()
        async with session.post(url, json=payload) as resp:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if resp.status >= 400:
                text = await resp.text()
                raise aiohttp.ClientResponseError(
                    request_info=resp.request_info,
                    history=resp.history,
                    status=resp.status,
                    message=text[:500],
                    headers=resp.headers,
                )
            data = await resp.json(content_type=None)
            if not isinstance(data, dict):
                raise ValueError(f"invalid siqi auth response type: {type(data).__name__}")
            return data, elapsed_ms

    @staticmethod
    def _parse_check_result(data: dict[str, Any]) -> Tuple[bool, str]:
        allowed = bool(data.get("allowed", False))
        reason = str(data.get("reason") or "")
        return allowed, reason

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        懒初始化并复用 ClientSession。
        内置 TCP 连接池 + HTTP Keep-Alive，避免每次请求重建 TCP 连接。
        """
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,              # 最大并发连接数（对 auth_server 而言足够）
                keepalive_timeout=60,  # Keep-Alive 保持 60 秒
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=_TIMEOUT),
            )
            logger.info("[siqi_auth] 连接池已创建 (limit=10, keepalive=60s)")
        return self._session

    async def close(self):
        """关闭连接池，释放所有 TCP 连接（NoneBot shutdown 时调用）"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("[siqi_auth] 连接池已关闭")

    @property
    def enabled(self) -> bool:
        """权限系统是否启用"""
        return _ENABLED

    @property
    def base_url(self) -> str:
        return _BASE_URL

    @property
    def port(self) -> int:
        return SiqiAuthConfig.PORT

    async def check(self, perm_key: str, user_id: str, app_code: str = None) -> Tuple[bool, str]:
        """
        检查用户是否拥有某个权限

        Args:
            perm_key: 权限标识，如 "member:ban"
            user_id:  用户ID，如 QQ号 "123456"
            app_code: 应用代码，默认使用配置中的 qq_bot

        Returns:
            (allowed, reason) 元组
        """
        payload = self._build_check_payload(perm_key, user_id, app_code)
        try:
            data, _ = await self._request_check(perm_key, user_id, app_code)
            allowed, reason = self._parse_check_result(data)

            logger.info(
                f"[siqi_auth] Check {payload['app_code']}/{user_id}/{perm_key} "
                f"→ allowed={allowed}, reason={reason!r}, raw_response={data}"
            )
            return allowed, reason
        except aiohttp.ClientError as e:
            logger.error(
                f"[siqi_auth] 网络错误: {type(e).__name__}: {e}"
            )
            return False, "权限系统网络错误"
        except Exception as e:
            logger.error(
                f"[siqi_auth] 权限检查异常: {type(e).__name__}: {e}"
            )
            return False, "权限系统异常"

    async def check_user_permission(
        self, user_id: str, perm_key: str, app_code: Optional[str] = None
    ) -> Tuple[bool, str]:
        return await self.check(perm_key, str(user_id), app_code)

    async def check_with_latency(
        self, perm_key: str, user_id: str, app_code: str = None
    ) -> Tuple[bool, float]:
        """
        带延迟测量的权限检查

        Returns:
            (allowed, latency_ms) 元组
        """
        payload = self._build_check_payload(perm_key, user_id, app_code)
        try:
            data, elapsed_ms = await self._request_check(perm_key, user_id, app_code)
            allowed, _ = self._parse_check_result(data)

            logger.info(
                f"[siqi_auth] Check {payload['app_code']}/{user_id}/{perm_key} "
                f"→ allowed={allowed}, latency={elapsed_ms:.2f}ms, "
                f"raw_response={data}"
            )
            return allowed, elapsed_ms

        except aiohttp.ClientError as e:
            logger.error(
                f"[siqi_auth] 网络错误: {type(e).__name__}: {e}"
            )
            return False, 0.0
        except Exception as e:
            logger.error(
                f"[siqi_auth] 权限检查异常: {type(e).__name__}: {e}"
            )
            return False, 0.0

    @staticmethod
    def _compute_stats(latencies: List[float], rounds: int, last_allowed: bool, fail_count: int) -> dict:
        """从延迟列表计算统计数据"""
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)
        return {
            "rounds": rounds,
            "avg_ms": sum(latencies) / n,
            "min_ms": latencies_sorted[0],
            "max_ms": latencies_sorted[-1],
            "p50_ms": latencies_sorted[n // 2],
            "p99_ms": latencies_sorted[int(n * 0.99)],
            "last_allowed": last_allowed,
            "success_count": rounds - fail_count,
            "fail_count": fail_count,
            "latencies": latencies,
        }

    async def batch_check_latency(
        self, perm_key: str, user_id: str, rounds: int = 10
    ) -> dict:
        """
        批量延迟测试（固定 user_id，首次 miss 后全部命中缓存）
        """
        latencies = []
        last_allowed = False
        fail_count = 0

        for _ in range(rounds):
            allowed, ms = await self.check_with_latency(perm_key, user_id)
            latencies.append(ms)
            last_allowed = allowed
            if ms >= _TIMEOUT * 1000:
                fail_count += 1

        return self._compute_stats(latencies, rounds, last_allowed, fail_count)

    async def batch_check_latency_nocache(
        self, perm_key: str, rounds: int = 10
    ) -> dict:
        """
        缓存未命中延迟测试：每次使用不同的随机 user_id，强制 cache miss。

        原理: auth_server 的缓存 key 为 app_code:user_id，
              使用不同 user_id 每次都会触发数据库查询。

        注意: 随机 user_id 在数据库中不存在，测的是「用户不存在」的 DB 查询路径，
              结果均为 denied，但延迟能真实反映 DB 往返耗时。
        """
        latencies = []
        fail_count = 0

        for _ in range(rounds):
            # 生成随机 user_id，确保不会命中已有缓存
            rand_uid = str(random.randint(10_0000_0000, 99_9999_9999))
            _, ms = await self.check_with_latency(perm_key, rand_uid)
            latencies.append(ms)
            if ms >= _TIMEOUT * 1000:
                fail_count += 1

        return self._compute_stats(latencies, rounds, False, fail_count)


# 全局单例
siqi_auth = SiqiAuthClient()

# 注册 NoneBot shutdown 钩子，优雅关闭连接池
_driver = get_driver()


@_driver.on_shutdown
async def _shutdown_siqi_auth():
    await siqi_auth.close()
