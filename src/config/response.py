from pydantic import BaseModel
from typing import Optional, Any, Dict
from fastapi import Request
from datetime import datetime

# HTTP 状态码常量 (按业务常用顺序排列)
SUCCESS = 200
CREATED = 201
NO_CONTENT = 204
BAD_REQUEST = 400
UNAUTHORIZED = 401
FORBIDDEN = 403
NOT_FOUND = 404
METHOD_NOT_ALLOWED = 405
INTERNAL_SERVER_ERROR = 500
BAD_GATEWAY = 502
SERVICE_UNAVAILABLE = 503
GATEWAY_TIMEOUT = 504

# 状态码对应的默认消息 (中文)
DEFAULT_MESSAGES: Dict[int, str] = {
    SUCCESS: "成功",
    CREATED: "已创建",
    NO_CONTENT: "无内容",
    BAD_REQUEST: "请求参数错误",
    UNAUTHORIZED: "未授权",
    FORBIDDEN: "禁止访问",
    NOT_FOUND: "资源未找到",
    METHOD_NOT_ALLOWED: "方法不被允许",
    INTERNAL_SERVER_ERROR: "服务器内部错误",
    BAD_GATEWAY: "网关错误",
    SERVICE_UNAVAILABLE: "服务不可用",
    GATEWAY_TIMEOUT: "网关超时",
}

# 业务自定义状态码 (可扩展)
BUSINESS_ERRORS = {
    1001: "用户未登录",
    1002: "权限不足",
    1003: "重复操作",
}

class APIResponse(BaseModel):
    status: str          # e.g., "success", "error"
    code: int            # HTTP or custom business code
    message: str         # Human-readable message
    data: Optional[Any] = None   # Actual payload
    timestamp: str       # ISO8601 format
    path: str            # Requested URL path


def build_response(
   *,
    status: str,
    code: int,
    message: str,
    data: Any = None,
    request: Request
):
    return APIResponse(
        status=status,
        code=code,
        message=message,
        data=data,
        timestamp=datetime.now().isoformat() + "Z",
        path=(request.url.path)
    )

def success(
    code: int = SUCCESS,
    message: str = None,
    data: Any = None,
    request: Request = None
):
    """
    成功响应 (自动填充状态/消息)
    
    自动填入：
        status="success"
        code=200
        message=成功

    默认只需填入：
        data
        request
    """
    msg = message or DEFAULT_MESSAGES.get(code, "成功")
    return build_response(
        status="success",
        code=code,
        message=msg,
        data=data,
        request=request
    )

def error(
    code: str = BAD_REQUEST,
    message: str = None,
    data: Any = None,
    request: Request = None
):
    """
    错误响应 (自动填充状态/消息)
    
    自动填入：
        status="error"
        code=400
        message=失败

    默认只需填入：
        data
        request
    """
    msg = message or BUSINESS_ERRORS.get(code, DEFAULT_MESSAGES.get(code, f"错误代码: {code}"))
    return build_response(
        status="error",
        code=code,
        message=msg,
        data=data,
        request=request
    )