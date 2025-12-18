from typing import TYPE_CHECKING

from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship

from .base import TableBase

if TYPE_CHECKING:
    from .user import User


class UserAuthn(TableBase, table=True):
    """用户 WebAuthn 凭证模型，与 User 为多对一关系"""

    credential_id: str = Field(max_length=255, unique=True, index=True)
    """凭证 ID，Base64 编码"""

    credential_public_key: str = Field(sa_column=Column(Text))
    """凭证公钥，Base64 编码"""

    sign_count: int = Field(default=0, ge=0)
    """签名计数器，用于防重放攻击"""

    credential_device_type: str = Field(max_length=32)
    """凭证设备类型：'single_device' 或 'multi_device'"""

    credential_backed_up: bool = Field(default=False)
    """凭证是否已备份"""

    transports: str | None = Field(default=None, max_length=255)
    """支持的传输方式，逗号分隔，如 'usb,nfc,ble,internal'"""

    name: str | None = Field(default=None, max_length=100)
    """用户自定义的凭证名称，便于识别"""

    # 外键
    user_id: int = Field(foreign_key="user.id", index=True)
    """所属用户ID"""

    # 关系
    user: "User" = Relationship(back_populates="authns")
