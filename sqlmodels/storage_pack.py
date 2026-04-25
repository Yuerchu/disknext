from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, NonNegativeBigInt, Str255

if TYPE_CHECKING:
    from .user import User


# ==================== DTO 模型 ====================

class StoragePackResponse(SQLModelBase):
    """容量包响应 DTO"""

    id: UUID
    """容量包ID"""

    name: str
    """容量包名称"""

    size: int
    """容量大小（字节）"""

    active_time: datetime | None = None
    """激活时间"""

    expired_time: datetime | None = None
    """过期时间"""

    product_id: UUID | None = None
    """来源商品UUID"""


# ==================== 数据库模型 ====================

class StoragePack(SQLModelBase, UUIDTableBaseMixin):
    """容量包模型"""

    name: Str255
    """容量包名称"""

    active_time: datetime | None = None
    """激活时间"""

    expired_time: datetime | None = Field(default=None, index=True)
    """过期时间"""

    size: NonNegativeBigInt
    """容量包大小（字节）"""

    product_id: UUID | None = Field(default=None, foreign_key="product.id", ondelete="SET NULL")
    """来源商品UUID"""

    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""

    # 关系
    user: "User" = Relationship(back_populates="storage_packs")

