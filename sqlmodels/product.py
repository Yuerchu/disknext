from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Numeric
from sqlmodel import Field, Relationship

from sqlmodel_ext import SQLModelBase, Str2048, UUIDTableBaseMixin, NonNegativeBigInt, Str255, NonNegativeInt, PositiveBigInt

if TYPE_CHECKING:
    from .order import Order
    from .redeem import Redeem


class ProductType(StrEnum):
    """商品类型枚举"""

    STORAGE_PACK = "storage_pack"
    """容量包"""

    GROUP_TIME = "group_time"
    """用户组时长"""

    SCORE = "score"
    """积分充值"""


class PaymentMethod(StrEnum):
    """支付方式枚举"""

    ALIPAY = "alipay"
    """支付宝"""

    WECHAT = "wechat"
    """微信支付"""

    STRIPE = "stripe"
    """Stripe"""

    EASYPAY = "easypay"
    """易支付"""

    CUSTOM = "custom"
    """自定义支付"""


# ==================== DTO 模型 ====================

class ProductBase(SQLModelBase):
    """商品基础字段"""

    name: Str255
    """商品名称"""

    type: ProductType
    """商品类型"""

    description: str | None = Field(default=None, max_length=1000)
    """商品描述"""


class ProductCreateRequest(ProductBase):
    """创建商品请求 DTO"""

    name: Str255
    """商品名称"""

    price: Decimal = Field(ge=0, decimal_places=2)
    """商品价格（元）"""

    is_active: bool = True
    """是否上架"""

    sort_order: NonNegativeInt
    """排序权重（越大越靠前）"""

    # storage_pack 专用
    size: NonNegativeInt | None = None
    """容量大小（字节），type=storage_pack 时必填"""

    duration_days: NonNegativeInt | None = None
    """有效天数，type=storage_pack/group_time 时必填"""

    # group_time 专用
    group_id: UUID | None = None
    """目标用户组UUID，type=group_time 时必填"""

    # score 专用
    score_amount: PositiveBigInt | None = None
    """积分数量，type=score 时必填"""


class ProductUpdateRequest(SQLModelBase):
    """更新商品请求 DTO（所有字段可选）"""

    name: Str255 | None = None
    """商品名称"""

    description: Str2048 | None = None
    """商品描述"""

    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    """商品价格（元）"""

    is_active: bool | None = None
    """是否上架"""

    sort_order: NonNegativeInt | None = None
    """排序权重"""

    size: NonNegativeInt | None = None
    """容量大小（字节）"""

    duration_days: NonNegativeInt | None = None
    """有效天数"""

    group_id: UUID | None = None
    """目标用户组UUID"""

    score_amount: PositiveBigInt | None = None
    """积分数量"""


class ProductResponse(ProductBase):
    """商品响应 DTO"""

    id: UUID
    """商品UUID"""

    price: float
    """商品价格（元）"""

    is_active: bool
    """是否上架"""

    sort_order: int
    """排序权重"""

    size: int | None = None
    """容量大小（字节）"""

    duration_days: int | None = None
    """有效天数"""

    group_id: UUID | None = None
    """目标用户组UUID"""

    score_amount: int | None = None
    """积分数量"""


# ==================== 数据库模型 ====================

class Product(ProductBase, UUIDTableBaseMixin):
    """商品模型"""

    name: Str255
    """商品名称"""

    price: Decimal = Field(sa_type=Numeric(12, 2), default=Decimal("0.00"))
    """商品价格（元）"""

    is_active: bool = True
    """是否上架"""

    sort_order: NonNegativeInt
    """排序权重（越大越靠前）"""

    # storage_pack 专用
    size: NonNegativeBigInt | None = None
    """容量大小（字节），type=storage_pack 时必填"""

    duration_days: NonNegativeInt | None = None
    """有效天数，type=storage_pack/group_time 时必填"""

    # group_time 专用
    group_id: UUID | None = Field(default=None, foreign_key="group.id", ondelete="SET NULL")
    """目标用户组UUID，type=group_time 时必填"""

    # score 专用
    score_amount: PositiveBigInt | None = None
    """积分数量，type=score 时必填"""

    # 关系
    orders: list["Order"] = Relationship(back_populates="product")
    """关联的订单列表"""

    redeems: list["Redeem"] = Relationship(back_populates="product")
    """关联的兑换码列表"""

