from typing import Annotated, Literal
from uuid import UUID, uuid4

import json

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer
from loguru import logger
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

import service
import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep, ServerConfigDep, require_captcha
from service.captcha import CaptchaScene
from service.redis.challenge_store import ChallengeStore
from service.webauthn import get_rp_config
from sqlmodels.auth_identity import AuthIdentity, AuthProviderType
from sqlmodels.user import UserStatus
from sqlmodels.user_authn import UserAuthn
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
    config: ServerConfigDep,
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
    return await service.user.unified_login(session, request, config)


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
    config: ServerConfigDep,
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
    if not config.default_group_id:
        logger.error("默认用户组未配置")
        http_exceptions.raise_internal_error()

    default_group_id = config.default_group_id
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
    new_user = await new_user.save(session)

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
    identity = await identity.save(session)

    # 8. 创建用户根目录（使用用户组关联的第一个存储策略）
    await session.refresh(default_group, ['policies'])
    if not default_group.policies:
        logger.error("默认用户组未关联任何存储策略")
        http_exceptions.raise_internal_error()
    default_policy = default_group.policies[0]

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

    from service.avatar import (
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

@user_router.put(
    path='/authn/start',
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

    rp_id, rp_name, _origin = get_rp_config(config)

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
    path='/authn/finish',
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

    rp_id, _rp_name, origin = get_rp_config(config)

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

    # 创建 AuthIdentity（provider=passkey，identifier=credential_id_b64）
    identity = AuthIdentity(
        provider=AuthProviderType.PASSKEY,
        identifier=credential_id_b64,
        is_primary=False,
        is_verified=True,
        user_id=user.id,
    )
    identity = await identity.save(session)

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

    rp_id, _rp_name, _origin = get_rp_config(config)

    options = generate_authentication_options(rp_id=rp_id)

    # 生成 challenge_token 用于关联 challenge
    challenge_token: str = str(uuid4())
    await ChallengeStore.store(f"auth:{challenge_token}", options.challenge)

    result: dict = json.loads(options_to_json(options))
    result["challenge_token"] = challenge_token
    return result
