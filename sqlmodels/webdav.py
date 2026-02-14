
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint

from sqlmodel_ext import SQLModelBase, TableBaseMixin

if TYPE_CHECKING:
    from .user import User

class WebDAV(SQLModelBase, TableBaseMixin):
    """WebDAV账户模型"""

    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_webdav_name_user"),)

    name: str = Field(max_length=255, description="WebDAV账户名")
    password: str = Field(max_length=255, description="WebDAV密码")
    root: str = Field(default="/", sa_column_kwargs={"server_default": "'/'"}, description="根目录路径")
    readonly: bool = Field(default=False, description="是否只读")
    use_proxy: bool = Field(default=False, description="是否使用代理下载")
    
    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""
    
    # 关系
    user: "User" = Relationship(back_populates="webdavs")