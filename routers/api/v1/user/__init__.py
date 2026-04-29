import json
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

import aiofiles.os
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from loguru import logger
from sqlalchemy import func, select, and_, or_
from sqlmodel_ext import rel
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep, ServerConfigDep
from sqlmodels.auth_identity import AuthProviderType
from sqlmodels.group import GroupResponse
from sqlmodels.mail_template import MailTemplateType
from sqlmodels.user import AvatarType, User, UserStatus
from sqlmodels.user_authn import UserAuthn
from utils import JWT, Password, http_exceptions
from utils.http.error_codes import ErrorCode as E
from utils.conf import appmeta
from utils.mail import MailService
from utils.redis.challenge_store import ChallengeStore
from utils.redis.verify_code_store import VerifyCodeStore

from .deps import check_provider_enabled, login_email_password, login_oauth, login_passkey, login_phone_sms
from .settings import user_settings_router

user_router = APIRouter(
    prefix="/user",
    tags=["user"],
)

user_router.include_router(user_settings_router)


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
    - provider: 登录方式（email_password / github / qq / passkey）
    - identifier: 标识符（邮箱 / OAuth code / credential_id）
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
    check_provider_enabled(config, request.provider)

    match request.provider:
        case AuthProviderType.EMAIL_PASSWORD:
            user = await login_email_password(session, request)
        case AuthProviderType.GITHUB:
            user = await login_oauth(session, request, AuthProviderType.GITHUB, config)
        case AuthProviderType.QQ:
            user = await login_oauth(session, request, AuthProviderType.QQ, config)
        case AuthProviderType.PASSKEY:
            user = await login_passkey(session, request, config)
        case AuthProviderType.PHONE_SMS:
            user = await login_phone_sms(session, request, config)
        case _:
            http_exceptions.raise_bad_request(E.AUTH_PROVIDER_UNSUPPORTED, f"不支持的登录方式: {request.provider}")

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
        http_exceptions.raise_unauthorized(E.AUTH_REFRESH_TOKEN_INVALID, "刷新令牌无效或已过期")

    if payload.get("token_type") != "refresh":
        http_exceptions.raise_unauthorized(E.AUTH_REFRESH_TOKEN_TYPE, "非刷新令牌")

    user_id_str = payload.get("sub")
    if not user_id_str:
        http_exceptions.raise_unauthorized(E.AUTH_TOKEN_MISSING_SUB, "令牌缺少用户标识")

    user: User = await User.get_exist_one(session, UUID(user_id_str), load=rel(User.group))

    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden(E.AUTH_ACCOUNT_DISABLED, "账户已被禁用")

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
        http_exceptions.raise_bad_request(E.USER_REGISTRATION_CLOSED, "注册功能未开放")

    # 2. 目前只支持 email_password 注册
    if request.provider == AuthProviderType.PHONE_SMS:
        http_exceptions.raise_not_implemented(message="短信注册暂未开放")
    elif request.provider != AuthProviderType.EMAIL_PASSWORD:
        http_exceptions.raise_bad_request(E.USER_REGISTRATION_UNSUPPORTED, "不支持的注册方式")

    # 3. 检查密码是否必填
    if config.is_auth_password_required and not request.credential:
        http_exceptions.raise_bad_request(E.USER_PASSWORD_EMPTY, "密码不能为空")

    # 4. 验证邮箱唯一性
    existing_user = await sqlmodels.User.get(
        session,
        sqlmodels.User.email == request.identifier,
    )
    if existing_user:
        http_exceptions.raise_conflict(E.USER_EMAIL_EXISTS, "该邮箱已被注册")

    # 5. 邮箱激活验证码校验
    if config.is_require_active:
        if not request.verify_code:
            http_exceptions.raise_bad_request(E.MAIL_CODE_INVALID, "需要邮箱验证码")
        valid = await VerifyCodeStore.verify_and_delete("register", request.identifier, request.verify_code)
        if not valid:
            http_exceptions.raise_bad_request(E.MAIL_CODE_INVALID, "验证码错误或已过期")

    # 6. 获取默认用户组
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
    new_user = await new_user.save(session)

    # 8. 创建用户根目录（使用用户组关联的第一个存储策略）
    await session.refresh(default_group, ['policies'])
    if not default_group.policies:
        logger.error("默认用户组未关联任何存储策略")
        http_exceptions.raise_internal_error()
    default_policy = default_group.policies[0]

    _ = await sqlmodels.Entry(
        name="/",
        type=sqlmodels.EntryType.FOLDER,
        owner_id=new_user.id,
        parent_id=None,
        policy_id=default_policy.id,
    ).save(session)


@user_router.post(
    path='/code',
    summary='发送验证码',
    description='发送 6 位数字验证码到指定邮箱或手机号，用于注册激活或密码重置。',
    status_code=204,
)
async def router_user_send_code(
    session: SessionDep,
    config: ServerConfigDep,
    request: sqlmodels.SendCodeRequest,
) -> None:
    """
    发送验证码（邮件或短信）

    流程：
    1. 根据 channel 验证参数
    2. 根据 reason 校验邮箱/手机号状态
    3. 限流检查 + 生成验证码
    4. 发送邮件或短信

    错误处理：
    - 400: 参数缺失
    - 409: 注册时邮箱/手机号已存在
    - 404: 重置时邮箱未注册
    - 429: 发送过于频繁
    - 501: 未配置短信提供商
    """
    if request.channel == 'email':
        if not request.email:
            http_exceptions.raise_bad_request(E.MAIL_CODE_INVALID, "邮箱地址不能为空")
        await _send_email_code(session, config, request.email, request.reason)
    else:
        if not request.phone:
            http_exceptions.raise_bad_request(E.SMS_CODE_INVALID, "手机号不能为空")
        await _send_sms_code(session, config, str(request.phone), request.reason)


async def _send_email_code(
    session: SessionDep,
    config: 'sqlmodels.ServerConfig',
    email: str,
    reason: str,
) -> None:
    """发送邮件验证码"""
    if reason == 'register':
        existing = await sqlmodels.User.get(session, sqlmodels.User.email == email)
        if existing:
            http_exceptions.raise_conflict(E.USER_EMAIL_EXISTS, "该邮箱已被注册")
        template_type = MailTemplateType.ACTIVATION
        subject = "验证您的邮箱"
    else:
        existing = await sqlmodels.User.get(session, sqlmodels.User.email == email)
        if not existing:
            http_exceptions.raise_not_found(E.USER_EMAIL_NOT_REGISTERED, "该邮箱未注册")
        template_type = MailTemplateType.RESET_PASSWORD
        subject = "重置密码"

    code = await VerifyCodeStore.generate_and_store(
        reason, email, ttl_minutes=config.mail_code_ttl_minutes,
    )

    await MailService.send_template(
        config, session, email, template_type, subject,
        variables={
            "site_url": config.site_url,
            "logo_light": config.logo_light,
            "logo_dark": config.logo_dark,
            "site_name": config.site_name,
            "verify_code": code,
            "valid_minutes": str(config.mail_code_ttl_minutes),
            "current_year": str(datetime.now().year),
        },
    )


async def _send_sms_code(
    session: SessionDep,
    config: 'sqlmodels.ServerConfig',
    phone: str,
    reason: str,
) -> None:
    """发送短信验证码"""
    from sqlmodels.sms import SmsProvider, SmsCodeReasonEnum, SmsRateLimitException

    # 获取所有启用的 SMS 提供商
    providers: list[SmsProvider] = await SmsProvider.get(
        session, SmsProvider.enabled == True, fetch_mode="all",
    )
    if not providers:
        http_exceptions.raise_not_implemented(E.SMS_NO_PROVIDER, "未配置短信提供商")

    # 映射 reason
    sms_reason = SmsCodeReasonEnum(reason) if reason in SmsCodeReasonEnum.__members__ else SmsCodeReasonEnum.login
    code_ttl = config.sms_code_ttl_minutes * 60
    rate_limit_ttl = config.sms_code_rate_limit_seconds

    # 冗余机制：依次尝试所有提供商
    last_error: Exception | None = None
    for provider in providers:
        try:
            await provider.send_verification_code(
                phone, sms_reason, code_ttl, rate_limit_ttl,
            )
            return
        except SmsRateLimitException:
            http_exceptions.raise_too_many_requests(E.SMS_RATE_LIMITED, "发送过于频繁，请稍后再试")
        except Exception as exc:
            logger.warning(f"短信提供商 {provider.name} 发送失败: {exc}")
            last_error = exc

    logger.error(f"所有短信提供商发送失败: {last_error}")
    http_exceptions.raise_internal_error(E.SMS_PROVIDER_ERROR, "短信发送失败")


@user_router.post(
    path='/reset_password',
    summary='通过验证码重置密码',
    description='验证邮箱验证码并重置密码。',
    status_code=204,
)
async def router_user_reset_password(
    session: SessionDep,
    request: sqlmodels.ResetPasswordRequest,
) -> None:
    """
    重置密码

    流程：
    1. 验证码校验（原子校验+删除）
    2. 查找用户
    3. 更新密码哈希

    错误处理：
    - 400: 验证码错误或已过期
    - 404: 邮箱未注册
    """
    valid = await VerifyCodeStore.verify_and_delete("reset", request.email, request.code)
    if not valid:
        http_exceptions.raise_bad_request(E.MAIL_CODE_INVALID, "验证码错误或已过期")

    user: User | None = await User.get(session, User.email == request.email)
    if not user:
        http_exceptions.raise_not_found(E.USER_EMAIL_NOT_REGISTERED, "该邮箱未注册")

    user.password_hash = Password.hash(request.new_password)
    _ = await user.save(session)

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
    from utils.avatar import (
        get_avatar_file_path,
        get_avatar_settings,
        gravatar_url,
        resolve_avatar_size,
    )

    user = await sqlmodels.User.get(session, sqlmodels.User.id == id)
    if not user:
        http_exceptions.raise_not_found(E.USER_NOT_FOUND, "用户不存在")

    avatar_path, _, size_l, size_m, size_s = await get_avatar_settings(session)

    if user.avatar == AvatarType.FILE:
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

    elif user.avatar == AvatarType.GRAVATAR:
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
    # group 已由 auth_required 预加载
    # 显式加载 tags 关系
    await session.refresh(user, ['tags'])

    return sqlmodels.UserResponse.model_validate(user, from_attributes=True, update={
        'group': GroupResponse.model_validate(user.group, from_attributes=True),
        'tags': [tag.name for tag in user.tags] if user.tags else [],
    })

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
        http_exceptions.raise_not_found(E.ADMIN_GROUP_NOT_FOUND, "用户组不存在")

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
        http_exceptions.raise_bad_request(E.AUTH_PASSKEY_DISABLED, "Passkey 未启用")

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
        http_exceptions.raise_bad_request(E.AUTH_PASSKEY_REGISTER_EXPIRED, "注册会话已过期，请重新开始")

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
        http_exceptions.raise_bad_request(E.AUTH_PASSKEY_VERIFICATION_FAILED, "Passkey 验证失败")

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

    from sqlmodels import AuthnDetailResponse
    return AuthnDetailResponse.model_validate(authn, from_attributes=True)


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
        http_exceptions.raise_bad_request(E.AUTH_PASSKEY_DISABLED, "Passkey 未启用")

    rp_id, _rp_name, _origin = config.get_rp_config()

    options = generate_authentication_options(rp_id=rp_id)

    # 生成 challenge_token 用于关联 challenge
    challenge_token: str = str(uuid4())
    await ChallengeStore.store(f"auth:{challenge_token}", options.challenge)

    result: dict = json.loads(options_to_json(options))
    result["challenge_token"] = challenge_token
    return result
