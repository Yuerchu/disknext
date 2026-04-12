from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, text

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str64

if TYPE_CHECKING:
    from .product import Product
    from .user import User


class RedeemType(StrEnum):
    """兑换码类型枚举"""

    STORAGE_PACK = "storage_pack"
    """容量包"""

    GROUP_TIME = "group_time"
    """用户组时长"""

    SCORE = "score"
    """积分充值"""


# ==================== DTO 模型 ====================

class RedeemCreateRequest(SQLModelBase):
    """批量生成兑换码请求 DTO"""

    product_id: UUID
    """关联商品UUID"""

    count: int = Field(default=1, ge=1, le=100)
    """生成数量"""


class RedeemUseRequest(SQLModelBase):
    """使用兑换码请求 DTO"""

    code: str = Field(min_length=1, max_length=64)
    """兑换码"""


class RedeemInfoResponse(SQLModelBase):
    """兑换码信息响应 DTO（用户侧）"""

    type: RedeemType
    """兑换码类型"""

    product_name: str | None = None
    """关联商品名称"""

    num: int
    """可兑换数量"""

    is_used: bool
    """是否已使用"""


class RedeemAdminResponse(SQLModelBase):
    """兑换码管理响应 DTO（管理侧）"""

    id: int
    """兑换码ID"""

    type: RedeemType
    """兑换码类型"""

    product_id: UUID | None = None
    """关联商品UUID"""

    num: int
    """可兑换数量"""

    code: str
    """兑换码"""

    is_used: bool
    """是否已使用"""

    used_at: datetime | None = None
    """使用时间"""

    used_by: UUID | None = None
    """使用者UUID"""


# ==================== 数据库模型 ====================

class Redeem(SQLModelBase, TableBaseMixin):
    """兑换码模型"""

    type: RedeemType
    """兑换码类型"""

    product_id: UUID | None = Field(default=None, foreign_key="product.id", ondelete="SET NULL")
    """关联商品UUID"""

    num: int = Field(default=1, sa_column_kwargs={"server_default": "1"})
    """可兑换数量/时长等"""

    code: str = Field(unique=True, index=True)
    """兑换码，唯一"""

    is_used: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否已使用"""

    used_at: datetime | None = None
    """使用时间"""

    used_by: UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    """使用者UUID"""

    # 关系
    product: "Product" = Relationship(back_populates="redeems")
    user: "User" = Relationship(back_populates="redeems")

    def to_admin_response(self) -> RedeemAdminResponse:
        """转换为管理侧响应 DTO"""
        return RedeemAdminResponse(
            id=self.id,
            type=self.type,
            product_id=self.product_id,
            num=self.num,
            code=self.code,
            is_used=self.is_used,
            used_at=self.used_at,
            used_by=self.used_by,
        )

    def to_info_response(self, product_name: str | None = None) -> RedeemInfoResponse:
        """转换为用户侧响应 DTO"""
        return RedeemInfoResponse(
            type=self.type,
            product_name=product_name,
            num=self.num,
            is_used=self.is_used,
        )
