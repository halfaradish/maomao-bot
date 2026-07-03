"""
Authentication API endpoints for the WebUI management panel.

Provides login (QQ number + temp password → JWT), refresh, and logout.
"""
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from src.common.permission.cache import perm_cache
from src.common.jwt_utils import (
    create_token,
    decode_token,
    blacklist_token,
    get_token_expiry,
)
from src.config.local_config import WebUIConfig
from src.config.response import success, error
from src.api.deps import verify_token, TokenPayload

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BRUTE_FORCE_MAX_ATTEMPTS = 3
BRUTE_FORCE_TTL = 60        # seconds
TEMP_PASSWORD_TTL = 300     # 5 minutes

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["认证"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    qq_number: str
    temp_password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int


# ---------------------------------------------------------------------------
# Brute-force helpers
# ---------------------------------------------------------------------------


def _attempts_key(qq: str) -> str:
    return f"webui:login_attempts:{qq}"


def _check_brute_force(qq_number: str) -> bool:
    """Return True if login is allowed, False if throttled."""
    attempts = perm_cache.get(_attempts_key(qq_number))
    return not (attempts is not None and attempts >= BRUTE_FORCE_MAX_ATTEMPTS)


def _record_failed_attempt(qq_number: str) -> None:
    """Increment the failed-login counter for the given QQ."""
    key = _attempts_key(qq_number)
    count = perm_cache.get(key) or 0
    perm_cache.set(key, count + 1, BRUTE_FORCE_TTL)


def _clear_brute_force(qq_number: str) -> None:
    """Reset the failed-login counter after a successful login."""
    perm_cache.delete(_attempts_key(qq_number))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", summary="验证临时密码并获取JWT令牌")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
):
    """Exchange a QQ number + temporary password for a JWT access token.

    The temporary password is obtained from the QQ bot via ``权限 登录``
    and is valid for one use within 5 minutes.
    """
    # 1. Brute force check
    if not _check_brute_force(body.qq_number):
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        return error(
            code=status.HTTP_429_TOO_MANY_REQUESTS,
            message="登录尝试过于频繁，请60秒后再试",
            request=request,
        )

    # 2. Validate temp password
    cache_key = f"webui:temp_pwd:{body.qq_number}"
    expected = perm_cache.get(cache_key)

    is_dev_login = False
    if expected is None and WebUIConfig.WEBUI_DEV_PASSWORD:
        # Dev bypass: accept dev password for superusers only.
        # Hard gate: NEVER allow dev bypass in production.
        from src.config.local_config import environment
        if environment != 'prod':
            from nonebot import get_driver
            superusers = {str(uid) for uid in get_driver().config.superusers}
            if (
                body.qq_number in superusers
                and body.temp_password == WebUIConfig.WEBUI_DEV_PASSWORD
            ):
                is_dev_login = True

    if not is_dev_login and (expected is None or body.temp_password != expected):
        _record_failed_attempt(body.qq_number)
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return error(
            code=status.HTTP_401_UNAUTHORIZED,
            message="临时密码无效或已过期",
            request=request,
        )

    # 3. One-time use: delete immediately (skip for dev login — it's reusable)
    if not is_dev_login:
        perm_cache.delete(cache_key)
    _clear_brute_force(body.qq_number)

    # 4. Issue JWT
    token_result = create_token(body.qq_number)
    return success(
        data={
            "token": token_result["token"],
            "expires_in": token_result["expires_in"],
        },
        request=request,
    )


@router.post("/refresh", summary="刷新JWT令牌（旧令牌立即失效）")
async def refresh_token(
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """Issue a new JWT token and blacklist the old one.

    Requires a valid (non-expired, non-blacklisted) Bearer token.
    """
    # Blacklist old token
    blacklist_token(auth.token)

    # Issue new token
    qq_number = auth.payload["sub"]
    token_result = create_token(qq_number)
    return success(
        data={
            "token": token_result["token"],
            "expires_in": token_result["expires_in"],
        },
        request=request,
    )


@router.post("/logout", summary="撤销当前JWT令牌")
async def logout(
    auth: TokenPayload = Depends(verify_token),
    request: Request = None,
):
    """Blacklist the current JWT token so it can no longer be used.

    Requires a valid Bearer token.
    """
    blacklist_token(auth.token)
    return success(message="已成功退出登录", request=request)
