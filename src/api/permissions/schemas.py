"""Pydantic request schemas for the permission management REST API."""
from pydantic import BaseModel, Field


class BlacklistUserAddRequest(BaseModel):
    """Add a user to the blacklist."""
    user_id: int = Field(..., description="QQ号")
    reason: str = Field("", description="拉黑原因")


class BlacklistGroupAddRequest(BaseModel):
    """Add a group to the blacklist."""
    group_id: int = Field(..., description="群号")
    reason: str = Field("", description="拉黑原因")


class WhitelistUserAddRequest(BaseModel):
    """Add a user to the whitelist."""
    user_id: int = Field(..., description="QQ号")
    reason: str = Field("", description="加白原因")


class WhitelistGroupAddRequest(BaseModel):
    """Add a group to the whitelist."""
    group_id: int = Field(..., description="群号")
    reason: str = Field("", description="加白原因")


class GroupCreateRequest(BaseModel):
    """Create a permission group (role)."""
    name: str = Field(..., min_length=1, max_length=100, description="权限组标识名（英文）")
    display_name: str = Field("", max_length=200, description="显示名称")
    description: str = Field("", description="描述")


class GroupMemberAddRequest(BaseModel):
    """Add members to a permission group."""
    user_ids: list[int] = Field(..., min_length=1, description="QQ号列表")


class GroupPermAddRequest(BaseModel):
    """Add permission keys to a permission group."""
    perm_keys: list[str] = Field(..., min_length=1, description="权限点key列表")


class BindingCreateRequest(BaseModel):
    """Bind a QQ group to a permission group."""
    qq_group_id: int = Field(..., description="QQ群号")
    permission_group_id: int = Field(..., description="权限组ID")
