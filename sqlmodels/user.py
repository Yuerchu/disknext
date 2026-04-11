import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Literal, TYPE_CHECKING, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import BigInteger, BinaryExpression, ClauseElement, and_
from sqlalchemy import update as sql_update
from sqlalchemy.sql.functions import func
from sqlmodel import Field, Relationship
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.main import RelationshipInfo

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, TableViewRequest, ListResponse, Str255

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
from .user_authn import AuthnDetailResponse  # noqa: E402

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

    storage: int = Field(default=0, sa_type=BigInteger, sa_column_kwargs={"server_default": "0"}, ge=0)
    """已用存储空间（字节）"""

    avatar: str | None = Field(default=None, max_length=255)
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

    def to_public(self) -> "UserPublic":
        """转换为公开 DTO，排除敏感字段。需要预加载 group 关系。"""
        data = UserPublic.model_validate(self)
        data.group_name = self.group.name
        return data

    # ==================== 登录流程 ====================

    @classmethod
    async def unified_login(
            cls,
            session: AsyncSession,
            request: "UnifiedLoginRequest",
            config: "ServerConfig",
    ) -> "TokenResponse":
        """
        统一登录入口，根据 provider 分发到不同的登录逻辑。

        :param session: 数据库会话
        :param request: 统一登录请求
        :param config: 服务器配置
        :return: TokenResponse
        """
        from utils import http_exceptions

        cls._check_provider_enabled(config, request.provider)

        match request.provider:
            case AuthProviderType.EMAIL_PASSWORD:
                user = await cls._login_email_password(session, request)
            case AuthProviderType.GITHUB:
                user = await cls._login_oauth(session, request, AuthProviderType.GITHUB, config)
            case AuthProviderType.QQ:
                user = await cls._login_oauth(session, request, AuthProviderType.QQ, config)
            case AuthProviderType.PASSKEY:
                user = await cls._login_passkey(session, request, config)
            case AuthProviderType.MAGIC_LINK:
                user = await cls._login_magic_link(session, request)
            case AuthProviderType.PHONE_SMS:
                http_exceptions.raise_not_implemented("短信登录暂未开放")
            case _:
                http_exceptions.raise_bad_request(f"不支持的登录方式: {request.provider}")

        return await user.issue_tokens(session)

    @staticmethod
    def _check_provider_enabled(
            config: "ServerConfig",
            provider: AuthProviderType,
    ) -> None:
        """检查认证方式是否已被站长启用"""
        from utils import http_exceptions

        provider_map = {
            AuthProviderType.GITHUB: config.is_github_enabled,
            AuthProviderType.QQ: config.is_qq_enabled,
            AuthProviderType.EMAIL_PASSWORD: config.is_auth_email_password_enabled,
            AuthProviderType.PHONE_SMS: config.is_auth_phone_sms_enabled,
            AuthProviderType.PASSKEY: config.is_auth_passkey_enabled,
            AuthProviderType.MAGIC_LINK: config.is_auth_magic_link_enabled,
        }
        is_enabled = provider_map.get(provider, False)
        if not is_enabled:
            http_exceptions.raise_bad_request(f"登录方式 {provider.value} 未启用")

    @classmethod
    async def _login_email_password(
            cls,
            session: AsyncSession,
            request: "UnifiedLoginRequest",
    ) -> "User":
        """邮箱+密码登录"""
        from loguru import logger as l
        from utils import http_exceptions
        from utils.password.pwd import Password, PasswordStatus
        from .auth_identity import AuthIdentity

        if not request.credential:
            http_exceptions.raise_bad_request("密码不能为空")

        # 查找 AuthIdentity
        identity: AuthIdentity | None = await AuthIdentity.get(
            session,
            (AuthIdentity.provider == AuthProviderType.EMAIL_PASSWORD)
            & (AuthIdentity.identifier == request.identifier),
        )
        if not identity:
            l.debug(f"未找到邮箱密码身份: {request.identifier}")
            http_exceptions.raise_unauthorized("邮箱或密码错误")

        # 验证密码
        if not identity.credential:
            http_exceptions.raise_unauthorized("邮箱或密码错误")

        if Password.verify(identity.credential, request.credential) != PasswordStatus.VALID:
            l.debug(f"密码验证失败: {request.identifier}")
            http_exceptions.raise_unauthorized("邮箱或密码错误")

        # 加载用户
        user: User = await cls.get(session, cls.id == identity.user_id, load=cls.group)
        if not user:
            http_exceptions.raise_unauthorized("用户不存在")

        # 验证用户状态
        if user.status != UserStatus.ACTIVE:
            http_exceptions.raise_forbidden("账户已被禁用")

        # 检查两步验证
        if identity.extra_data:
            import orjson
            extra: dict = orjson.loads(identity.extra_data)
            two_factor_secret: str | None = extra.get("two_factor")
            if two_factor_secret:
                if not request.two_fa_code:
                    l.debug(f"需要两步验证: {request.identifier}")
                    http_exceptions.raise_precondition_required("需要两步验证")
                if Password.verify_totp(two_factor_secret, request.two_fa_code) != PasswordStatus.VALID:
                    l.debug(f"两步验证失败: {request.identifier}")
                    http_exceptions.raise_unauthorized("两步验证码错误")

        return user

    @classmethod
    async def _login_oauth(
            cls,
            session: AsyncSession,
            request: "UnifiedLoginRequest",
            provider: AuthProviderType,
            config: "ServerConfig",
    ) -> "User":
        """
        OAuth 登录（GitHub / QQ）

        identifier 为 OAuth authorization code，后端换取 access_token 再获取用户信息。
        """
        from utils import http_exceptions
        from .auth_identity import AuthIdentity

        # 读取 OAuth 配置
        if provider == AuthProviderType.GITHUB:
            client_id = config.github_client_id
            client_secret = config.github_client_secret
        elif provider == AuthProviderType.QQ:
            client_id = config.qq_client_id
            client_secret = config.qq_client_secret
        else:
            http_exceptions.raise_bad_request(f"不支持的 OAuth 提供者: {provider.value}")

        if not client_id or not client_secret:
            http_exceptions.raise_bad_request(f"{provider.value} OAuth 未配置")

        # 根据 provider 创建对应的 OAuth 客户端
        if provider == AuthProviderType.GITHUB:
            from utils.oauth import GithubOAuth
            oauth_client = GithubOAuth(client_id, client_secret)
            token_resp = await oauth_client.get_access_token(code=request.identifier)
            user_info_resp = await oauth_client.get_user_info(token_resp)
            openid = str(user_info_resp.user_data.id)
            nickname = user_info_resp.user_data.name or user_info_resp.user_data.login
            avatar_url = user_info_resp.user_data.avatar_url
            email = user_info_resp.user_data.email
        elif provider == AuthProviderType.QQ:
            from utils.oauth import QQOAuth
            oauth_client = QQOAuth(client_id, client_secret)
            token_resp = await oauth_client.get_access_token(
                code=request.identifier,
                redirect_uri=request.redirect_uri or "",
            )
            openid_resp = await oauth_client.get_openid(token_resp.access_token)
            user_info_resp = await oauth_client.get_user_info(
                token_resp,
                app_id=client_id,
                openid=openid_resp.openid,
            )
            openid = openid_resp.openid
            nickname = user_info_resp.user_data.nickname
            avatar_url = user_info_resp.user_data.figureurl_qq_2 or user_info_resp.user_data.figureurl_2
            email = None
        else:
            http_exceptions.raise_bad_request(f"不支持的 OAuth 提供者: {provider.value}")

        # 查找已有 AuthIdentity
        identity: AuthIdentity | None = await AuthIdentity.get(
            session,
            (AuthIdentity.provider == provider) & (AuthIdentity.identifier == openid),
        )

        if identity:
            # 已绑定 → 更新 OAuth 信息并返回关联用户
            identity.display_name = nickname
            identity.avatar_url = avatar_url
            identity = await identity.save(session)

            user: User = await cls.get(session, cls.id == identity.user_id, load=cls.group)
            if not user:
                http_exceptions.raise_unauthorized("用户不存在")
            if user.status != UserStatus.ACTIVE:
                http_exceptions.raise_forbidden("账户已被禁用")
            return user

        # 未绑定 → 自动注册
        user = await cls._auto_register_oauth_user(
            session,
            config,
            provider=provider,
            openid=openid,
            nickname=nickname,
            avatar_url=avatar_url,
            email=email,
        )
        return user

    @classmethod
    async def _auto_register_oauth_user(
            cls,
            session: AsyncSession,
            config: "ServerConfig",
            *,
            provider: AuthProviderType,
            openid: str,
            nickname: str | None,
            avatar_url: str | None,
            email: str | None,
    ) -> "User":
        """OAuth 自动注册用户"""
        from loguru import logger as l
        from utils import http_exceptions
        from .auth_identity import AuthIdentity
        from .object import Object, ObjectType
        from .policy import Policy

        # 获取默认用户组
        if not config.default_group_id:
            l.error("默认用户组未配置")
            http_exceptions.raise_internal_error()

        default_group_id = config.default_group_id

        # 创建用户
        new_user = cls(
            email=email,
            nickname=nickname,
            avatar=avatar_url or "default",
            group_id=default_group_id,
        )
        new_user_id = new_user.id
        new_user = await new_user.save(session)

        # 创建 AuthIdentity
        identity = AuthIdentity(
            provider=provider,
            identifier=openid,
            display_name=nickname,
            avatar_url=avatar_url,
            is_primary=True,
            is_verified=True,
            user_id=new_user_id,
        )
        identity = await identity.save(session)

        # 创建用户根目录
        default_policy = await Policy.get(session, Policy.name == "本地存储")
        if default_policy:
            await Object(
                name="/",
                type=ObjectType.FOLDER,
                owner_id=new_user_id,
                parent_id=None,
                policy_id=default_policy.id,
            ).save(session)

        # 重新加载用户（含 group 关系）
        user: User = await cls.get(session, cls.id == new_user_id, load=cls.group)
        l.info(f"OAuth 自动注册用户: provider={provider.value}, openid={openid}")
        return user

    @classmethod
    async def _login_passkey(
            cls,
            session: AsyncSession,
            request: "UnifiedLoginRequest",
            config: "ServerConfig",
    ) -> "User":
        """
        Passkey/WebAuthn 登录（Discoverable Credentials 模式）

        identifier 为 challenge_token，credential 为 JSON 格式的 authenticator assertion response。
        """
        from loguru import logger as l
        from webauthn import verify_authentication_response
        from webauthn.helpers import base64url_to_bytes

        from utils import http_exceptions
        from utils.redis.challenge_store import ChallengeStore
        from .user_authn import UserAuthn

        if not request.credential:
            http_exceptions.raise_bad_request("WebAuthn assertion response 不能为空")

        if not request.identifier:
            http_exceptions.raise_bad_request("challenge_token 不能为空")

        # 从 ChallengeStore 取出 challenge（一次性，防重放）
        challenge: bytes | None = await ChallengeStore.retrieve_and_delete(f"auth:{request.identifier}")
        if challenge is None:
            http_exceptions.raise_unauthorized("登录会话已过期，请重新获取 options")

        # 从 assertion JSON 中解析 credential_id（Discoverable Credentials 模式）
        import orjson
        credential_dict: dict = orjson.loads(request.credential)
        credential_id_b64: str | None = credential_dict.get("id")
        if not credential_id_b64:
            http_exceptions.raise_bad_request("缺少凭证 ID")

        # 查找 UserAuthn 记录
        authn: UserAuthn | None = await UserAuthn.get(
            session,
            UserAuthn.credential_id == credential_id_b64,
        )
        if not authn:
            http_exceptions.raise_unauthorized("Passkey 凭证未注册")

        # 获取 RP 配置
        rp_id, _rp_name, origin = config.get_rp_config()

        # 验证 WebAuthn assertion
        try:
            verification = verify_authentication_response(
                credential=request.credential,
                expected_rp_id=rp_id,
                expected_origin=origin,
                expected_challenge=challenge,
                credential_public_key=base64url_to_bytes(authn.credential_public_key),
                credential_current_sign_count=authn.sign_count,
            )
        except Exception as e:
            l.warning(f"WebAuthn 验证失败: {e}")
            http_exceptions.raise_unauthorized("Passkey 验证失败")

        # 更新签名计数
        authn.sign_count = verification.new_sign_count
        authn = await authn.save(session)

        # 加载用户
        user: User = await cls.get(session, cls.id == authn.user_id, load=cls.group)
        if not user:
            http_exceptions.raise_unauthorized("用户不存在")
        if user.status != UserStatus.ACTIVE:
            http_exceptions.raise_forbidden("账户已被禁用")

        return user

    @classmethod
    async def _login_magic_link(
            cls,
            session: AsyncSession,
            request: "UnifiedLoginRequest",
    ) -> "User":
        """
        Magic Link 登录

        identifier 为签名 token，由 itsdangerous 生成。
        """
        from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

        from utils import JWT, http_exceptions
        from utils.redis.token_store import TokenStore
        from .auth_identity import AuthIdentity

        serializer = URLSafeTimedSerializer(JWT.SECRET_KEY)

        try:
            email = serializer.loads(request.identifier, salt="magic-link-salt", max_age=600)
        except SignatureExpired:
            http_exceptions.raise_unauthorized("Magic Link 已过期")
        except BadSignature:
            http_exceptions.raise_unauthorized("Magic Link 无效")

        # 防重放：使用 token 哈希作为标识符
        token_hash = hashlib.sha256(request.identifier.encode()).hexdigest()
        is_first_use = await TokenStore.mark_used(f"magic_link:{token_hash}", ttl=600)
        if not is_first_use:
            http_exceptions.raise_unauthorized("Magic Link 已被使用")

        # 查找绑定了该邮箱的 AuthIdentity（email_password 或 magic_link）
        identity: AuthIdentity | None = await AuthIdentity.get(
            session,
            (AuthIdentity.identifier == email)
            & (
                (AuthIdentity.provider == AuthProviderType.EMAIL_PASSWORD)
                | (AuthIdentity.provider == AuthProviderType.MAGIC_LINK)
            ),
        )
        if not identity:
            http_exceptions.raise_unauthorized("该邮箱未注册")

        user: User = await cls.get(session, cls.id == identity.user_id, load=cls.group)
        if not user:
            http_exceptions.raise_unauthorized("用户不存在")
        if user.status != UserStatus.ACTIVE:
            http_exceptions.raise_forbidden("账户已被禁用")

        # 标记邮箱已验证
        if not identity.is_verified:
            identity.is_verified = True
            identity = await identity.save(session)

        return user

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
        await session.execute(stmt)

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
