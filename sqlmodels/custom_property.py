"""
用户自定义属性定义模型

允许用户定义类型化的自定义属性模板（如标签、评分、分类等），
实际值通过 EntryMetadata KV 表存储，键名格式：custom:{property_definition_id}。

支持的属性类型：text, number, boolean, select, multi_select, rating, link
"""
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON
from sqlmodel import Field, Relationship

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str100, Str255, Str500, NonNegativeBigInt

if TYPE_CHECKING:
    from .user import User


# ==================== 枚举 ====================

class CustomPropertyType(StrEnum):
    """自定义属性值类型枚举"""
    TEXT = "text"
    """文本"""
    NUMBER = "number"
    """数字"""
    BOOLEAN = "boolean"
    """布尔值"""
    SELECT = "select"
    """单选"""
    MULTI_SELECT = "multi_select"
    """多选"""
    RATING = "rating"
    """评分（1-5）"""
    LINK = "link"
    """链接"""


# ==================== Base 模型 ====================

class CustomPropertyDefinitionBase(SQLModelBase):
    """自定义属性定义基础模型"""

    name: Str100
    """属性显示名称"""

    type: CustomPropertyType
    """属性值类型"""

    icon: Str100 | None = None
    """图标标识（iconify 名称）"""

    options: list[str] | None = Field(default=None, sa_type=JSON)
    """可选值列表（仅 select/multi_select 类型）"""

    default_value: str | None = Field(default=None, max_length=500)
    """默认值"""


# ==================== 数据库模型 ====================

class CustomPropertyDefinition(CustomPropertyDefinitionBase, UUIDTableBaseMixin):
    """
    用户自定义属性定义

    每个用户独立管理自己的属性模板。
    实际属性值存储在 EntryMetadata 表中，键名格式：custom:{id}。
    """

    owner_id: UUID = Field(
        foreign_key="user.id",
        ondelete="CASCADE",
        index=True,
    )
    """所有者用户UUID"""

    sort_order: NonNegativeBigInt = 0
    """排序顺序"""

    # 关系
    owner: "User" = Relationship()
    """所有者"""


# ==================== DTO 模型 ====================

class CustomPropertyCreateRequest(SQLModelBase):
    """创建自定义属性请求 DTO"""

    name: Str100
    """属性显示名称"""

    type: CustomPropertyType
    """属性值类型"""

    icon: Str100 | None = None
    """图标标识"""

    options: list[Str255] | None = Field(default=None, max_length=50)
    """可选值列表（仅 select/multi_select 类型）"""

    default_value: Str500 | None = None
    """默认值"""


class CustomPropertyUpdateRequest(SQLModelBase):
    """更新自定义属性请求 DTO"""

    name: Str100 | None = None
    """属性显示名称"""

    icon: Str100 | None = None
    """图标标识"""

    options: list[Str255] | None = Field(default=None, max_length=50)
    """可选值列表"""

    default_value: Str500 | None = None
    """默认值"""

    sort_order: NonNegativeBigInt | None = None
    """排序顺序"""


class CustomPropertyResponse(CustomPropertyDefinitionBase):
    """自定义属性响应 DTO"""

    id: UUID
    """属性定义UUID"""

    sort_order: int
    """排序顺序"""
