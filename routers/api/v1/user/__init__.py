import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

import jwt
import orjson
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel_ext import rel, cond
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep, ServerConfigDep, require_captcha
from sqlmodels.auth_identity import AuthProviderType
from sqlmodels.group import Group
from sqlmodels.server_config import ServerConfig
from sqlmodels.user import User, UserStatus
from sqlmodels.user_authn import UserAuthn
from utils import JWT, Password, http_exceptions
from utils.conf import appmeta
from utils.captcha import CaptchaScene
from utils.password.pwd import PasswordStatus
from utils.redis.challenge_store import ChallengeStore
from utils.redis.token_store import TokenStore
from .settings import user_settings_router

user_router = APIRouter(
    prefix="/user",
    tags=["user"],
)

user_router.include_router(user_settings_router)


# ==================== 登录流程辅助函数 ====================


def _check_provider_enabled(config: ServerConfig, provider: AuthProviderType) -> None:
    """检查认证方式是否已被站长启用"""
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


async def _login_email_password(
        session: AsyncSession,
        request: sqlmodels.UnifiedAuthRequest,
) -> User:
    """邮箱+密码登录"""
    if not request.credential:
        http_exceptions.raise_bad_request("密码不能为空")

    user: User | None = await User.get(session, cond(User.email == request.identifier), load=rel(User.group))
    if not user or not user.password_hash:
        logger.debug(f"未找到邮箱密码身份: {request.identifier}")
        http_exceptions.raise_unauthorized("邮箱或密码错误")

    if Password.verify(user.password_hash, request.credential) != PasswordStatus.VALID:
        logger.debug(f"密码验证失败: {request.identifier}")
        http_exceptions.raise_unauthorized("邮箱或密码错误")

    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    # 检查两步验证
    if user.two_factor_secret:
        if not request.two_fa_code:
            logger.debug(f"需要两步验证: {request.identifier}")
            http_exceptions.raise_precondition_required("需要两步验证")
        if Password.verify_totp(user.two_factor_secret, request.two_fa_code) != PasswordStatus.VALID:
            logger.debug(f"两步验证失败: {request.identifier}")
            http_exceptions.raise_unauthorized("两步验证码错误")

    return user


async def _login_oauth(
        session: AsyncSession,
        request: sqlmodels.UnifiedAuthRequest,
        provider: AuthProviderType,
        config: ServerConfig,
) -> User:
    """
    OAuth 登录（GitHub / QQ）

    identifier 为 OAuth authorization code，后端换取 access_token 再获取用户信息。
    """
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

    # 按 provider 查找已绑定的用户
    if provider == AuthProviderType.GITHUB:
        user: User | None = await User.get(session, cond(User.github_id == openid), load=rel(User.group))
    elif provider == AuthProviderType.QQ:
        user: User | None = await User.get(session, cond(User.qq_id == openid), load=rel(User.group))
    else:
        http_exceptions.raise_bad_request(f"不支持的 OAuth 提供者: {provider.value}")

    if user:
        if user.status != UserStatus.ACTIVE:
            http_exceptions.raise_forbidden("账户已被禁用")
        return user

    # 未绑定 → 自动注册
    user = await _auto_register_oauth_user(
        session,
        config,
        provider=provider,
        openid=openid,
        nickname=nickname,
        avatar_url=avatar_url,
        email=email,
    )
    return user


async def _auto_register_oauth_user(
        session: AsyncSession,
        config: ServerConfig,
        *,
        provider: AuthProviderType,
        openid: str,
        nickname: str | None,
        avatar_url: str | None,
        email: str | None,
) -> User:
    """OAuth 自动注册用户"""
    # 获取默认用户组
    if not config.default_group_id:
        logger.error("默认用户组未配置")
        http_exceptions.raise_internal_error()

    default_group_id = config.default_group_id
    default_group = await Group.get_exist_one(session, default_group_id)

    # 构建 OAuth 字段
    oauth_fields: dict = {}
    if provider == AuthProviderType.GITHUB:
        oauth_fields["github_id"] = openid
    elif provider == AuthProviderType.QQ:
        oauth_fields["qq_id"] = openid

    new_user = User(
        email=email,
        nickname=nickname,
        avatar=avatar_url or "default",
        group_id=default_group_id,
        scopes=default_group.default_scopes,
        **oauth_fields,
    )
    new_user_id = new_user.id
    new_user = await new_user.save(session)

    # 创建用户根目录
    default_policy = await sqlmodels.Policy.get(session, sqlmodels.Policy.name == "本地存储")
    if default_policy:
        await sqlmodels.Entry(
            name="/",
            type=sqlmodels.EntryType.FOLDER,
            owner_id=new_user_id,
            parent_id=None,
            policy_id=default_policy.id,
        ).save(session)

    # 重新加载用户（含 group 关系）
    user: User = await User.get_exist_one(session, new_user_id, load=rel(User.group))
    logger.info(f"OAuth 自动注册用户: provider={provider.value}, openid={openid}")
    return user


async def _login_passkey(
        session: AsyncSession,
        request: sqlmodels.UnifiedAuthRequest,
        config: ServerConfig,
) -> User:
    """
    Passkey/WebAuthn 登录（Discoverable Credentials 模式）

    identifier 为 challenge_token，credential 为 JSON 格式的 authenticator assertion response。
    """
    if not request.credential:
        http_exceptions.raise_bad_request("WebAuthn assertion response 不能为空")

    if not request.identifier:
        http_exceptions.raise_bad_request("challenge_token 不能为空")

    # 从 ChallengeStore 取出 challenge（一次性，防重放）
    challenge: bytes | None = await ChallengeStore.retrieve_and_delete(f"auth:{request.identifier}")
    if challenge is None:
        http_exceptions.raise_unauthorized("登录会话已过期，请重新获取 options")

    # 从 assertion JSON 中解析 credential_id（Discoverable Credentials 模式）
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
        logger.warning(f"WebAuthn 验证失败: {e}")
        http_exceptions.raise_unauthorized("Passkey 验证失败")

    # 更新签名计数
    authn.sign_count = verification.new_sign_count
    authn = await authn.save(session)

    # 加载用户
    user: User = await User.get_exist_one(session, authn.user_id, load=rel(User.group))
    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    return user


async def _login_magic_link(
        session: AsyncSession,
        request: sqlmodels.UnifiedAuthRequest,
) -> User:
    """
    Magic Link 登录

    identifier 为签名 token，由 itsdangerous 生成。
    """
    serializer = URLSafeTimedSerializer(appmeta.secret_key)

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

    user: User = await User.get_exist_one(session, User.email == email, load=rel(User.group))
    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    return user


# ==================== 端点 ====================


@user_router.post(
    path='/session',
    summary='用户登录（统一入口）',
    description='统一登录端点，支持多种认证方式。',
)
async def router_user_session(
    session: SessionDep,
    config: ServerConfigDep,
    request: sqlmodels.UnifiedAuthRequest,
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
    _check_provider_enabled(config, request.provider)

    match request.provider:
        case AuthProviderType.EMAIL_PASSWORD:
            user = await _login_email_password(session, request)
        case AuthProviderType.GITHUB:
            user = await _login_oauth(session, request, AuthProviderType.GITHUB, config)
        case AuthProviderType.QQ:
            user = await _login_oauth(session, request, AuthProviderType.QQ, config)
        case AuthProviderType.PASSKEY:
            user = await _login_passkey(session, request, config)
        case AuthProviderType.MAGIC_LINK:
            user = await _login_magic_link(session, request)
        case AuthProviderType.PHONE_SMS:
            http_exceptions.raise_not_implemented("短信登录暂未开放")
        case _:
            http_exceptions.raise_bad_request(f"不支持的登录方式: {request.provider}")

    return await user.issue_tokens(session)


@user_router.post(
    path='/session/refresh',
    summary="用刷新令牌刷新会话",
    description="客户端在 Authorization header 中传递 refresh_token，验证后签发新的双令牌。"
)
async def router_user_session_refresh(
    session: SessionDep,
    token: Annotated[str, Depends(JWT.oauth2_scheme)],
) -> sqlmodels.TokenResponse:
    """
    使用 refresh_token 签发新的 access_token 和 refresh_token

    认证：Authorization: Bearer <refresh_token>

    流程：
    1. 从 Authorization header 解码 refresh_token JWT
    2. 验证 token_type 为 refresh
    3. 验证用户存在且状态正常
    4. 签发新的 access_token + refresh_token
    """
    try:
        payload = jwt.decode(token, appmeta.secret_key, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        http_exceptions.raise_unauthorized("刷新令牌无效或已过期")

    if payload.get("token_type") != "refresh":
        http_exceptions.raise_unauthorized("非刷新令牌")

    user_id_str = payload.get("sub")
    if not user_id_str:
        http_exceptions.raise_unauthorized("令牌缺少用户标识")

    user: User = await User.get_exist_one(session, UUID(user_id_str), load=rel(User.group))

    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    return await user.issue_tokens(session)

@user_router.post(
    path='/',
    summary='用户注册（统一入口）',
    description='User registration endpoint.',
    status_code=204,
)
async def router_user_register(
    session: SessionDep,
    config: ServerConfigDep,
    request: sqlmodels.UnifiedAuthRequest,
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
    if not config.is_register_enabled:
        http_exceptions.raise_bad_request("注册功能未开放")

    # 2. 目前只支持 email_password 注册
    if request.provider == AuthProviderType.PHONE_SMS:
        http_exceptions.raise_not_implemented("短信注册暂未开放")
    elif request.provider != AuthProviderType.EMAIL_PASSWORD:
        http_exceptions.raise_bad_request("不支持的注册方式")

    # 3. 检查密码是否必填
    if config.is_auth_password_required and not request.credential:
        http_exceptions.raise_bad_request("密码不能为空")

    # 4. 验证邮箱唯一性
    existing_user = await sqlmodels.User.get(
        session,
        sqlmodels.User.email == request.identifier,
    )
    if existing_user:
        raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 5. 获取默认用户组
    if not config.default_group_id:
        logger.error("默认用户组未配置")
        http_exceptions.raise_internal_error()

    default_group_id = config.default_group_id
    default_group = await sqlmodels.Group.get(session, sqlmodels.Group.id == default_group_id)
    if not default_group:
        logger.error("默认用户组不存在")
        http_exceptions.raise_internal_error()

    # 6. 创建用户（密码哈希直接存 User 表）
    hashed_password = Password.hash(request.credential) if request.credential else None
    new_user = sqlmodels.User(
        email=request.identifier,
        nickname=request.identifier,
        group_id=default_group.id,
        password_hash=hashed_password,
        scopes=default_group.default_scopes,
    )
    new_user_id = new_user.id
    new_user = await new_user.save(session)

    # 8. 创建用户根目录（使用用户组关联的第一个存储策略）
    await session.refresh(default_group, ['policies'])
    if not default_group.policies:
        logger.error("默认用户组未关联任何存储策略")
        http_exceptions.raise_internal_error()
    default_policy = default_group.policies[0]

    await sqlmodels.Entry(
        name="/",
        type=sqlmodels.EntryType.FOLDER,
        owner_id=new_user_id,
        parent_id=None,
        policy_id=default_policy.id,
    ).save(session)


@user_router.post(
    path='/magic_link',
    summary='发送 Magic Link 邮件',
    description='生成 Magic Link token 并发送到指定邮箱。',
    status_code=204,
)
async def router_user_magic_link(
    session: SessionDep,
    config: ServerConfigDep,
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
    if not config.is_auth_magic_link_enabled:
        http_exceptions.raise_bad_request("Magic Link 登录未启用")

    # 验证邮箱存在
    user = await User.get(session, User.email == request.email)
    if not user:
        http_exceptions.raise_not_found("该邮箱未注册")

    # 生成签名 token
    serializer = URLSafeTimedSerializer(appmeta.secret_key)
    token = serializer.dumps(request.email, salt="magic-link-salt")

    # 获取站点 URL
    site_url = config.site_url

    # TODO: 发送邮件（包含 {site_url}/auth/magic-link?token={token}）
    logger.info(f"Magic Link token 已为 {request.email} 生成 (邮件发送待实现)")


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
    response_model=None,
)
async def router_user_avatar(
        session: SessionDep,
        config: ServerConfigDep,
        id: UUID,
        size: int = 128,
) -> FileResponse | RedirectResponse:
    """
    获取指定用户指定尺寸的头像（公开端点，无需认证）

    路径参数：
    - id: 用户 UUID
    - size: 请求的头像尺寸（px），默认 128

    行为：
    - default: 302 重定向到 Gravatar identicon
    - gravatar: 302 重定向到 Gravatar（使用用户邮箱 MD5）
    - file: 返回本地 WebP 文件

    响应：
    - 200: image/webp（file 模式）
    - 302: 重定向到外部 URL（default/gravatar 模式）
    - 404: 用户不存在

    缓存：Cache-Control: public, max-age=3600
    """
    import aiofiles.os

    from utils.avatar import (
        get_avatar_file_path,
        get_avatar_settings,
        gravatar_url,
        resolve_avatar_size,
    )

    user = await sqlmodels.User.get(session, sqlmodels.User.id == id)
    if not user:
        http_exceptions.raise_not_found("用户不存在")

    avatar_path, _, size_l, size_m, size_s = await get_avatar_settings(session)

    if user.avatar == "file":
        size_label = resolve_avatar_size(size, size_l, size_m, size_s)
        file_path = get_avatar_file_path(avatar_path, user.id, size_label)

        if not await aiofiles.os.path.exists(file_path):
            # 文件丢失，降级为 identicon
            fallback_url = gravatar_url(str(user.id), size, "https://www.gravatar.com/")
            return RedirectResponse(url=fallback_url, status_code=302)

        return FileResponse(
            path=file_path,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    elif user.avatar == "gravatar":
        server = config.gravatar_server
        email = user.email or str(user.id)
        url = gravatar_url(email, size, server)
        return RedirectResponse(url=url, status_code=302)

    else:
        # default: identicon
        email_or_id = user.email or str(user.id)
        url = gravatar_url(email_or_id, size, "https://www.gravatar.com/")
        return RedirectResponse(url=url, status_code=302)

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
    # 重新加载用户并预取 tags 关系（sqlmodel_ext 默认 lazy='raise_on_sql'）
    user = await sqlmodels.User.get(
        session,
        sqlmodels.User.id == user.id,
        load=sqlmodels.User.tags,
    )

    # 加载 group
    group = await sqlmodels.Group.get(
        session,
        sqlmodels.Group.id == user.group_id,
    )

    # 构建 GroupResponse
    group_response = group.to_response() if group else None

    return sqlmodels.UserResponse(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        avatar=user.avatar,
        created_at=user.created_at,
        group=group_response,
        tags=[tag.name for tag in user.tags] if user.tags else [],
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

    # 查询用户所有未过期容量包的 size 总和
    from datetime import datetime
    from sqlalchemy import func, select, and_, or_

    now = datetime.now()
    stmt = select(func.coalesce(func.sum(sqlmodels.StoragePack.size), 0)).where(
        and_(
            sqlmodels.StoragePack.user_id == user.id,
            or_(
                sqlmodels.StoragePack.expired_time.is_(None),
                sqlmodels.StoragePack.expired_time > now,
            ),
        )
    )
    result = await session.exec(stmt)
    active_packs_total: int = result.scalar_one()

    total: int = group.max_storage + active_packs_total
    used: int = user.storage
    free: int = max(0, total - used)

    return sqlmodels.UserStorageResponse(
        used=used,
        free=free,
        total=total,
    )

@user_router.post(
    path='/authn/registration',
    summary='注册 Passkey 凭证（初始化）',
    description='Initialize Passkey registration for a user.',
    dependencies=[Depends(auth_required)],
)
async def router_user_authn_start(
    session: SessionDep,
    config: ServerConfigDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> dict:
    """
    Passkey 注册初始化（需要登录）

    返回 WebAuthn registration options，前端使用 navigator.credentials.create() 处理。

    错误处理：
    - 400: Passkey 未启用
    """
    if not config.is_authn_enabled:
        http_exceptions.raise_bad_request("Passkey 未启用")

    rp_id, rp_name, _origin = config.get_rp_config()

    # 查询用户已注册凭证，用于 exclude_credentials
    existing_authns: list[UserAuthn] = await UserAuthn.get(
        session,
        UserAuthn.user_id == user.id,
        fetch_mode="all",
    )
    exclude_credentials: list[PublicKeyCredentialDescriptor] = [
        PublicKeyCredentialDescriptor(
            id=authn.credential_id,
            transports=authn.transports.split(",") if authn.transports else [],
        )
        for authn in existing_authns
    ]

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=user.id.bytes,
        user_name=user.email or str(user.id),
        user_display_name=user.nickname or user.email or str(user.id),
        exclude_credentials=exclude_credentials if exclude_credentials else None,
    )

    # 存储 challenge
    await ChallengeStore.store(f"reg:{user.id}", options.challenge)

    return json.loads(options_to_json(options))


@user_router.put(
    path='/authn/registration',
    summary='注册 Passkey 凭证（完成）',
    description='Finish Passkey registration for a user.',
    dependencies=[Depends(auth_required)],
    status_code=201,
)
async def router_user_authn_finish(
    session: SessionDep,
    config: ServerConfigDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
    request: sqlmodels.AuthnFinishRequest,
) -> sqlmodels.AuthnDetailResponse:
    """
    Passkey 注册完成（需要登录）

    接收前端 navigator.credentials.create() 返回的凭证数据，
    验证后创建 UserAuthn 行 + AuthIdentity(provider=passkey)。

    请求体：
    - credential: navigator.credentials.create() 返回的 JSON 字符串
    - name: 凭证名称（可选）

    错误处理：
    - 400: challenge 已过期或无效 / 验证失败
    """
    # 取出 challenge（一次性）
    challenge: bytes | None = await ChallengeStore.retrieve_and_delete(f"reg:{user.id}")
    if challenge is None:
        http_exceptions.raise_bad_request("注册会话已过期，请重新开始")

    rp_id, _rp_name, origin = config.get_rp_config()

    # 验证注册响应
    try:
        verification = verify_registration_response(
            credential=request.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except Exception as e:
        logger.warning(f"WebAuthn 注册验证失败: {e}")
        http_exceptions.raise_bad_request("Passkey 验证失败")

    # 编码为 base64url 存储
    credential_id_b64: str = bytes_to_base64url(verification.credential_id)
    credential_public_key_b64: str = bytes_to_base64url(verification.credential_public_key)

    # 提取 transports
    credential_dict: dict = json.loads(request.credential)
    response_dict: dict = credential_dict.get("response", {})
    transports_list: list[str] = response_dict.get("transports", [])
    transports_str: str | None = ",".join(transports_list) if transports_list else None

    # 创建 UserAuthn 记录
    authn = UserAuthn(
        credential_id=credential_id_b64,
        credential_public_key=credential_public_key_b64,
        sign_count=verification.sign_count,
        credential_device_type=verification.credential_device_type,
        credential_backed_up=verification.credential_backed_up,
        transports=transports_str,
        name=request.name,
        user_id=user.id,
    )
    authn = await authn.save(session)

    return authn.to_detail_response()


@user_router.post(
    path='/authn/options',
    summary='获取 Passkey 登录 options（无需登录）',
    description='Generate authentication options for Passkey login.',
)
async def router_user_authn_options(
    config: ServerConfigDep,
) -> dict:
    """
    获取 Passkey 登录的 authentication options（无需登录）

    前端调用此端点获取 options 后使用 navigator.credentials.get() 处理。
    使用 Discoverable Credentials 模式（空 allow_credentials），
    由浏览器/平台决定展示哪些凭证。

    返回值包含 ``challenge_token`` 字段，前端在登录请求中作为 ``identifier`` 传入。

    错误处理：
    - 400: Passkey 未启用
    """
    if not config.is_authn_enabled:
        http_exceptions.raise_bad_request("Passkey 未启用")

    rp_id, _rp_name, _origin = config.get_rp_config()

    options = generate_authentication_options(rp_id=rp_id)

    # 生成 challenge_token 用于关联 challenge
    challenge_token: str = str(uuid4())
    await ChallengeStore.store(f"auth:{challenge_token}", options.challenge)

    result: dict = json.loads(options_to_json(options))
    result["challenge_token"] = challenge_token
    return result
