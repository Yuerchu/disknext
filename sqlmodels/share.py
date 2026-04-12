
from typing import TYPE_CHECKING
from datetime import datetime
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint, Index

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str64, Str128, Str255

from .model_base import ResponseBase
from .object import ObjectType

if TYPE_CHECKING:
    from .user import User
    from .report import Report
    from .object import Object


# ==================== Base 模型 ====================

class ShareBase(SQLModelBase):
    """分享基础字段，供 DTO 和数据库模型共享"""

    object_id: UUID
    """关联的对象UUID"""

    password: Str128 | None = None
    """分享密码"""

    expires: datetime | None = None
    """过期时间（NULL为永不过期）"""

    remain_downloads: int | None = None
    """剩余下载次数（NULL为不限制）"""

    preview_enabled: bool = True
    """是否允许预览"""

    score: int = Field(default=0, ge=0)
    """兑换此分享所需的积分"""


# ==================== 数据库模型 ====================

class Share(SQLModelBase, UUIDTableBaseMixin):
    """分享模型"""

    __table_args__ = (
        UniqueConstraint("code", name="uq_share_code"),
        Index("ix_share_source_name", "source_name"),
        Index("ix_share_user_created", "user_id", "created_at"),
        Index("ix_share_object", "object_id"),
    )

    code: Str64 = Field(nullable=False, index=True)
    """分享码"""

    password: Str255 | None = None
    """分享密码（加密后）"""

    object_id: UUID = Field(
        foreign_key="object.id",
        index=True,
        ondelete="CASCADE"
    )
    """关联的对象UUID"""

    views: int = 0
    """浏览次数"""

    downloads: int = 0
    """下载次数"""

    remain_downloads: int | None = None
    """剩余下载次数 (NULL为不限制)"""

    expires: datetime | None = None
    """过期时间 (NULL为永不过期)"""

    preview_enabled: bool = True
    """是否允许预览"""

    source_name: Str255 | None = None
    """源名称（冗余字段，便于展示）"""

    score: int = Field(default=0, ge=0)
    """兑换此分享所需的积分"""

    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """创建分享的用户UUID"""

    # 关系
    user: "User" = Relationship(back_populates="shares")
    """分享创建者"""

    object: "Object" = Relationship(back_populates="shares")
    """关联的对象"""

    reports: list["Report"] = Relationship(back_populates="share", cascade_delete=True)
    """举报列表"""

    @property
    def is_dir(self) -> bool:
        """是否为目录分享（向后兼容属性）"""
        from .object import ObjectType
        return self.object.type == ObjectType.FOLDER if self.object else False


# ==================== DTO 模型 ====================

class ShareCreateRequest(ShareBase):
    """创建分享请求 DTO，继承 ShareBase 中的所有字段"""
    pass


class CreateShareResponse(ResponseBase):
    """创建分享响应 DTO"""

    share_id: UUID
    """新创建的分享记录 ID"""


class ShareResponse(SQLModelBase):
    """查看分享响应 DTO"""

    id: UUID
    """分享ID"""

    code: Str64
    """分享码"""

    object_id: UUID
    """关联对象UUID"""

    source_name: Str255 | None
    """源名称"""

    views: int
    """浏览次数"""

    downloads: int
    """下载次数"""

    remain_downloads: int | None
    """剩余下载次数"""

    expires: datetime | None
    """过期时间"""

    preview_enabled: bool
    """是否允许预览"""

    score: int
    """积分"""

    created_at: datetime
    """创建时间"""

    is_expired: bool
    """是否已过期"""

    has_password: bool
    """是否有密码"""


class ShareOwnerInfo(SQLModelBase):
    """分享者公开信息 DTO"""

    nickname: Str255 | None
    """昵称"""

    avatar: Str255
    """头像"""


class ShareObjectItem(SQLModelBase):
    """分享中的文件/文件夹信息 DTO"""

    id: UUID
    """对象UUID"""

    name: Str255
    """名称"""

    type: ObjectType
    """类型：file 或 folder"""

    size: int
    """文件大小（字节），目录为 0"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """修改时间"""


class ShareDetailResponse(SQLModelBase):
    """获取分享详情响应 DTO（面向访客，隐藏内部统计数据）"""

    expires: datetime | None
    """过期时间"""

    preview_enabled: bool
    """是否允许预览"""

    score: int
    """积分"""

    created_at: datetime
    """创建时间"""

    owner: ShareOwnerInfo
    """分享者信息"""

    object: ShareObjectItem
    """分享的根对象"""

    children: list[ShareObjectItem]
    """子文件/文件夹列表（仅目录分享有内容）"""


class ShareListItemBase(SQLModelBase):
    """分享列表项基础字段"""

    id: UUID
    """分享ID"""

    code: Str64
    """分享码"""

    views: int
    """浏览次数"""

    downloads: int
    """下载次数"""

    remain_downloads: int | None
    """剩余下载次数"""

    expires: datetime | None
    """过期时间"""

    preview_enabled: bool
    """是否允许预览"""

    score: int
    """积分"""

    user_id: UUID
    """用户UUID"""

    created_at: datetime
    """创建时间"""


class AdminShareListItem(ShareListItemBase):
    """管理员分享列表项 DTO，添加关联字段"""

    username: Str255 | None
    """用户名"""

    object_name: Str255 | None
    """对象名称"""

    @classmethod
    def from_share(
        cls,
        share: "Share",
        user: "User | None",
        obj: "Object | None",
    ) -> "AdminShareListItem":
        """从 Share ORM 对象构建"""
        return cls(
            **ShareListItemBase.model_validate(share, from_attributes=True).model_dump(),
            username=user.email if user else None,
            object_name=obj.name if obj else None,
        )
