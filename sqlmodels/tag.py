from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str255

if TYPE_CHECKING:
    from .user import User


class TagType(StrEnum):
    """标签类型枚举"""
    MANUAL = "manual"
    """手动标签"""
    AUTOMATIC = "automatic"
    """自动标签"""


class Tag(SQLModelBase, TableBaseMixin):
    """标签模型"""

    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_tag_name_user"),)

    name: Str255
    """标签名称"""

    icon: Str255 | None = None
    """标签图标"""

    color: Str255 | None = None
    """标签颜色"""

    type: TagType = Field(default=TagType.MANUAL)
    """标签类型"""
    expression: str | None = Field(default=None, description="自动标签的匹配表达式")
    
    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""
    
    # 关系
    user: "User" = Relationship(back_populates="tags")