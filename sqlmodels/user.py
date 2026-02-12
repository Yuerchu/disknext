from datetime import datetime
from enum import StrEnum
from typing import Literal, TYPE_CHECKING, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import BinaryExpression, ClauseElement, and_
from sqlmodel import Field, Relationship
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.main import RelationshipInfo

from .auth_identity import AuthProviderType
from .base import SQLModelBase
from .color import ChromaticColor, NeutralColor, ThemeColorsBase
from .model_base import ResponseBase
from .mixin import UUIDTableBaseMixin, TableViewRequest, ListResponse

T = TypeVar("T", bound="User")

if TYPE_CHECKING:
    from .auth_identity import AuthIdentity
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

    email_contains: str | None = Field(default=None, max_length=50)
    """邮箱包含（不区分大小写的模糊搜索）"""

    nickname_contains: str | None = Field(default=None, max_length=50)
    """昵称包含（不区分大小写的模糊搜索）"""

    status: UserStatus | None = None
    """按用户状态筛选"""


# ==================== Base 模型 ====================

class UserBase(SQLModelBase):
    """用户基础字段，供数据库模型和 DTO 共享"""

    email: str | None = None
    """用户邮箱（社交登录用户可能没有邮箱）"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""

    score: int = 0
    """用户积分"""


# ==================== DTO 模型 ====================

class UnifiedLoginRequest(SQLModelBase):
    """统一登录请求 DTO"""

    provider: AuthProviderType
    """登录方式"""

    identifier: str
    """标识符（邮箱 / OAuth code / Magic Link token）"""

    credential: str | None = None
    """凭证（密码，provider=email_password 时必填）"""

    two_fa_code: str | None = Field(default=None, min_length=6, max_length=6)
    """两步验证代码"""

    redirect_uri: str | None = None
    """OAuth 回调地址"""

    captcha: str | None = None
    """验证码"""


class UnifiedRegisterRequest(SQLModelBase):
    """统一注册请求 DTO"""

    provider: AuthProviderType
    """注册方式（email_password / phone_sms）"""

    identifier: str
    """标识符（邮箱 / 手机号）"""

    credential: str | None = None
    """凭证（密码 / 短信验证码）"""

    nickname: str | None = Field(default=None, max_length=50)
    """昵称"""

    captcha: str | None = None
    """验证码"""


class BatchDeleteRequest(SQLModelBase):
    """批量删除请求 DTO"""

    ids: list[UUID]
    """待删除 UUID 列表"""


class RefreshTokenRequest(SQLModelBase):
    """刷新令牌请求 DTO"""

    refresh_token: str
    """刷新令牌"""


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

class JWTPayload(SQLModelBase):
    """JWT 访问令牌解析后的 claims"""

    sub: UUID
    """用户 ID"""

    jti: UUID
    """令牌唯一标识符"""

    status: UserStatus
    """用户状态"""

    group: "GroupClaims"
    """用户组权限快照"""


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

    email: str | None = None
    """用户邮箱"""

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

class UserStorageResponse(SQLModelBase):
    """用户存储信息 DTO"""

    used: int
    """已用存储空间（字节）"""

    free: int
    """剩余存储空间（字节）"""

    total: int
    """总存储空间（字节）"""


class UserPublic(UserBase):
    """用户公开信息 DTO，用于 API 响应"""

    id: UUID
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

    group_name: str | None = None
    """用户组名称"""

    created_at: datetime | None = None
    """创建时间"""

    updated_at: datetime | None = None
    """更新时间"""


class UserSettingResponse(SQLModelBase):
    """用户设置响应 DTO"""

    id: UUID
    """用户UUID"""

    email: str | None = None
    """用户邮箱"""

    phone: str | None = None
    """手机号"""

    nickname: str | None = None
    """昵称"""

    created_at: datetime
    """用户注册时间"""

    group_name: str
    """用户所属用户组名称"""

    language: str
    """语言偏好"""

    timezone: int
    """时区"""

    authn: "list[AuthnResponse] | None" = None
    """认证信息"""

    group_expires: datetime | None = None
    """用户组过期时间"""

    two_factor: bool = False
    """是否启用两步验证"""

    theme_preset_id: UUID | None = None
    """选用的主题预设UUID"""

    theme_colors: ThemeColorsBase | None = None
    """当前生效的颜色配置"""


class UserThemeUpdateRequest(SQLModelBase):
    """用户更新主题请求 DTO"""

    theme_preset_id: UUID | None = None
    """主题预设UUID"""

    theme_colors: ThemeColorsBase | None = None
    """颜色配置"""


class SettingOption(StrEnum):
    """用户可自助修改的设置选项"""

    NICKNAME = "nickname"
    """昵称"""

    LANGUAGE = "language"
    """语言偏好"""

    TIMEZONE = "timezone"
    """时区"""


class UserSettingUpdateRequest(SQLModelBase):
    """用户设置更新请求 DTO，根据 option 路径参数仅使用对应字段"""

    nickname: str | None = Field(default=None, max_length=50)
    """昵称（传 null 可清除）"""

    language: str | None = Field(default=None, max_length=5)
    """语言偏好"""

    timezone: int | None = Field(default=None, ge=-12, le=14)
    """时区，UTC 偏移小时数"""


class UserTwoFactorResponse(SQLModelBase):
    """用户两步验证信息 DTO"""

    two_factor_key: str
    """两步验证密钥"""


class MagicLinkRequest(SQLModelBase):
    """Magic Link 请求 DTO"""

    email: str
    """接收 Magic Link 的邮箱"""

    captcha: str | None = None
    """验证码"""


# ==================== 管理员用户管理 DTO ====================

class UserAdminCreateRequest(SQLModelBase):
    """管理员创建用户请求 DTO"""

    email: str | None = Field(default=None, max_length=50)
    """用户邮箱"""

    password: str | None = None
    """用户密码（明文，由服务端加密；为空则不创建邮箱密码身份）"""

    nickname: str | None = Field(default=None, max_length=50)
    """昵称"""

    group_id: UUID
    """所属用户组UUID"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""


class UserAdminUpdateRequest(SQLModelBase):
    """管理员更新用户请求 DTO"""

    email: str | None = Field(default=None, max_length=50)
    """邮箱"""

    nickname: str | None = Field(default=None, max_length=50)
    """昵称"""

    phone: str | None = None
    """手机号"""

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

    file_count: int = 0
    """文件数量"""

    share_count: int = 0
    """分享数量"""

    task_count: int = 0
    """任务数量"""


# 前向引用导入
from .group import GroupClaims, GroupResponse  # noqa: E402
from .user_authn import AuthnResponse  # noqa: E402

# 更新前向引用
JWTPayload.model_rebuild()
UserResponse.model_rebuild()
UserSettingResponse.model_rebuild()


# ==================== 数据库模型 ====================

class User(UserBase, UUIDTableBaseMixin):
    """用户模型"""

    email: str | None = Field(default=None, max_length=50, unique=True, index=True)
    """用户邮箱（社交登录用户可能没有邮箱）"""

    nickname: str | None = Field(default=None, max_length=50)
    """用于公开展示的名字，可使用真实姓名或昵称"""

    phone: str | None = Field(default=None, max_length=20, unique=True, index=True)
    """手机号（预留）"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""

    storage: int = Field(default=0, sa_column_kwargs={"server_default": "0"}, ge=0)
    """已用存储空间（字节）"""

    avatar: str = Field(default="default", max_length=255)
    """头像地址"""

    score: int = Field(default=0, sa_column_kwargs={"server_default": "0"}, ge=0)
    """用户积分"""

    group_expires: datetime | None = Field(default=None)
    """当前用户组过期时间"""

    # Option 相关字段
    theme_preset_id: UUID | None = Field(
        default=None, foreign_key="themepreset.id", ondelete="SET NULL"
    )
    """选用的主题预设UUID"""

    color_primary: ChromaticColor | None = None
    """颜色快照：主色调"""

    color_secondary: ChromaticColor | None = None
    """颜色快照：辅助色"""

    color_success: ChromaticColor | None = None
    """颜色快照：成功色"""

    color_info: ChromaticColor | None = None
    """颜色快照：信息色"""

    color_warning: ChromaticColor | None = None
    """颜色快照：警告色"""

    color_error: ChromaticColor | None = None
    """颜色快照：错误色"""

    color_neutral: NeutralColor | None = None
    """颜色快照：中性色"""

    language: str = Field(default="zh-CN", max_length=5)
    """语言偏好"""

    timezone: int = Field(default=8, ge=-12, le=14)
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

    auth_identities: list["AuthIdentity"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    """用户的认证身份列表"""

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
        """转换为公开 DTO，排除敏感字段。需要预加载 group 关系。"""
        data = UserPublic.model_validate(self)
        data.group_name = self.group.name
        return data

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

            if filter_params.email_contains is not None:
                filter_conditions.append(cls.email.ilike(f"%{filter_params.email_contains}%"))

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
