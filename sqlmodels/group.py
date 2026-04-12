
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger
from sqlmodel import Field, Relationship, text

from sqlmodel_ext import SQLModelBase, TableBaseMixin, UUIDTableBaseMixin, Str255

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

    @classmethod
    def from_group(
        cls,
        group: "Group",
        user_count: int,
        policies: list["Policy"],
    ) -> "GroupDetailResponse":
        """从 Group ORM 对象构建"""
        opts = group.options
        return cls(
            # GroupCoreBase 字段（从 Group 模型提取）
            **GroupCoreBase.model_validate(group, from_attributes=True).model_dump(),
            # GroupAllOptionsBase 字段（从 GroupOptions 提取）
            **(GroupAllOptionsBase.model_validate(opts, from_attributes=True).model_dump() if opts else {}),
            # 计算字段
            user_count=user_count,
            policy_ids=[p.id for p in policies],
        )


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

    @classmethod
    def from_group(cls, group: "Group") -> "GroupClaims":
        """
        从 Group ORM 对象（需预加载 options 关系）构建权限快照。

        :param group: 已加载 options 的 Group 对象
        """
        opts = group.options
        return cls(
            **GroupCoreBase.model_validate(group, from_attributes=True).model_dump(),
            **(GroupAllOptionsBase.model_validate(opts, from_attributes=True).model_dump() if opts else {}),
        )


class GroupResponse(GroupBase, GroupOptionsBase):
    """用户组响应 DTO"""

    id: UUID
    """用户组UUID"""

    allow_share: bool = False
    """是否允许分享"""

    allow_remote_download: bool = False
    """是否允许离线下载"""

    allow_archive_download: bool = False
    """是否允许打包下载"""

    compress: bool = False
    """是否允许压缩"""

    webdav: bool = False
    """是否允许WebDAV"""

    allow_webdav_proxy: bool = False
    """是否允许WebDAV代理"""


# ==================== 数据库模型 ====================

# GroupPolicyLink 定义在 policy.py 中以避免循环导入
from .policy import GroupPolicyLink


class GroupOptions(GroupAllOptionsBase, TableBaseMixin):
    """用户组选项模型"""

    group_id: UUID = Field(
        foreign_key="group.id",
        unique=True,
        ondelete="CASCADE"
    )
    """关联的用户组UUID"""

    # 反向关系
    group: "Group" = Relationship(back_populates="options")


class Group(GroupBase, UUIDTableBaseMixin):
    """用户组模型"""

    name: Str255 = Field(unique=True)
    """用户组名"""

    max_storage: int = Field(default=0, sa_type=BigInteger, sa_column_kwargs={"server_default": "0"})
    """最大存储空间（字节）"""

    share_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否允许创建分享"""

    web_dav_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否允许使用WebDAV"""

    admin: bool = False
    """是否为管理员组"""

    speed_limit: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """速度限制 (KB/s), 0为不限制"""

    # 一对一关系：用户组选项
    options: GroupOptions | None = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )

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

    def to_response(self) -> "GroupResponse":
        """转换为响应 DTO"""
        opts = self.options
        return GroupResponse(
            id=self.id,
            name=self.name,
            allow_share=self.share_enabled,
            webdav=self.web_dav_enabled,
            share_download=opts.share_download if opts else False,
            share_free=opts.share_free if opts else False,
            relocate=opts.relocate if opts else False,
            source_batch=opts.source_batch if opts else 0,
            select_node=opts.select_node if opts else False,
            advance_delete=opts.advance_delete if opts else False,
            allow_remote_download=opts.aria2 if opts else False,
            allow_archive_download=opts.archive_download if opts else False,
            allow_webdav_proxy=opts.webdav_proxy if opts else False,
        )
