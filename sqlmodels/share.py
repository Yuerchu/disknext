
from typing import TYPE_CHECKING
from datetime import datetime
from uuid import UUID

from sqlmodel import Field, Relationship

from sqlmodel_ext import NonNegativeBigInt, SQLModelBase, UUIDTableBaseMixin, Str64, Str128, Str255

from .model_base import ResponseBase
from .file import EntryType
from .user import AvatarType

if TYPE_CHECKING:
    from .user import User
    from .report import Report
    from .file import Entry


# ==================== Base 模型 ====================

class ShareBase(SQLModelBase):
    """分享基础字段，供 DTO 和数据库模型共享"""

    file_id: UUID
    """关联的对象UUID"""

    password: Str128 | None = None
    """分享密码"""

    expires: datetime | None = None
    """过期时间（NULL为永不过期）"""

    remain_downloads: int | None = None
    """剩余下载次数（NULL为不限制）"""

    preview_enabled: bool = True
    """是否允许预览"""

    score: NonNegativeBigInt = 0
    """兑换此分享所需的积分"""


# ==================== 数据库模型 ====================

class Share(SQLModelBase, UUIDTableBaseMixin):
    """分享模型"""

    code: UUID = Field(nullable=False, unique=True)
    """分享码"""

    password: Str255 | None = None
    """分享密码（加密后）"""

    file_id: UUID = Field(
        foreign_key="entry.id",
        index=True,
        ondelete="CASCADE"
    )
    """关联的对象UUID"""

    views: NonNegativeBigInt = 0
    """浏览次数"""

    downloads: NonNegativeBigInt = 0
    """下载次数"""

    remain_downloads: NonNegativeBigInt | None = None
    """剩余下载次数 (NULL为不限制)"""

    expires: datetime | None = None
    """过期时间 (NULL为永不过期)"""

    preview_enabled: bool = True
    """是否允许预览"""

    score: NonNegativeBigInt = 0
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

    entry: "Entry" = Relationship(back_populates="shares")
    """关联的对象"""

    reports: list["Report"] = Relationship(back_populates="share", cascade_delete=True)
    """举报列表"""


# ==================== DTO 模型 ====================

class ShareCreateRequest(ShareBase):
    """创建分享请求 DTO，继承 ShareBase 中的所有字段"""
    pass


class CreateShareResponse(ResponseBase):
    """创建分享响应 DTO"""

    share_id: UUID
    """新创建的分享记录 ID"""


class ShareOwnerInfo(SQLModelBase):
    """分享者公开信息 DTO"""

    user_id: UUID | None = None
    """用户 UUID（用于拼接头像端点，用户已删除时为 None）"""

    nickname: Str255 | None
    """昵称"""

    avatar: AvatarType = AvatarType.DEFAULT
    """头像类型"""


class ShareObjectItem(SQLModelBase):
    """分享中的文件/文件夹信息 DTO"""

    id: UUID
    """对象UUID"""

    name: Str255
    """名称"""

    type: EntryType
    """类型：file 或 folder"""

    size: int
    """文件大小（字节），目录为 0"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """修改时间"""


class SharePublic(SQLModelBase):
    """分享公开可见字段基类"""

    id: UUID
    """分享ID"""

    code: UUID
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

    has_password: bool
    """是否有密码"""

    created_at: datetime
    """创建时间"""


class ShareResponse(SharePublic):
    """用户自己的分享列表响应 DTO"""

    file_id: UUID
    """关联对象UUID"""

    is_expired: bool
    """是否已过期"""


class AdminShareListItem(SharePublic):
    """管理员分享列表项 DTO"""

    user_id: UUID
    """用户UUID"""

    username: Str255 | None
    """用户邮箱"""

    object_name: Str255 | None
    """对象名称"""


class AdminShareDetailResponse(SharePublic):
    """管理员分享详情响应 DTO"""

    user_id: UUID
    """用户UUID"""

    username: Str255 | None
    """用户邮箱"""

    object: ShareObjectItem | None
    """关联的对象"""


class ShareDetailResponse(SQLModelBase):
    """获取分享详情响应 DTO（面向访客，隐藏内部统计数据）"""

    created_at: datetime
    """创建时间"""

    expires: datetime | None
    """过期时间"""

    preview_enabled: bool
    """是否允许预览"""

    score: int
    """积分"""

    owner: ShareOwnerInfo
    """分享者信息"""

    object: ShareObjectItem
    """分享的根对象"""

    children: list[ShareObjectItem]
    """子文件/文件夹列表（仅目录分享有内容）"""

