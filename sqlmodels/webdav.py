"""
WebDAV 账户模型

管理用户的 WebDAV 连接账户，每个账户对应一个挂载根路径。
通过 HTTP Basic Auth 认证访问 DAV 协议端点。
"""
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str255

if TYPE_CHECKING:
    from .user import User


# ==================== Base 模型 ====================

class WebDAVBase(SQLModelBase):
    """WebDAV 账户基础字段"""

    name: Str255
    """账户名称（同一用户下唯一）"""

    root: Str255 = "/"
    """挂载根目录路径"""

    readonly: bool = False
    """是否只读"""

    use_proxy: bool = False
    """是否使用代理下载"""


# ==================== 数据库模型 ====================

class WebDAV(WebDAVBase, UUIDTableBaseMixin):
    """WebDAV 账户模型"""

    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_webdav_name_user"),)

    password: Str255
    """密码（Argon2 哈希）"""

    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE",
    )
    """所属用户UUID"""

    # 关系
    user: "User" = Relationship(back_populates="webdavs")


# ==================== DTO 模型 ====================

class WebDAVCreateRequest(SQLModelBase):
    """创建 WebDAV 账户请求"""

    name: Str255
    """账户名称"""

    password: Str255 = Field(min_length=1)
    """账户密码（明文，服务端哈希后存储）"""

    root: Str255 = "/"
    """挂载根目录路径"""

    readonly: bool = False
    """是否只读"""

    use_proxy: bool = False
    """是否使用代理下载"""


class WebDAVUpdateRequest(SQLModelBase):
    """更新 WebDAV 账户请求"""

    password: Str255 | None = Field(default=None, min_length=1)
    """新密码（为 None 时不修改）"""

    root: Str255 | None = None
    """新挂载根目录路径（为 None 时不修改）"""

    readonly: bool | None = None
    """是否只读（为 None 时不修改）"""

    use_proxy: bool | None = None
    """是否使用代理下载（为 None 时不修改）"""


class WebDAVAccountResponse(SQLModelBase):
    """WebDAV 账户响应"""

    id: UUID
    """账户ID"""

    name: Str255
    """账户名称"""

    root: Str255
    """挂载根目录路径"""

    readonly: bool
    """是否只读"""

    use_proxy: bool
    """是否使用代理下载"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """更新时间"""
