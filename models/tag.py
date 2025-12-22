from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID
from datetime import datetime

from sqlmodel import Field, Relationship, UniqueConstraint, Column, func, DateTime

from .base import SQLModelBase
from .mixin import TableBaseMixin

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

    name: str = Field(max_length=255)
    """标签名称"""

    icon: str | None = Field(default=None, max_length=255)
    """标签图标"""

    color: str | None = Field(default=None, max_length=255)
    """标签颜色"""

    type: TagType = Field(default=TagType.MANUAL, sa_column_kwargs={"server_default": "'manual'"})
    """标签类型"""
    expression: str | None = Field(default=None, description="自动标签的匹配表达式")
    
    # 外键
    user_id: UUID = Field(foreign_key="user.id", index=True, description="所属用户UUID")
    
    # 关系
    user: "User" = Relationship(back_populates="tags")