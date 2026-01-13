from datetime import datetime
from enum import StrEnum
from typing import Literal, TYPE_CHECKING, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import BinaryExpression, ClauseElement, and_
from sqlmodel import Field, Relationship
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.main import RelationshipInfo

from .base import SQLModelBase
from .model_base import ResponseBase
from .mixin import UUIDTableBaseMixin, TableViewRequest, ListResponse

T = TypeVar("T", bound="User")

if TYPE_CHECKING:
    from .group import Group
    from .download import Download
    from .object import Object
    from .order import Order
    from .share import Share
    from .storage_pack import StoragePack
    from .tag import Tag
    from .task import Task
    from .user_authn import UserAuthn
    from .webdav import WebDAV

class AvatarType(StrEnum):
    """头像类型枚举"""
    
    DEFAULT = "default"
    GRAVATAR = "gravatar"
    FILE = "file"

class ThemeType(StrEnum):
    """主题类型枚举"""
    
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"

class UserStatus(StrEnum):
    """用户状态枚举"""

    ACTIVE = "active"
    ADMIN_BANNED = "admin_banned"
    SYSTEM_BANNED = "system_banned"


# ==================== 筛选参数 ====================

class UserFilterParams(SQLModelBase):
    """
    用户过滤参数

    用于管理员搜索用户列表，支持用户组、用户名、昵称、状态等过滤。
    """
    group_id: UUID | None = None
    """按用户组UUID筛选"""

    username_contains: str | None = Field(default=None, max_length=50)
    """用户名包含（不区分大小写的模糊搜索）"""

    nickname_contains: str | None = Field(default=None, max_length=50)
    """昵称包含（不区分大小写的模糊搜索）"""

    status: UserStatus | None = None
    """按用户状态筛选"""


# ==================== Base 模型 ====================

class UserBase(SQLModelBase):
    """用户基础字段，供数据库模型和 DTO 共享"""

    username: str
    """用户名"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""

    score: int = 0
    """用户积分"""


# ==================== DTO 模型 ====================

class LoginRequest(SQLModelBase):
    """登录请求 DTO"""

    username: str
    """用户名或邮箱"""

    password: str
    """用户密码"""

    captcha: str | None = None
    """验证码"""

    two_fa_code: int | None = Field(min_length=6, max_length=6)
    """两步验证代码"""


class RegisterRequest(SQLModelBase):
    """注册请求 DTO"""

    username: str
    """用户名，唯一，一经注册不可更改"""

    password: str
    """用户密码"""

    captcha: str | None = None
    """验证码"""


class WebAuthnInfo(SQLModelBase):
    """WebAuthn 信息 DTO"""

    credential_id: str
    """凭证 ID"""

    credential_public_key: str
    """凭证公钥"""

    sign_count: int
    """签名计数器"""

    credential_device_type: bool
    """是否为平台认证器"""

    credential_backed_up: bool
    """凭证是否已备份"""

    transports: list[str]
    """支持的传输方式"""

class AccessTokenBase(BaseModel):
    """访问令牌响应 DTO"""

    access_expires: datetime
    """访问令牌过期时间"""

    access_token: str
    """访问令牌"""

class RefreshTokenBase(BaseModel):
    """刷新令牌响应DTO"""

    refresh_expires: datetime
    """刷新令牌过期时间"""

    refresh_token: str
    """刷新令牌"""


class TokenResponse(ResponseBase, AccessTokenBase, RefreshTokenBase):
    """令牌响应 DTO"""


class UserResponse(ResponseBase):
    """用户响应 DTO"""

    id: UUID
    """用户UUID"""

    nickname: str | None = None
    """用户昵称"""

    avatar: Literal["default", "gravatar", "file"] = "default"
    """头像类型"""

    created_at: datetime
    """用户创建时间"""

    anonymous: bool = False
    """是否为匿名用户"""

    group: "GroupResponse | None" = None
    """用户所属用户组"""

    tags: list[str] = []
    """用户标签列表"""


class UserPublic(UserBase):
    """用户公开信息 DTO，用于 API 响应"""

    id: UUID | None = None
    """用户UUID"""

    nickname: str | None = None
    """昵称"""

    storage: int = 0
    """已用存储空间（字节）"""

    avatar: str | None = None
    """头像地址"""

    group_expires: datetime | None = None
    """用户组过期时间"""

    group_id: UUID | None = None
    """所属用户组UUID"""

    two_factor: str | None = None
    """两步验证密钥（32位字符串，null 表示未启用）"""

    created_at: datetime | None = None
    """创建时间"""

    updated_at: datetime | None = None
    """更新时间"""


class UserSettingResponse(SQLModelBase):
    """用户设置响应 DTO"""

    authn: "AuthnResponse | None" = None
    """认证信息"""

    group_expires: datetime | None = None
    """用户组过期时间"""

    prefer_theme: str = "#5898d4"
    """用户首选主题"""

    themes: dict[str, str] = {}
    """用户主题配置"""

    two_factor: bool = False
    """是否启用两步验证"""

    uid: UUID | None = None
    """用户UUID"""


# ==================== 管理员用户管理 DTO ====================

class UserAdminUpdateRequest(SQLModelBase):
    """管理员更新用户请求 DTO"""

    nickname: str | None = Field(default=None, max_length=50)
    """昵称"""

    password: str | None = None
    """新密码（为空则不修改）"""

    group_id: UUID | None = None
    """用户组UUID"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""

    score: int | None = Field(default=None, ge=0)
    """积分"""

    storage: int | None = Field(default=None, ge=0)
    """已用存储空间（用于手动校准）"""

    group_expires: datetime | None = None
    """用户组过期时间"""

    two_factor: str | None = None
    """两步验证密钥（32位字符串，传 null 可清除，不传则不修改）"""


class UserCalibrateResponse(SQLModelBase):
    """用户存储校准响应 DTO"""

    user_id: UUID
    """用户UUID"""

    previous_storage: int
    """校准前的存储空间（字节）"""

    current_storage: int
    """校准后的存储空间（字节）"""

    difference: int
    """差异值（字节）"""

    file_count: int
    """实际文件数量"""


class UserAdminDetailResponse(UserPublic):
    """管理员用户详情响应 DTO"""

    two_factor_enabled: bool = False
    """是否启用两步验证"""

    file_count: int = 0
    """文件数量"""

    share_count: int = 0
    """分享数量"""

    task_count: int = 0
    """任务数量"""


# 前向引用导入
from .group import GroupResponse  # noqa: E402
from .user_authn import AuthnResponse  # noqa: E402

# 更新前向引用
UserResponse.model_rebuild()
UserSettingResponse.model_rebuild()


# ==================== 数据库模型 ====================

class User(UserBase, UUIDTableBaseMixin):
    """用户模型"""

    username: str = Field(max_length=50, unique=True, index=True)
    """用户名，唯一，一经注册不可更改"""

    nickname: str | None = Field(default=None, max_length=50)
    """用于公开展示的名字，可使用真实姓名或昵称"""

    password: str = Field(max_length=255)
    """用户密码（加密后）"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""

    storage: int = Field(default=0, sa_column_kwargs={"server_default": "0"}, ge=0)
    """已用存储空间（字节）"""

    two_factor: str | None = Field(default=None, min_length=32, max_length=32)
    """两步验证密钥"""

    avatar: str = Field(default="default", max_length=255)
    """头像地址"""

    score: int = Field(default=0, sa_column_kwargs={"server_default": "0"}, ge=0)
    """用户积分"""

    group_expires: datetime | None = Field(default=None)
    """当前用户组过期时间"""

    # Option 相关字段
    # theme: ThemeType = Field(default=ThemeType.SYSTEM)
    # """主题类型: light/dark/system"""

    language: str = Field(default="zh-CN", max_length=5)
    """语言偏好"""

    timezone: int = Field(default=8, ge=-12, le=12)
    """时区，UTC 偏移小时数"""

    # 外键
    group_id: UUID = Field(
        foreign_key="group.id",
        index=True,
        ondelete="RESTRICT"
    )
    """所属用户组UUID"""

    previous_group_id: UUID | None = Field(
        default=None,
        foreign_key="group.id",
        ondelete="SET NULL"
    )
    """之前的用户组UUID（用于过期后恢复）"""


    # 关系
    group: "Group" = Relationship(
        back_populates="users",
        sa_relationship_kwargs={
            "foreign_keys": "User.group_id"
        }
    )
    previous_group: "Group" = Relationship(
        back_populates="previous_users",
        sa_relationship_kwargs={
            "foreign_keys": "User.previous_group_id"
        }
    )

    downloads: list["Download"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    objects: list["Object"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "foreign_keys": "[Object.owner_id]"
        }
    )
    """用户的所有对象（文件和目录）"""
    orders: list["Order"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    shares: list["Share"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    storage_packs: list["StoragePack"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    tags: list["Tag"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    tasks: list["Task"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    webdavs: list["WebDAV"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    authns: list["UserAuthn"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    def to_public(self) -> "UserPublic":
        """转换为公开 DTO，排除敏感字段"""
        return UserPublic.model_validate(self)

    @classmethod
    async def get_with_count(
            cls: type[T],
            session: AsyncSession,
            condition: BinaryExpression | ClauseElement | None = None,
            *,
            filter_params: 'UserFilterParams | None' = None,
            join: type[T] | tuple[type[T], ClauseElement] | None = None,
            options: list | None = None,
            load: RelationshipInfo | None = None,
            order_by: list[ClauseElement] | None = None,
            filter: BinaryExpression | ClauseElement | None = None,
            table_view: TableViewRequest | None = None,
    ) -> 'ListResponse[T]':
        """
        获取分页用户列表及总数，支持用户过滤参数

        :param filter_params: UserFilterParams 过滤参数对象（用户组、用户名、昵称、状态等）
        :param 其他参数: 继承自 UUIDTableBaseMixin.get_with_count()
        """
        # 构建过滤条件
        merged_condition = condition
        if filter_params is not None:
            filter_conditions: list[BinaryExpression] = []

            if filter_params.group_id is not None:
                filter_conditions.append(cls.group_id == filter_params.group_id)

            if filter_params.username_contains is not None:
                filter_conditions.append(cls.username.ilike(f"%{filter_params.username_contains}%"))

            if filter_params.nickname_contains is not None:
                filter_conditions.append(cls.nickname.ilike(f"%{filter_params.nickname_contains}%"))

            if filter_params.status is not None:
                filter_conditions.append(cls.status == filter_params.status)

            if filter_conditions:
                combined_filter = and_(*filter_conditions)
                if merged_condition is not None:
                    merged_condition = and_(merged_condition, combined_filter)
                else:
                    merged_condition = combined_filter

        return await super().get_with_count(
            session,
            merged_condition,
            join=join,
            options=options,
            load=load,
            order_by=order_by,
            filter=filter,
            table_view=table_view,
        )