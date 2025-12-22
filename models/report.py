from enum import StrEnum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from .base import SQLModelBase
from .mixin import TableBaseMixin

if TYPE_CHECKING:
    from .share import Share


class ReportReason(StrEnum):
    """举报原因枚举"""
    # [TODO] 补充具体举报原因
    pass


class Report(SQLModelBase, TableBaseMixin):
    """举报模型"""

    reason: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """举报原因 [TODO] 待定义枚举"""
    description: str | None = Field(default=None, max_length=255, description="补充描述")
    
    # 外键
    share_id: int = Field(foreign_key="share.id", index=True, description="被举报的分享ID")
    
    # 关系
    share: "Share" = Relationship(back_populates="reports")