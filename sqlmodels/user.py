from datetime import datetime
from enum import StrEnum
from typing import Literal, TYPE_CHECKING, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr
from sqlalchemy import BinaryExpression, ClauseElement, and_
from sqlalchemy import update as sql_update
from sqlalchemy.sql.functions import func
from sqlmodel import Field, Relationship
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.main import RelationshipInfo
from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, TableViewRequest, ListResponse, NonNegativeBigInt, HttpUrl, Str32, Str64, Str128, Str255

from .auth_identity import AuthProviderType
from .color import ChromaticColor, NeutralColor, ThemeColorsBase
from .model_base import ResponseBase

T = TypeVar("T", bound="User")

if TYPE_CHECKING:
    from .auth_identity import AuthIdentity
    from .group import Group
    from .download import Download
    from .object import Object
    from .order import Order
    from .redeem import Redeem
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


# ==================== Base 模型 ====================

class UserBase(SQLModelBase):
    """用户基础字段，供数据库模型和 DTO 共享"""

    email: EmailStr
    """用户邮箱"""


# ==================== DTO 模型 ====================

class UnifiedLoginRequest(SQLModelBase):
    """统一登录请求 DTO"""

    provider: AuthProviderType
    """登录方式"""

    identifier: str = Field(min_length=1, max_length=255)
    """标识符（邮箱 / OAuth code / Magic Link token）"""

    credential: str | None = Field(default=None, max_length=255)
    """凭证（密码，provider=email_password 时必填）"""

    two_fa_code: str | None = Field(default=None, min_length=6, max_length=6)
    """两步验证代码"""

    captcha: Str255 | None = None
    """验证码"""


class WebAuthnInfo(SQLModelBase):
    """WebAuthn 信息 DTO"""

    credential_id: Str255
    """凭证 ID"""

    credential_public_key: Str255
    """凭证公钥"""

    sign_count: int = Field(ge=0)
    """签名计数器"""

    credential_device_type: bool
    """是否为平台认证器"""

    credential_backed_up: bool
    """凭证是否已备份"""

    transports: list[Str64] = Field(max_length=20)
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

    email: EmailStr
    """用户邮箱"""

    nickname: str = Field(max_length=32)
    """用户昵称"""

    avatar: Literal["default", "gravatar", "file"] = "default"
    """头像类型"""

    created_at: datetime
    """用户创建时间"""

    anonymous: bool = False
    """是否为匿名用户"""

    group: GroupResponse
    """用户所属用户组"""

    tags: list[str] = []
    """用户标签列表"""

class UserStorageResponse(SQLModelBase):
    """用户存储信息 DTO"""

    used: int = Field(ge=0)
    """已用存储空间（字节）"""

    free: int
    """剩余存储空间（字节）"""

    total: int = Field(ge=0)
    """总存储空间（字节）"""


class UserPublic(UserBase):
    """用户公开信息 DTO，用于 API 响应"""

    id: UUID
    """用户UUID"""

    nickname: Str32
    """昵称"""

    storage: int = Field(ge=0)
    """已用存储空间（字节）"""

    avatar: Str255 | None = None
    """头像地址"""

    group_expires: datetime
    """用户组过期时间"""

    group_id: UUID
    """所属用户组UUID"""

    group_name: Str255
    """用户组名称"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """更新时间"""


class UserSettingResponse(SQLModelBase):
    """用户设置响应 DTO"""

    id: UUID
    """用户UUID"""

    email: str
    """用户邮箱"""

    nickname: str = Field(max_length=32)
    """昵称"""

    created_at: datetime
    """用户注册时间"""

    group_name: str
    """用户所属用户组名称"""

    language: str
    """语言偏好"""

    timezone: int
    """时区"""

    authn: "list[AuthnDetailResponse] | None" = None
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

    email: EmailStr
    """接收 Magic Link 的邮箱"""

    captcha: Str255 | None = None
    """验证码"""


# ==================== 管理员用户管理 DTO ====================

class UserAdminCreateRequest(SQLModelBase):
    """管理员创建用户请求 DTO"""

    email: str | None = Field(default=None, max_length=50)
    """用户邮箱"""

    password: Str128 | None = Field(default=None, min_length=8)
    """用户密码（明文，由服务端加密；为空则不创建邮箱密码身份）"""

    nickname: str = Field(max_length=32)
    """昵称"""

    group_id: UUID
    """所属用户组UUID"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""


class UserAdminUpdateRequest(SQLModelBase):
    """管理员更新用户请求 DTO"""

    email: str | None = Field(default=None, max_length=50)
    """邮箱"""

    nickname: str = Field(max_length=32)
    """昵称"""

    phone: Str32 | None = None
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
from .user_authn import AuthnDetailResponse  # noqa: E402

# 更新前向引用
JWTPayload.model_rebuild()
UserResponse.model_rebuild()
UserSettingResponse.model_rebuild()


# ==================== 数据库模型 ====================

class User(UserBase, UUIDTableBaseMixin):
    """用户模型"""

    email: EmailStr = Field(max_length=50, unique=True, index=True)
    """用户邮箱（社交登录用户可能没有邮箱）"""

    nickname: str = Field(max_length=32)
    """昵称"""

    status: UserStatus = UserStatus.ACTIVE
    """用户状态"""

    storage: NonNegativeBigInt
    """已用存储空间（字节）"""

    avatar: HttpUrl | None = Field(default=None, max_length=255)
    """头像地址"""

    score: NonNegativeBigInt
    """用户积分"""

    group_expires: datetime | None = None
    """当前用户组过期时间"""

    # Option 相关字段
    theme_preset_id: UUID | None = Field(default=None, foreign_key="themepreset.id")
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
    redeems: list["Redeem"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "foreign_keys": "[Redeem.used_by]"
        }
    )
    """用户使用过的兑换码列表"""
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

    async def issue_tokens(self, session: AsyncSession) -> "TokenResponse":
        """
        签发 JWT 双令牌（access + refresh）

        :param session: 数据库会话
        :return: TokenResponse
        """
        from utils import JWT
        from .group import GroupOptions

        # 加载 GroupOptions
        group_options: GroupOptions | None = await GroupOptions.get(
            session,
            GroupOptions.group_id == self.group_id,
        )

        # 构建权限快照
        self.group.options = group_options
        group_claims = GroupClaims.from_group(self.group)

        # 创建令牌
        access_token = JWT.create_access_token(
            sub=self.id,
            jti=uuid4(),
            status=self.status.value,
            group=group_claims,
        )
        refresh_token = JWT.create_refresh_token(
            sub=self.id,
            jti=uuid4(),
        )

        return TokenResponse(
            access_token=access_token.access_token,
            access_expires=access_token.access_expires,
            refresh_token=refresh_token.refresh_token,
            refresh_expires=refresh_token.refresh_expires,
        )

    async def adjust_storage(
            self,
            session: AsyncSession,
            delta: int,
            commit: bool = True,
    ) -> None:
        """
        原子更新用户已用存储空间

        使用 SQL UPDATE SET storage = GREATEST(0, storage + delta) 避免竞态条件。

        :param session: 数据库会话
        :param delta: 变化量（正数增加，负数减少）
        :param commit: 是否立即提交
        """
        from loguru import logger as l

        if delta == 0:
            return

        stmt = (
            sql_update(User)
            .where(User.id == self.id)
            .values(storage=func.greatest(0, User.storage + delta))
        )
        await session.exec(stmt)

        if commit:
            await session.commit()

        l.debug(f"用户 {self.id} 存储配额变更: {'+' if delta > 0 else ''}{delta} bytes")

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
