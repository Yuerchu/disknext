from typing import TYPE_CHECKING
from uuid import UUID

from enum import StrEnum
from sqlmodel import Field, Relationship, text

from .base import SQLModelBase
from .mixin import UUIDTableBaseMixin

if TYPE_CHECKING:
    from .object import Object
    from .group import Group


class GroupPolicyLink(SQLModelBase, table=True):
    """用户组与存储策略的多对多关联表"""

    group_id: UUID = Field(
        foreign_key="group.id",
        primary_key=True,
        ondelete="CASCADE"
    )
    """用户组UUID"""

    policy_id: UUID = Field(
        foreign_key="policy.id",
        primary_key=True,
        ondelete="CASCADE"
    )
    """存储策略UUID"""


class PolicyType(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class PolicyBase(SQLModelBase):
    """存储策略基础字段，供 DTO 和数据库模型共享"""

    name: str = Field(max_length=255)
    """策略名称"""

    type: PolicyType
    """存储策略类型"""

    server: str | None = Field(default=None, max_length=255)
    """服务器地址（本地策略为绝对路径）"""

    bucket_name: str | None = Field(default=None, max_length=255)
    """存储桶名称"""

    is_private: bool = True
    """是否为私有空间"""

    base_url: str | None = Field(default=None, max_length=255)
    """访问文件的基础URL"""

    access_key: str | None = None
    """Access Key"""

    secret_key: str | None = None
    """Secret Key"""

    max_size: int = Field(default=0, ge=0)
    """允许上传的最大文件尺寸（字节）"""

    auto_rename: bool = False
    """是否自动重命名"""

    dir_name_rule: str | None = Field(default=None, max_length=255)
    """目录命名规则"""

    file_name_rule: str | None = Field(default=None, max_length=255)
    """文件命名规则"""

    is_origin_link_enable: bool = False
    """是否开启源链接访问"""


# ==================== DTO 模型 ====================


class PolicySummary(SQLModelBase):
    """策略摘要，用于列表展示"""

    id: UUID
    """策略UUID"""

    name: str
    """策略名称"""

    type: PolicyType
    """策略类型"""

    server: str | None
    """服务器地址"""

    max_size: int
    """最大文件尺寸"""

    is_private: bool
    """是否私有"""


# ==================== 数据库模型 ====================


class PolicyOptionsBase(SQLModelBase):
    """存储策略选项的基础模型"""

    token: str | None = Field(default=None)
    """访问令牌"""

    file_type: str | None = Field(default=None)
    """允许的文件类型"""

    mimetype: str | None = Field(default=None, max_length=127)
    """MIME类型"""

    od_redirect: str | None = Field(default=None, max_length=255)
    """OneDrive重定向地址"""

    chunk_size: int = Field(default=52428800, sa_column_kwargs={"server_default": "52428800"})
    """分片上传大小（字节），默认50MB"""

    s3_path_style: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否使用S3路径风格"""


class PolicyOptions(PolicyOptionsBase, UUIDTableBaseMixin):
    """存储策略选项模型（与Policy一对一关联）"""

    policy_id: UUID = Field(
        foreign_key="policy.id",
        unique=True,
        ondelete="CASCADE"
    )
    """关联的策略UUID"""

    # 反向关系
    policy: "Policy" = Relationship(back_populates="options")
    """关联的策略"""


class Policy(PolicyBase, UUIDTableBaseMixin):
    """存储策略模型"""

    # 覆盖基类字段以添加数据库专有配置
    name: str = Field(max_length=255, unique=True)
    """策略名称"""

    is_private: bool = Field(default=True, sa_column_kwargs={"server_default": text("true")})
    """是否为私有空间"""

    max_size: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """允许上传的最大文件尺寸（字节）"""

    auto_rename: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否自动重命名"""

    is_origin_link_enable: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否开启源链接访问"""

    # 一对一关系：策略选项
    options: PolicyOptions | None = Relationship(
        back_populates="policy",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    """策略的扩展选项"""

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