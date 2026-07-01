"""
FastAPI dependency injection for JWT authentication.

Provides verify_token — a Depends callable that extracts and validates
the Bearer token from the Authorization header.
"""
from typing import NamedTuple

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.common.jwt_utils import decode_token, is_jti_blacklisted

security = HTTPBearer()


class TokenPayload(NamedTuple):
    """Returned by verify_token dependency.

    Attributes:
        payload: Decoded JWT payload dict (contains sub, jti, exp, etc.)
        token: Raw token string (useful for refresh/logout operations)
    """
    payload: dict
    token: str


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """FastAPI dependency: extracts Bearer token, decodes JWT, checks blacklist.

    Raises:
        HTTPException(401) if token is invalid, expired, or blacklisted.
    """
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
        )
    jti = payload.get("jti", "")
    if is_jti_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已被撤销",
        )
    return TokenPayload(payload=payload, token=token)
