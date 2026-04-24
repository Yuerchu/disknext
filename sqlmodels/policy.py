from typing import TYPE_CHECKING
from uuid import UUID

from enum import StrEnum
from sqlmodel import Field, Relationship

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str64, Str255, Str2048

if TYPE_CHECKING:
    from .file import Entry
    from .group import Group


class GroupPolicyLink(SQLModelBase, UUIDTableBaseMixin):
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

    name: Str255
    """策略名称"""

    type: PolicyType
    """存储策略类型"""

    server: Str255 | None = None
    """服务器地址（本地策略为绝对路径）"""

    bucket_name: Str255 | None = None
    """存储桶名称"""

    is_private: bool = True
    """是否为私有空间"""

    base_url: Str255 | None = None
    """访问文件的基础URL"""

    access_key: Str255 | None = None
    """Access Key"""

    secret_key: Str255 | None = None
    """Secret Key"""

    max_size: int = Field(default=0, ge=0)
    """允许上传的最大文件尺寸（字节）"""

    auto_rename: bool = False
    """是否自动重命名"""

    dir_name_rule: Str255 | None = None
    """目录命名规则"""

    file_name_rule: Str255 | None = None
    """文件命名规则"""

    is_origin_link_enable: bool = False
    """是否开启源链接访问"""

    token: str | None = None
    """访问令牌"""

    file_type: str | None = None
    """允许的文件类型"""

    mimetype: str | None = Field(default=None, max_length=127)
    """MIME类型"""

    od_redirect: Str255 | None = None
    """OneDrive重定向地址"""

    chunk_size: int = 52428800
    """分片上传大小（字节），默认50MB"""

    s3_path_style: bool = False
    """是否使用S3路径风格"""

    s3_region: Str64 = 'us-east-1'
    """S3 区域（如 us-east-1、ap-southeast-1），仅 S3 策略使用"""


# ==================== DTO 模型 ====================


class PolicySummary(SQLModelBase):
    """策略摘要，用于列表展示"""

    id: UUID
    """策略UUID"""

    name: Str255
    """策略名称"""

    type: PolicyType
    """策略类型"""

    server: Str255 | None
    """服务器地址"""

    max_size: int
    """最大文件尺寸"""

    is_private: bool
    """是否私有"""


class PolicyCreateRequest(PolicyBase):
    """创建存储策略请求 DTO"""

    chunk_size: int = Field(default=52428800, ge=1)
    """分片上传大小（字节），默认50MB（覆盖基类以添加 ge 约束）"""


class PolicyUpdateRequest(SQLModelBase):
    """更新存储策略请求 DTO（所有字段可选）"""

    name: Str255 | None = None
    """策略名称"""

    server: Str255 | None = None
    """服务器地址"""

    bucket_name: Str255 | None = None
    """存储桶名称"""

    is_private: bool | None = None
    """是否为私有空间"""

    base_url: Str255 | None = None
    """访问文件的基础URL"""

    access_key: Str255 | None = None
    """Access Key"""

    secret_key: Str255 | None = None
    """Secret Key"""

    max_size: int | None = Field(default=None, ge=0)
    """允许上传的最大文件尺寸（字节）"""

    auto_rename: bool | None = None
    """是否自动重命名"""

    dir_name_rule: Str255 | None = None
    """目录命名规则"""

    file_name_rule: Str255 | None = None
    """文件命名规则"""

    is_origin_link_enable: bool | None = None
    """是否开启源链接访问"""

    token: Str255 | None = None
    """访问令牌"""

    file_type: Str2048 | None = None
    """允许的文件类型"""

    mimetype: str | None = Field(default=None, max_length=127)
    """MIME类型"""

    od_redirect: Str255 | None = None
    """OneDrive重定向地址"""

    chunk_size: int | None = Field(default=None, ge=1)
    """分片上传大小（字节）"""

    s3_path_style: bool | None = None
    """是否使用S3路径风格"""

    s3_region: Str64 | None = None
    """S3 区域"""


class PathTestResponse(SQLModelBase):
    """路径测试响应"""

    path: str
    """解析后的路径"""

    is_exists: bool
    """路径是否存在"""

    is_writable: bool
    """路径是否可写"""


class PolicyGroupInfo(SQLModelBase):
    """策略关联的用户组信息"""

    id: str
    """用户组UUID"""

    name: str
    """用户组名称"""


class PolicyDetailResponse(SQLModelBase):
    """存储策略详情响应"""

    id: str
    """策略UUID"""

    name: str
    """策略名称"""

    type: str
    """策略类型"""

    server: str | None
    """服务器地址"""

    bucket_name: str | None
    """存储桶名称"""

    is_private: bool
    """是否私有"""

    base_url: str | None
    """基础URL"""

    access_key: str | None
    """Access Key"""

    secret_key: str | None
    """Secret Key"""

    max_size: int
    """最大文件尺寸"""

    auto_rename: bool
    """是否自动重命名"""

    dir_name_rule: str | None
    """目录命名规则"""

    file_name_rule: str | None
    """文件命名规则"""

    is_origin_link_enable: bool
    """是否启用外链"""

    token: str | None
    """访问令牌"""

    file_type: str | None
    """允许的文件类型"""

    mimetype: str | None
    """MIME类型"""

    od_redirect: str | None
    """OneDrive重定向地址"""

    chunk_size: int
    """分片上传大小（字节）"""

    s3_path_style: bool
    """是否使用S3路径风格"""

    s3_region: str
    """S3 区域"""

    groups: list[PolicyGroupInfo]
    """关联的用户组"""

    object_count: int
    """使用此策略的对象数量"""


class PolicyTestPathRequest(SQLModelBase):
    """测试本地路径请求 DTO"""

    path: str = Field(max_length=512)
    """要测试的本地路径"""


class PolicyTestSlaveRequest(SQLModelBase):
    """测试从机通信请求 DTO"""

    server: str = Field(max_length=255)
    """从机服务器地址"""

    secret: str
    """从机通信密钥"""


class PolicyTestS3Request(SQLModelBase):
    """测试 S3 连接请求 DTO"""

    server: str = Field(max_length=255)
    """S3 端点地址"""

    bucket_name: str = Field(max_length=255)
    """存储桶名称"""

    access_key: str
    """Access Key"""

    secret_key: str
    """Secret Key"""

    s3_region: str = Field(default='us-east-1', max_length=64)
    """S3 区域"""

    s3_path_style: bool = False
    """是否使用路径风格"""


class PolicyTestS3Response(SQLModelBase):
    """S3 连接测试响应"""

    is_connected: bool
    """连接是否成功"""

    message: str
    """测试结果消息"""


# ==================== 数据库模型 ====================


class Policy(PolicyBase, UUIDTableBaseMixin):
    """存储策略模型"""

    name: Str255 = Field(unique=True)
    """策略名称"""

    # 关系
    entries: list["Entry"] = Relationship(back_populates="policy")
    """策略下的所有对象"""

    groups: list["Group"] = Relationship(
        back_populates="policies",
        link_model=GroupPolicyLink,
    )