
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship
from sqlmodel_ext.field_types.dialects.postgresql import Array

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str255, NonNegativeBigInt

from .scope import ScopeValueEnum

if TYPE_CHECKING:
    from .user import User
    from .policy import Policy


# ==================== Base 模型 ====================

class GroupBase(SQLModelBase):
    """用户组基础字段，供数据库模型和 DTO 共享"""

    name: Str255
    """用户组名称"""


class GroupOptionsBase(SQLModelBase):
    """用户组基础选项字段"""

    share_download: bool = False
    """是否允许分享下载"""

    share_free: bool = False
    """是否免积分获取需要积分的内容"""

    relocate: bool = False
    """是否允许文件重定位"""

    source_batch: int = 0
    """批量获取源地址数量"""

    select_node: bool = False
    """是否允许选择节点"""

    advance_delete: bool = False
    """是否允许高级删除"""


class GroupAllOptionsBase(GroupOptionsBase):
    """用户组完整选项字段，供 DTO 和数据库模型共享"""

    archive_download: bool = False
    """是否允许打包下载"""

    archive_task: bool = False
    """是否允许创建打包任务"""

    webdav_proxy: bool = False
    """是否允许WebDAV代理"""

    aria2: bool = False
    """是否允许使用aria2"""

    redirected_source: bool = False
    """是否使用重定向源"""


# ==================== DTO 模型 ====================

class GroupCreateRequest(GroupAllOptionsBase):
    """创建用户组请求 DTO"""

    name: Str255
    """用户组名称"""

    max_storage: int = Field(default=0, ge=0)
    """最大存储空间（字节），0表示不限制"""

    share_enabled: bool = False
    """是否允许创建分享"""

    web_dav_enabled: bool = False
    """是否允许使用WebDAV"""

    speed_limit: int = Field(default=0, ge=0)
    """速度限制 (KB/s), 0为不限制"""

    source_batch: int = Field(default=0, ge=0)
    """批量获取源地址数量（覆盖基类以添加 ge 约束）"""

    policy_ids: list[UUID] = Field(default=[], max_length=50)
    """关联的存储策略UUID列表"""


class GroupUpdateRequest(SQLModelBase):
    """更新用户组请求 DTO（所有字段可选）"""

    name: Str255 | None = None
    """用户组名称"""

    max_storage: int | None = Field(default=None, ge=0)
    """最大存储空间（字节）"""

    share_enabled: bool | None = None
    """是否允许创建分享"""

    web_dav_enabled: bool | None = None
    """是否允许使用WebDAV"""

    speed_limit: int | None = Field(default=None, ge=0)
    """速度限制 (KB/s)"""

    # 用户组选项
    share_download: bool | None = None
    share_free: bool | None = None
    relocate: bool | None = None
    source_batch: int | None = None
    select_node: bool | None = None
    advance_delete: bool | None = None
    archive_download: bool | None = None
    archive_task: bool | None = None
    webdav_proxy: bool | None = None
    aria2: bool | None = None
    redirected_source: bool | None = None

    policy_ids: list[UUID] | None = Field(default=None, max_length=50)
    """关联的存储策略UUID列表"""


class GroupCoreBase(SQLModelBase):
    """用户组核心字段（从 Group 模型提取）"""

    id: UUID
    """用户组UUID"""

    name: str
    """用户组名称"""

    max_storage: int = 0
    """最大存储空间（字节）"""

    share_enabled: bool = False
    """是否允许创建分享"""

    web_dav_enabled: bool = False
    """是否允许使用WebDAV"""

    admin: bool = False
    """是否为管理员组"""

    speed_limit: int = 0
    """速度限制 (KB/s)"""


class GroupDetailResponse(GroupCoreBase, GroupAllOptionsBase):
    """用户组详情响应 DTO"""

    user_count: int = 0
    """用户数量"""

    policy_ids: list[UUID] = []
    """关联的存储策略UUID列表"""


class GroupListResponse(SQLModelBase):
    """用户组列表响应 DTO"""

    groups: list["GroupDetailResponse"] = []
    """用户组列表"""

    total: int = 0
    """总数"""


class GroupClaims(GroupCoreBase, GroupAllOptionsBase):
    """
    JWT 中的用户组权限快照。

    复用 GroupCoreBase（id, name, max_storage, share_enabled, web_dav_enabled, admin, speed_limit）
    和 GroupAllOptionsBase（share_download, share_free, ... 共 11 个功能开关）。
    """


class GroupResponse(GroupBase, GroupAllOptionsBase):
    """用户组响应 DTO"""

    id: UUID
    """用户组UUID"""

    share_enabled: bool = False
    """是否允许分享"""

    web_dav_enabled: bool = False
    """是否允许WebDAV"""


# ==================== 数据库模型 ====================

# GroupPolicyLink 定义在 policy.py 中以避免循环导入
from .policy import GroupPolicyLink


class Group(GroupBase, GroupAllOptionsBase, UUIDTableBaseMixin):
    """用户组模型"""

    name: Str255 = Field(unique=True)
    """用户组名"""

    max_storage: NonNegativeBigInt = 0
    """最大存储空间（字节）"""

    share_enabled: bool = False
    """是否允许创建分享"""

    web_dav_enabled: bool = False
    """是否允许使用WebDAV"""

    admin: bool = False
    """是否为管理员组"""

    speed_limit: int = 0
    """速度限制 (KB/s), 0为不限制"""

    default_scopes: Array[ScopeValueEnum] = Field(default_factory=list)
    """新用户加入该组时的默认权限模板"""

    # 多对多关系：用户组可以关联多个存储策略
    policies: list["Policy"] = Relationship(
        back_populates="groups",
        link_model=GroupPolicyLink,
    )

    # 关系：一个组可以有多个用户
    users: list["User"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"foreign_keys": "User.group_id"}
    )
    """当前属于该组的用户列表"""

    previous_users: list["User"] = Relationship(
        back_populates="previous_group",
        sa_relationship_kwargs={"foreign_keys": "User.previous_group_id"}
    )
    """之前属于该组的用户列表（用于过期后恢复）"""

