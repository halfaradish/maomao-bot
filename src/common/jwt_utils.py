"""
JWT token utilities for WebUI authentication.

Uses python-jose (cryptography backend) for token creation/validation
and perm_cache for blacklist storage.
"""
import hashlib
import os
import time
import uuid
from typing import Optional

from jose import jwt as jose_jwt, JWTError

from src.config.local_config import WebUIConfig
from src.common.permission.cache import perm_cache

# Resolve secret: prefer env var, otherwise generate a deterministic-once secret
_JWT_SECRET = WebUIConfig.WEBUI_JWT_SECRET or hashlib.sha256(os.urandom(32)).hexdigest()
_JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_SECONDS = 86400  # 24 hours

__all__ = [
    "create_token",
    "decode_token",
    "blacklist_token",
    "is_jti_blacklisted",
    "get_token_expiry",
]


def create_token(qq_number: str) -> dict:
    """Create a JWT access token for the given QQ number.

    Returns:
        dict with keys: token (str), expires_in (int), jti (str)
    """
    now = int(time.time())
    jti = str(uuid.uuid4())
    payload = {
        "sub": qq_number,
        "iat": now,
        "exp": now + _ACCESS_TOKEN_EXPIRE_SECONDS,
        "type": "access",
        "jti": jti,
    }
    token = jose_jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)
    return {
        "token": token,
        "expires_in": _ACCESS_TOKEN_EXPIRE_SECONDS,
        "jti": jti,
    }


def decode_token(token: str) -> Optional[dict]:
    """Validate and decode a JWT token.

    Returns:
        The payload dict if valid, None if expired or malformed.
    """
    try:
        payload = jose_jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def blacklist_token(token: str) -> None:
    """Add a token's JTI to the blacklist so it cannot be reused.

    TTL is set to match the token's remaining lifetime so the entry
    self-cleans when the token would have expired anyway.
    """
    payload = decode_token(token)
    if payload is None or "jti" not in payload:
        return
    jti = payload["jti"]
    # Calculate remaining TTL — cap at max token lifetime
    now = int(time.time())
    exp = payload.get("exp", now + _ACCESS_TOKEN_EXPIRE_SECONDS)
    remaining_ttl = max(1, exp - now)
    perm_cache.set(f"webui:token_blacklist:{jti}", True, remaining_ttl)


def is_jti_blacklisted(jti: str) -> bool:
    """Check whether a JWT ID has been blacklisted."""
    return perm_cache.get(f"webui:token_blacklist:{jti}") is not None


def get_token_expiry() -> int:
    """Return the access token expiry duration in seconds."""
    return _ACCESS_TOKEN_EXPIRE_SECONDS
