
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, Index

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str255

if TYPE_CHECKING:
    from .object import Object


class SourceLink(SQLModelBase, TableBaseMixin):
    """链接模型"""

    __table_args__ = (
        Index("ix_sourcelink_object_name", "object_id", "name"),
    )

    name: Str255
    """链接名称"""

    downloads: int = 0
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