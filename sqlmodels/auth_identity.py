"""
认证类型定义

定义用户认证方式的枚举和通用认证 DTO。
"""
from enum import StrEnum

from sqlmodel import Field

from sqlmodel_ext import SQLModelBase, Str128


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


class ChangePasswordRequest(SQLModelBase):
    """修改密码请求 DTO"""

    old_password: Str128 = Field(min_length=8)
    """当前密码"""

    new_password: Str128 = Field(min_length=8)
    """新密码（至少 8 位）"""
