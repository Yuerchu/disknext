
from typing import TYPE_CHECKING
from datetime import datetime
from uuid import UUID

from sqlmodel import Field, Relationship, Column, func, DateTime

from .base import SQLModelBase
from .mixin import TableBaseMixin

if TYPE_CHECKING:
    from .user import User

class StoragePack(SQLModelBase, TableBaseMixin):
    """容量包模型"""

    name: str = Field(max_length=255, description="容量包名称")
    active_time: datetime | None = Field(default=None, description="激活时间")
    expired_time: datetime | None = Field(default=None, index=True, description="过期时间")
    size: int = Field(description="容量包大小（字节）")
    
    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""
    
    # 关系
    user: "User" = Relationship(back_populates="storage_packs")