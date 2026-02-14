from enum import StrEnum

from sqlmodel import Field, text

from sqlmodel_ext import SQLModelBase, TableBaseMixin


class RedeemType(StrEnum):
    """兑换码类型枚举"""
    # [TODO] 补充具体兑换码类型
    pass


class Redeem(SQLModelBase, TableBaseMixin):
    """兑换码模型"""

    type: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """兑换码类型 [TODO] 待定义枚举"""
    product_id: int | None = Field(default=None, description="关联的商品/权益ID")
    num: int = Field(default=1, sa_column_kwargs={"server_default": "1"}, description="可兑换数量/时长等")
    code: str = Field(unique=True, index=True, description="兑换码，唯一")
    used: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")}, description="是否已使用")