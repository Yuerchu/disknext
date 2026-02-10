"""
InfoResponse DTO Mixin模块

提供用于InfoResponse类型DTO的Mixin，统一定义id/created_at/updated_at字段。

设计说明：
- 这些Mixin用于**响应DTO**，不是数据库表
- 从数据库返回时这些字段永远不为空，所以定义为必填字段
- TableBase中的id=None和default_factory=now是正确的（入库前为None，数据库生成）
- 这些Mixin让DTO明确表示"返回给客户端时这些字段必定有值"
"""
from datetime import datetime
from uuid import UUID

from sqlmodels.base import SQLModelBase


class IntIdInfoMixin(SQLModelBase):
    """整数ID响应mixin - 用于InfoResponse DTO"""
    id: int
    """记录ID"""


class UUIDIdInfoMixin(SQLModelBase):
    """UUID ID响应mixin - 用于InfoResponse DTO"""
    id: UUID
    """记录ID"""


class DatetimeInfoMixin(SQLModelBase):
    """时间戳响应mixin - 用于InfoResponse DTO"""
    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """更新时间"""


class IntIdDatetimeInfoMixin(IntIdInfoMixin, DatetimeInfoMixin):
    """整数ID + 时间戳响应mixin"""
    pass


class UUIDIdDatetimeInfoMixin(UUIDIdInfoMixin, DatetimeInfoMixin):
    """UUID ID + 时间戳响应mixin"""
    pass
