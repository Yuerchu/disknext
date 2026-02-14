"""
认证身份模块

一个用户可拥有多种登录方式（邮箱密码、OAuth、Passkey、Magic Link 等）。
AuthIdentity 表存储每种认证方式的凭证信息。
"""
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin

if TYPE_CHECKING:
    from .user import User


class AuthProviderType(StrEnum):
    """认证提供者类型"""

    EMAIL_PASSWORD = "email_password"
    """邮箱+密码"""

    PHONE_SMS = "phone_sms"
    """手机号+短信验证码（预留）"""

    GITHUB = "github"
    """GitHub OAuth"""

    QQ = "qq"
    """QQ OAuth"""

    PASSKEY = "passkey"
    """Passkey/WebAuthn"""

    MAGIC_LINK = "magic_link"
    """邮箱 Magic Link"""


# ==================== DTO 模型 ====================

class AuthIdentityResponse(SQLModelBase):
    """认证身份响应 DTO（列表展示用）"""

    id: UUID
    """身份UUID"""

    provider: AuthProviderType
    """提供者类型"""

    identifier: str
    """标识符（邮箱/手机号/OAuth openid）"""

    display_name: str | None = None
    """显示名称（OAuth 昵称等）"""

    avatar_url: str | None = None
    """头像 URL"""

    is_primary: bool = False
    """是否主要身份"""

    is_verified: bool = False
    """是否已验证"""


class BindIdentityRequest(SQLModelBase):
    """绑定认证身份请求 DTO"""

    provider: AuthProviderType
    """提供者类型"""

    identifier: str
    """标识符（邮箱/手机号/OAuth code）"""

    credential: str | None = None
    """凭证（密码、验证码等）"""

    redirect_uri: str | None = None
    """OAuth 回调地址"""


# ==================== 数据库模型 ====================

class AuthIdentity(SQLModelBase, UUIDTableBaseMixin):
    """用户认证身份 — 一个用户可以有多种登录方式"""

    __table_args__ = (
        UniqueConstraint("provider", "identifier", name="uq_auth_identity_provider_identifier"),
    )

    provider: AuthProviderType = Field(index=True)
    """提供者类型"""

    identifier: str = Field(max_length=255, index=True)
    """标识符（邮箱/手机号/OAuth openid）"""

    credential: str | None = Field(default=None, max_length=1024)
    """凭证（Argon2 哈希密码 / null）"""

    display_name: str | None = Field(default=None, max_length=100)
    """OAuth 昵称"""

    avatar_url: str | None = Field(default=None, max_length=512)
    """OAuth 头像 URL"""

    extra_data: str | None = None
    """JSON 附加数据（2FA secret、OAuth refresh_token 等）"""

    is_primary: bool = False
    """是否主要身份"""

    is_verified: bool = False
    """是否已验证"""

    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE",
    )
    """所属用户UUID"""

    # 关系
    user: "User" = Relationship(back_populates="auth_identities")

    def to_response(self) -> AuthIdentityResponse:
        """转换为响应 DTO"""
        return AuthIdentityResponse(
            id=self.id,
            provider=self.provider,
            identifier=self.identifier,
            display_name=self.display_name,
            avatar_url=self.avatar_url,
            is_primary=self.is_primary,
            is_verified=self.is_verified,
        )
