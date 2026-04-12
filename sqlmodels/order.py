from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Numeric
from sqlmodel import Field, Relationship

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str64, Str255

if TYPE_CHECKING:
    from .product import Product
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

    STORAGE_PACK = "storage_pack"
    """容量包"""

    GROUP_TIME = "group_time"
    """用户组时长"""

    SCORE = "score"
    """积分充值"""


# ==================== DTO 模型 ====================

class CreateOrderRequest(SQLModelBase):
    """创建订单请求 DTO"""

    product_id: UUID
    """商品UUID"""

    num: int = Field(default=1, ge=1)
    """购买数量"""

    method: str = Field(min_length=1, max_length=64)
    """支付方式"""


class OrderResponse(SQLModelBase):
    """订单响应 DTO"""

    id: int
    """订单ID"""

    order_no: Str255
    """订单号"""

    type: OrderType
    """订单类型"""

    method: Str64 | None = None
    """支付方式"""

    product_id: UUID | None = None
    """商品UUID"""

    num: int
    """购买数量"""

    name: Str255
    """商品名称"""

    price: float
    """订单价格（元）"""

    status: OrderStatus
    """订单状态"""

    user_id: UUID
    """所属用户UUID"""


# ==================== 数据库模型 ====================

class Order(SQLModelBase, TableBaseMixin):
    """订单模型"""

    order_no: Str255 = Field(unique=True, index=True)
    """订单号，唯一"""

    type: OrderType
    """订单类型"""

    method: Str255 | None = None
    """支付方式"""

    product_id: UUID | None = Field(default=None, foreign_key="product.id", ondelete="SET NULL")
    """关联商品UUID"""

    num: int = Field(default=1, sa_column_kwargs={"server_default": "1"})
    """购买数量"""

    name: Str255
    """商品名称"""

    price: Decimal = Field(sa_type=Numeric(12, 2), default=Decimal("0.00"))
    """订单价格（元）"""

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
    product: "Product" = Relationship(back_populates="orders")

    def to_response(self) -> OrderResponse:
        """转换为响应 DTO"""
        return OrderResponse(
            id=self.id,
            order_no=self.order_no,
            type=self.type,
            method=self.method,
            product_id=self.product_id,
            num=self.num,
            name=self.name,
            price=float(self.price),
            status=self.status,
            user_id=self.user_id,
        )
