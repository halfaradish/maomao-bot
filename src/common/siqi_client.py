from dataclasses import dataclass
from typing import Any, Optional

import aiohttp
from nonebot import get_driver, logger

from ..config import SiqiAuthConfig

_BASE_URL = f"http://{SiqiAuthConfig.HOST}:{SiqiAuthConfig.PORT}"
_APP_CODE = SiqiAuthConfig.APP_CODE
_TIMEOUT = SiqiAuthConfig.TIMEOUT
_ENABLED = SiqiAuthConfig.ENABLED

logger.info(f"[siqi_client] 初始化: enabled={_ENABLED}, url={_BASE_URL}, app_code={_APP_CODE}")


@dataclass(slots=True)
class AuthCheckResult:
    allowed: bool
    reason: str = ""
    current_roles: tuple[str, ...] = ()
    suggest_roles: tuple[str, ...] = ()


class SiqiAuthRequestError(RuntimeError):
    pass


def _split_csv(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text:
        return ()
    return tuple(item.strip() for item in text.split(",") if item.strip())


class SiqiClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def enabled(self) -> bool:
        return _ENABLED

    @property
    def base_url(self) -> str:
        return _BASE_URL

    @property
    def port(self) -> int:
        return SiqiAuthConfig.PORT

    def _build_check_payload(self, perm_key: str, user_id: str, app_code: Optional[str] = None) -> dict[str, str]:
        return {
            "app_code": app_code or _APP_CODE,
            "user_id": str(user_id),
            "perm_key": perm_key,
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,
                keepalive_timeout=60,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(
                total=None,
                connect=_TIMEOUT,
                sock_connect=_TIMEOUT,
                sock_read=_TIMEOUT,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )
            logger.info("[siqi_client] 连接池已创建 (limit=10, keepalive=60s)")
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("[siqi_client] 连接池已关闭")

    async def _request_check(
        self,
        perm_key: str,
        user_id: str,
        app_code: Optional[str] = None,
    ) -> dict[str, Any]:
        url = f"{_BASE_URL}/AuthService/Check"
        payload = self._build_check_payload(perm_key, user_id, app_code)
        session = await self._get_session()
        try:
            async with session.post(url, json=payload) as resp:
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
        except Exception as e:
            raise SiqiAuthRequestError(f"{type(e).__name__}: {e}") from e

        if not isinstance(data, dict):
            raise SiqiAuthRequestError(f"invalid siqi auth response type: {type(data).__name__}")

        return data

    @staticmethod
    def _parse_check_result(data: dict[str, Any]) -> AuthCheckResult:
        return AuthCheckResult(
            allowed=bool(data.get("allowed", False)),
            reason=str(data.get("reason") or ""),
            current_roles=_split_csv(data.get("current_roles", "")),
            suggest_roles=_split_csv(data.get("suggest_roles", "")),
        )

    async def check_detail(self, perm_key: str, user_id: str, app_code: str | None = None) -> AuthCheckResult:
        payload = self._build_check_payload(perm_key, user_id, app_code)
        data = await self._request_check(perm_key, user_id, app_code)

        result = self._parse_check_result(data)
        logger.info(
            f"[siqi_client] Check {payload['app_code']}/{user_id}/{perm_key} "
            f"→ allowed={result.allowed}, reason={result.reason!r}, "
            f"current_roles={result.current_roles}, suggest_roles={result.suggest_roles}"
        )
        return result

    async def check(self, perm_key: str, user_id: str, app_code: str | None = None) -> bool:
        return (await self.check_detail(perm_key, user_id, app_code)).allowed


siqi_client = SiqiClient()

_driver = get_driver()


@_driver.on_shutdown
async def _shutdown_siqi_client():
    await siqi_client.close()
