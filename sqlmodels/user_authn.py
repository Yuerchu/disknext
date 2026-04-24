from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str32, Str100, Str255, Text5K

if TYPE_CHECKING:
    from .user import User


# ==================== DTO 模型 ====================

class AuthnFinishRequest(SQLModelBase):
    """WebAuthn 注册完成请求 DTO"""

    credential: str = Field(min_length=1, max_length=5000)
    """前端 navigator.credentials.create() 返回的 JSON 字符串"""

    name: Str100 | None = None
    """用户自定义的凭证名称"""


class AuthnDetailResponse(SQLModelBase):
    """WebAuthn 凭证详情响应 DTO"""

    id: int
    """凭证数据库 ID"""

    credential_id: Str255
    """凭�� ID（Base64URL 编码）"""

    name: Str100 | None = None
    """用户自定义的凭证名称"""

    credential_device_type: Str32
    """凭证设备类型"""

    credential_backed_up: bool
    """凭证是否已备份"""

    transports: Str255 | None = None
    """支持的传输方式"""

    created_at: datetime
    """创建时间"""


class AuthnRenameRequest(SQLModelBase):
    """WebAuthn 凭证重命名请求 DTO"""

    name: Str100
    """新的凭证名称"""


# ==================== 数据库模型 ====================

class UserAuthn(SQLModelBase, TableBaseMixin):
    """用户 WebAuthn 凭证模型，与 User 为多对一关系"""

    credential_id: Str255 = Field(unique=True, index=True)
    """凭证 ID，Base64URL 编码"""

    credential_public_key: str = Field(sa_column=Column(Text))
    """凭证公钥，Base64URL 编码"""

    sign_count: int = Field(default=0, ge=0)
    """签名计数器，用于防重放攻击"""

    credential_device_type: Str32
    """凭证设备类型：'single_device' 或 'multi_device'"""

    credential_backed_up: bool = Field(default=False)
    """凭证是否已备份"""

    transports: Str255 | None = None
    """支持的传输方式，逗号分隔，如 'usb,nfc,ble,internal'"""

    name: Str100 | None = None
    """用户自定义的凭证名称，便于识别"""

    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""

    # 关系
    user: "User" = Relationship(back_populates="passkeys")

