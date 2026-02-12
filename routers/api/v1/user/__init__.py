from typing import Annotated, Literal
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException
from itsdangerous import URLSafeTimedSerializer
from loguru import logger
from webauthn import generate_registration_options
from webauthn.helpers import options_to_json_dict

import service
import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep, require_captcha
from service.captcha import CaptchaScene
from sqlmodels.auth_identity import AuthIdentity, AuthProviderType
from sqlmodels.user import UserStatus
from utils import JWT, Password, http_exceptions
from .settings import user_settings_router

user_router = APIRouter(
    prefix="/user",
    tags=["user"],
)

user_router.include_router(user_settings_router)


@user_router.post(
    path='/session',
    summary='用户登录（统一入口）',
    description='统一登录端点，支持多种认证方式。',
)
async def router_user_session(
    session: SessionDep,
    request: sqlmodels.UnifiedLoginRequest,
) -> sqlmodels.TokenResponse:
    """
    统一登录端点

    请求体：
    - provider: 登录方式（email_password / github / qq / passkey / magic_link）
    - identifier: 标识符（邮箱 / OAuth code / credential_id / magic link token）
    - credential: 凭证（密码 / WebAuthn assertion 等）
    - two_fa_code: 两步验证码（可选）
    - redirect_uri: OAuth 回调地址（可选）
    - captcha: 验证码（可选）

    错误处理：
    - 400: 登录方式未启用 / 参数错误
    - 401: 凭证错误
    - 403: 账户已禁用
    - 428: 需要两步验证
    - 501: 暂未实现的登录方式
    """
    return await service.user.unified_login(session, request)


@user_router.post(
    path='/session/refresh',
    summary="用刷新令牌刷新会话",
    description="Refresh the user session using a refresh token."
)
async def router_user_session_refresh(
    session: SessionDep,
    request: sqlmodels.RefreshTokenRequest,
) -> sqlmodels.TokenResponse:
    """
    使用 refresh_token 签发新的 access_token 和 refresh_token。

    流程：
    1. 解码 refresh_token JWT
    2. 验证 token_type 为 refresh
    3. 验证用户存在且状态正常
    4. 签发新的 access_token + refresh_token

    :param session: 数据库会话
    :param request: 刷新令牌请求
    :return: 新的 TokenResponse
    """

    try:
        payload = jwt.decode(request.refresh_token, JWT.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        http_exceptions.raise_unauthorized("刷新令牌无效或已过期")

    # 验证是 refresh token
    if payload.get("token_type") != "refresh":
        http_exceptions.raise_unauthorized("非刷新令牌")

    user_id_str = payload.get("sub")
    if not user_id_str:
        http_exceptions.raise_unauthorized("令牌缺少用户标识")

    user_id = UUID(user_id_str)
    user = await sqlmodels.User.get(session, sqlmodels.User.id == user_id, load=sqlmodels.User.group)
    if not user:
        http_exceptions.raise_unauthorized("用户不存在")

    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    # 加载 GroupOptions（获取最新权限）
    group_options = await sqlmodels.GroupOptions.get(
        session,
        sqlmodels.GroupOptions.group_id == user.group_id,
    )
    user.group.options = group_options
    group_claims = sqlmodels.GroupClaims.from_group(user.group)

    # 签发新令牌
    access_token = JWT.create_access_token(
        sub=user.id,
        jti=uuid4(),
        status=user.status.value,
        group=group_claims,
    )
    refresh_token = JWT.create_refresh_token(
        sub=user.id,
        jti=uuid4(),
    )

    return sqlmodels.TokenResponse(
        access_token=access_token.access_token,
        access_expires=access_token.access_expires,
        refresh_token=refresh_token.refresh_token,
        refresh_expires=refresh_token.refresh_expires,
    )

@user_router.post(
    path='/',
    summary='用户注册（统一入口）',
    description='User registration endpoint.',
    status_code=204,
)
async def router_user_register(
    session: SessionDep,
    request: sqlmodels.UnifiedRegisterRequest,
) -> None:
    """
    统一注册端点

    流程：
    1. 检查注册开关
    2. 检查 provider 启用
    3. 验证 identifier 唯一性（AuthIdentity 表）
    4. 创建 User + AuthIdentity + 根目录

    请求体：
    - provider: 注册方式（email_password / phone_sms）
    - identifier: 标识符（邮箱 / 手机号）
    - credential: 凭证（密码 / 短信验证码）
    - nickname: 昵称（可选）
    - captcha: 验证码（可选）

    错误处理：
    - 400: 注册未开放 / 参数错误
    - 409: 邮箱或手机号已存在
    - 501: 暂未实现的注册方式
    """
    # 1. 检查注册开关
    register_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == sqlmodels.SettingsType.REGISTER)
        & (sqlmodels.Setting.name == "register_enabled"),
    )
    if not register_setting or register_setting.value != "1":
        http_exceptions.raise_bad_request("注册功能未开放")

    # 2. 目前只支持 email_password 注册
    if request.provider == AuthProviderType.PHONE_SMS:
        http_exceptions.raise_not_implemented("短信注册暂未开放")
    elif request.provider != AuthProviderType.EMAIL_PASSWORD:
        http_exceptions.raise_bad_request("不支持的注册方式")

    # 3. 检查密码是否必填
    password_required_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == sqlmodels.SettingsType.AUTH)
        & (sqlmodels.Setting.name == "auth_password_required"),
    )
    is_password_required = not password_required_setting or password_required_setting.value != "0"
    if is_password_required and not request.credential:
        http_exceptions.raise_bad_request("密码不能为空")

    # 4. 验证 identifier 唯一性（AuthIdentity 表）
    existing_identity = await AuthIdentity.get(
        session,
        (AuthIdentity.provider == request.provider)
        & (AuthIdentity.identifier == request.identifier),
    )
    if existing_identity:
        raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 同时检查 User.email 唯一性（防止旧数据冲突）
    existing_user = await sqlmodels.User.get(
        session,
        sqlmodels.User.email == request.identifier,
    )
    if existing_user:
        raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 5. 获取默认用户组
    default_group_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == sqlmodels.SettingsType.REGISTER)
        & (sqlmodels.Setting.name == "default_group"),
    )
    if default_group_setting is None or not default_group_setting.value:
        logger.error("默认用户组不存在")
        http_exceptions.raise_internal_error()

    default_group_id = UUID(default_group_setting.value)
    default_group = await sqlmodels.Group.get(session, sqlmodels.Group.id == default_group_id)
    if not default_group:
        logger.error("默认用户组不存在")
        http_exceptions.raise_internal_error()

    # 6. 创建用户
    new_user = sqlmodels.User(
        email=request.identifier,
        nickname=request.nickname,
        group_id=default_group.id,
    )
    new_user_id = new_user.id
    await new_user.save(session)

    # 7. 创建 AuthIdentity
    hashed_password = Password.hash(request.credential) if request.credential else None
    identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier=request.identifier,
        credential=hashed_password,
        is_primary=True,
        is_verified=False,
        user_id=new_user_id,
    )
    await identity.save(session)

    # 8. 创建用户根目录
    default_policy = await sqlmodels.Policy.get(session, sqlmodels.Policy.name == "本地存储")
    if not default_policy:
        logger.error("默认存储策略不存在")
        http_exceptions.raise_internal_error()

    await sqlmodels.Object(
        name="/",
        type=sqlmodels.ObjectType.FOLDER,
        owner_id=new_user_id,
        parent_id=None,
        policy_id=default_policy.id,
    ).save(session)


@user_router.post(
    path='/magic-link',
    summary='发送 Magic Link 邮件',
    description='生成 Magic Link token 并发送到指定邮箱。',
    status_code=204,
)
async def router_user_magic_link(
    session: SessionDep,
    request: sqlmodels.MagicLinkRequest,
) -> None:
    """
    发送 Magic Link 邮件

    流程：
    1. 验证邮箱对应的 AuthIdentity 存在
    2. 生成签名 token
    3. 发送邮件（包含带 token 的链接）

    错误处理：
    - 400: Magic Link 未启用
    - 404: 邮箱未注册
    """
    # 检查 magic_link 是否启用
    magic_link_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == sqlmodels.SettingsType.AUTH)
        & (sqlmodels.Setting.name == "auth_magic_link_enabled"),
    )
    if not magic_link_setting or magic_link_setting.value != "1":
        http_exceptions.raise_bad_request("Magic Link 登录未启用")

    # 验证邮箱存在
    identity = await AuthIdentity.get(
        session,
        (AuthIdentity.identifier == request.email)
        & (
            (AuthIdentity.provider == AuthProviderType.EMAIL_PASSWORD)
            | (AuthIdentity.provider == AuthProviderType.MAGIC_LINK)
        ),
    )
    if not identity:
        http_exceptions.raise_not_found("该邮箱未注册")

    # 生成签名 token
    serializer = URLSafeTimedSerializer(JWT.SECRET_KEY)
    token = serializer.dumps(request.email, salt="magic-link-salt")

    # 获取站点 URL
    site_url_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == sqlmodels.SettingsType.BASIC)
        & (sqlmodels.Setting.name == "siteURL"),
    )
    site_url = site_url_setting.value if site_url_setting else "http://localhost"

    # TODO: 发送邮件（包含 {site_url}/auth/magic-link?token={token}）
    logger.info(f"Magic Link token 已生成: {token} (邮件发送待实现)")


@user_router.post(
    path='/code',
    summary='发送验证码邮件',
    description='Send a verification code email.',
)
def router_user_email_code(
    reason: Literal['register', 'reset'] = 'register',
) -> sqlmodels.ResponseBase:
    """
    Send a verification code email.

    Returns:
        dict: A dictionary containing information about the password reset email.
    """
    http_exceptions.raise_not_implemented()

@user_router.get(
    path='/profile/{id}',
    summary='获取用户主页展示用分享',
    description='Get user profile for display.',
)
def router_user_profile(id: str) -> sqlmodels.ResponseBase:
    """
    Get user profile for display.

    Args:
        id (str): The user ID.

    Returns:
        dict: A dictionary containing user profile information.
    """
    http_exceptions.raise_not_implemented()

@user_router.get(
    path='/avatar/{id}/{size}',
    summary='获取用户头像',
    description='Get user avatar by ID and size.',
)
def router_user_avatar(id: str, size: int = 128) -> sqlmodels.ResponseBase:
    """
    Get user avatar by ID and size.

    Args:
        id (str): The user ID.
        size (int): The size of the avatar image.

    Returns:
        str: A Base64 encoded string of the user avatar image.
    """
    http_exceptions.raise_not_implemented()

#####################
# 需要登录的接口
#####################

@user_router.get(
    path='/me',
    summary='获取用户信息',
    description='Get user information.',
    dependencies=[Depends(dependency=auth_required)],
    response_model=sqlmodels.UserResponse,
)
async def router_user_me(
    session: SessionDep,
    user: Annotated[sqlmodels.User, Depends(auth_required)],
) -> sqlmodels.UserResponse:
    """
    获取用户信息.

    :return: ResponseBase containing user information.
    :rtype: ResponseBase
    """
    # 加载 group 及其 options 关系
    group = await sqlmodels.Group.get(
        session,
        sqlmodels.Group.id == user.group_id,
        load=sqlmodels.Group.options
    )

    # 构建 GroupResponse
    group_response = group.to_response() if group else None

    # 异步加载 tags 关系
    user_tags = await user.awaitable_attrs.tags

    return sqlmodels.UserResponse(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        avatar=user.avatar,
        created_at=user.created_at,
        group=group_response,
        tags=[tag.name for tag in user_tags] if user_tags else [],
    )

@user_router.get(
    path='/storage',
    summary='存储信息',
    description='Get user storage information.',
    dependencies=[Depends(auth_required)],
)
async def router_user_storage(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> sqlmodels.UserStorageResponse:
    """
    获取用户存储空间信息。
    """
    # 获取用户组的基础存储容量
    group = await sqlmodels.Group.get(session, sqlmodels.Group.id == user.group_id)
    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")

    # [TODO] 总空间加上用户购买的额外空间

    total: int = group.max_storage
    used: int = user.storage
    free: int = max(0, total - used)

    return sqlmodels.UserStorageResponse(
        used=used,
        free=free,
        total=total,
    )

@user_router.put(
    path='/authn/start',
    summary='注册 Passkey 凭证（初始化）',
    description='Initialize Passkey registration for a user.',
    dependencies=[Depends(auth_required)],
)
async def router_user_authn_start(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> sqlmodels.ResponseBase:
    """
    Passkey 注册初始化（需要登录）

    返回 WebAuthn registration options，前端使用 navigator.credentials.create() 处理。

    错误处理：
    - 400: Passkey 未启用
    """
    authn_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == "authn") & (sqlmodels.Setting.name == "authn_enabled")
    )
    if not authn_setting or authn_setting.value != "1":
        raise HTTPException(status_code=400, detail="Passkey 未启用")

    site_url_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == "basic") & (sqlmodels.Setting.name == "siteURL")
    )
    site_title_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == "basic") & (sqlmodels.Setting.name == "siteTitle")
    )

    options = generate_registration_options(
        rp_id=site_url_setting.value if site_url_setting else "",
        rp_name=site_title_setting.value if site_title_setting else "",
        user_name=user.email or str(user.id),
        user_display_name=user.nickname or user.email or str(user.id),
    )

    return sqlmodels.ResponseBase(data=options_to_json_dict(options))

@user_router.put(
    path='/authn/finish',
    summary='注册 Passkey 凭证（完成）',
    description='Finish Passkey registration for a user.',
    dependencies=[Depends(auth_required)],
)
def router_user_authn_finish() -> sqlmodels.ResponseBase:
    """
    Passkey 注册完成（需要登录）

    接收前端 navigator.credentials.create() 返回的凭证数据，
    创建 UserAuthn 行 + AuthIdentity(provider=passkey)。

    Returns:
        dict: A dictionary containing Passkey registration information.
    """
    http_exceptions.raise_not_implemented()
