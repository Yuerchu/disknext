"""
WebDAV 账户模型

管理用户的 WebDAV 连接账户，每个账户对应一个挂载根路径。
通过 HTTP Basic Auth 认证访问 DAV 协议端点。
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint

from sqlmodel_ext import SQLModelBase, TableBaseMixin

if TYPE_CHECKING:
    from .user import User


# ==================== Base 模型 ====================

class WebDAVBase(SQLModelBase):
    """WebDAV 账户基础字段"""

    name: str = Field(max_length=255)
    """账户名称（同一用户下唯一）"""

    root: str = Field(default="/", sa_column_kwargs={"server_default": "'/'"})
    """挂载根目录路径"""

    readonly: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    """是否只读"""

    use_proxy: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    """是否使用代理下载"""


# ==================== 数据库模型 ====================

class WebDAV(WebDAVBase, TableBaseMixin):
    """WebDAV 账户模型"""

    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_webdav_name_user"),)

    password: str = Field(max_length=255)
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

    name: str = Field(max_length=255)
    """账户名称"""

    password: str = Field(min_length=1, max_length=255)
    """账户密码（明文，服务端哈希后存储）"""

    root: str = "/"
    """挂载根目录路径"""

    readonly: bool = False
    """是否只读"""

    use_proxy: bool = False
    """是否使用代理下载"""


class WebDAVUpdateRequest(SQLModelBase):
    """更新 WebDAV 账户请求"""

    password: str | None = Field(default=None, min_length=1, max_length=255)
    """新密码（为 None 时不修改）"""

    root: str | None = None
    """新挂载根目录路径（为 None 时不修改）"""

    readonly: bool | None = None
    """是否只读（为 None 时不修改）"""

    use_proxy: bool | None = None
    """是否使用代理下载（为 None 时不修改）"""


class WebDAVAccountResponse(SQLModelBase):
    """WebDAV 账户响应"""

    id: int
    """账户ID"""

    name: str
    """账户名称"""

    root: str
    """挂载根目录路径"""

    readonly: bool
    """是否只读"""

    use_proxy: bool
    """是否使用代理下载"""

    created_at: str
    """创建时间"""

    updated_at: str
    """更新时间"""
