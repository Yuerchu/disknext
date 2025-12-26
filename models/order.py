from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship

from .base import SQLModelBase
from .mixin import TableBaseMixin

if TYPE_CHECKING:
    from .user import User


class OrderStatus(StrEnum):
    """订单状态枚举"""
    PENDING = "pending"
    """待支付"""
    COMPLETED = "completed"
    """已完成"""
    CANCELLED = "cancelled"
    """已取消"""


class OrderType(StrEnum):
    """订单类型枚举"""
    # [TODO] 补充具体订单类型
    pass


class Order(SQLModelBase, TableBaseMixin):
    """订单模型"""

    order_no: str = Field(max_length=255, unique=True, index=True)
    """订单号，唯一"""

    type: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """订单类型 [TODO] 待定义枚举"""

    method: str | None = Field(default=None, max_length=255)
    """支付方式"""

    product_id: int | None = Field(default=None)
    """商品ID"""

    num: int = Field(default=1, sa_column_kwargs={"server_default": "1"})
    """购买数量"""

    name: str = Field(max_length=255)
    """商品名称"""

    price: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """订单价格（分）"""

    status: OrderStatus = Field(default=OrderStatus.PENDING)
    """订单状态"""
    
    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""
    
    # 关系
    user: "User" = Relationship(back_populates="orders")