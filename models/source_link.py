
from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, Index
from .base import TableBase

if TYPE_CHECKING:
    from .object import Object


class SourceLink(TableBase, table=True):
    """链接模型"""

    __table_args__ = (
        Index("ix_sourcelink_object_name", "object_id", "name"),
    )

    name: str = Field(max_length=255)
    """链接名称"""

    downloads: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """通过此链接的下载次数"""

    # 外键
    object_id: int = Field(foreign_key="object.id", index=True)
    """关联的对象ID（必须是文件类型）"""

    # 关系
    object: "Object" = Relationship(back_populates="source_links")
    """关联的对象"""