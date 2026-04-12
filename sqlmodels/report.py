from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str255

if TYPE_CHECKING:
    from .share import Share


class ReportReason(StrEnum):
    """举报原因枚举"""
    # [TODO] 补充具体举报原因
    pass


class Report(SQLModelBase, TableBaseMixin):
    """举报模型"""

    reason: int = 0
    """举报原因 [TODO] 待定义枚举"""

    description: Str255 | None = None
    """补充描述"""
    
    # 外键
    share_id: UUID = Field(
        foreign_key="share.id",
        index=True,
        ondelete="CASCADE"
    )
    """被举报的分享ID"""
    
    # 关系
    share: "Share" = Relationship(back_populates="reports")