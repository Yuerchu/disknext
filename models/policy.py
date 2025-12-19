from typing import TYPE_CHECKING
from uuid import UUID

from enum import StrEnum
from sqlmodel import Field, Relationship, text

from .base import SQLModelBase, UUIDTableBase

if TYPE_CHECKING:
    from .object import Object
    from .group import Group


class GroupPolicyLink(SQLModelBase, table=True):
    """用户组与存储策略的多对多关联表"""

    group_id: UUID = Field(foreign_key="group.id", primary_key=True)
    """用户组UUID"""

    policy_id: UUID = Field(foreign_key="policy.id", primary_key=True)
    """存储策略UUID"""

class PolicyType(StrEnum):
    LOCAL = "local"
    S3 = "s3"

class Policy(UUIDTableBase, table=True):
    """存储策略模型"""

    name: str = Field(max_length=255, unique=True)
    """策略名称"""

    type: PolicyType
    """存储策略类型"""

    server: str | None = Field(default=None, max_length=255)
    """服务器地址（本地策略为绝对路径）"""

    bucket_name: str | None = Field(default=None, max_length=255)
    """存储桶名称"""

    is_private: bool = Field(default=True, sa_column_kwargs={"server_default": text("true")})
    """是否为私有空间"""

    base_url: str | None = Field(default=None, max_length=255)
    """访问文件的基础URL"""

    access_key: str | None = Field(default=None)
    """Access Key"""

    secret_key: str | None = Field(default=None)
    """Secret Key"""
    max_size: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """允许上传的最大文件尺寸（字节）"""

    auto_rename: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否自动重命名"""

    dir_name_rule: str | None = Field(default=None, max_length=255)
    """目录命名规则"""

    file_name_rule: str | None = Field(default=None, max_length=255)
    """文件命名规则"""

    is_origin_link_enable: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否开启源链接访问"""
    
    options: str | None = Field(default=None)
    """其他选项 (JSON格式)"""
    # options 示例: {"token":"","file_type":null,"mimetype":"","od_redirect":"http://127.0.0.1:8000/...","chunk_size":52428800,"s3_path_style":false}
    
    # 关系
    objects: list["Object"] = Relationship(back_populates="policy")
    """策略下的所有对象"""

    # 多对多关系：策略可以被多个用户组使用
    groups: list["Group"] = Relationship(
        back_populates="policies",
        link_model=GroupPolicyLink,
    )
    
    @staticmethod
    async def create(
        policy: 'Policy | None' = None,
        **kwargs
    ):
        pass