
from typing import TYPE_CHECKING
from datetime import datetime
from uuid import UUID

from sqlmodel import Field, Relationship, text, UniqueConstraint, Index

from .base import SQLModelBase
from .mixin import TableBaseMixin

if TYPE_CHECKING:
    from .user import User
    from .report import Report
    from .object import Object


class Share(SQLModelBase, TableBaseMixin):
    """分享模型"""

    __table_args__ = (
        UniqueConstraint("code", name="uq_share_code"),
        Index("ix_share_source_name", "source_name"),
        Index("ix_share_user_created", "user_id", "created_at"),
        Index("ix_share_object", "object_id"),
    )

    code: str = Field(max_length=64, nullable=False, index=True)
    """分享码"""

    password: str | None = Field(default=None, max_length=255)
    """分享密码（加密后）"""

    object_id: UUID = Field(foreign_key="object.id", index=True)
    """关联的对象UUID"""

    views: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """浏览次数"""

    downloads: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """下载次数"""

    remain_downloads: int | None = Field(default=None)
    """剩余下载次数 (NULL为不限制)"""

    expires: datetime | None = Field(default=None)
    """过期时间 (NULL为永不过期)"""

    preview_enabled: bool = Field(default=True, sa_column_kwargs={"server_default": text("true")})
    """是否允许预览"""

    source_name: str | None = Field(default=None, max_length=255)
    """源名称（冗余字段，便于展示）"""

    score: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """兑换此分享所需的积分"""

    # 外键
    user_id: UUID = Field(foreign_key="user.id", index=True)
    """创建分享的用户UUID"""

    # 关系
    user: "User" = Relationship(back_populates="shares")
    """分享创建者"""

    object: "Object" = Relationship(back_populates="shares")
    """关联的对象"""

    reports: list["Report"] = Relationship(back_populates="share")
    """举报列表"""

    @property
    def is_dir(self) -> bool:
        """是否为目录分享（向后兼容属性）"""
        from .object import ObjectType
        return self.object.type == ObjectType.FOLDER if self.object else False
