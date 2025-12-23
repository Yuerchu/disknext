
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, Index

from .base import SQLModelBase
from .mixin import TableBaseMixin

if TYPE_CHECKING:
    from .object import Object


class SourceLink(SQLModelBase, TableBaseMixin):
    """链接模型"""

    __table_args__ = (
        Index("ix_sourcelink_object_name", "object_id", "name"),
    )

    name: str = Field(max_length=255)
    """链接名称"""

    downloads: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """通过此链接的下载次数"""

    # 外键
    object_id: UUID = Field(
        foreign_key="object.id",
        index=True,
        ondelete="CASCADE"
    )
    """关联的对象UUID（必须是文件类型）"""

    # 关系
    object: "Object" = Relationship(back_populates="source_links")
    """关联的对象"""