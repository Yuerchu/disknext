"""
用户认证流程辅助函数

提供各种登录方式（邮箱密码、OAuth、Passkey、手机号短信）的实现逻辑。
"""
import orjson
from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel_ext import rel, cond
from webauthn import verify_authentication_response
from webauthn.helpers import base64url_to_bytes

import sqlmodels
from sqlmodels.auth_identity import AuthProviderType
from sqlmodels.group import Group
from sqlmodels.server_config import ServerConfig
from sqlmodels.user import AvatarType, User, UserStatus
from sqlmodels.user_authn import UserAuthn
from utils import Password, http_exceptions
from utils.http.error_codes import ErrorCode as E
from utils.password.pwd import PasswordStatus
from utils.redis.challenge_store import ChallengeStore


def check_provider_enabled(config: ServerConfig, provider: AuthProviderType) -> None:
    """检查认证方式是否已被站长启用"""
    provider_map = {
        AuthProviderType.GITHUB: config.is_github_enabled,
        AuthProviderType.QQ: config.is_qq_enabled,
        AuthProviderType.EMAIL_PASSWORD: config.is_auth_email_password_enabled,
        AuthProviderType.PHONE_SMS: config.is_auth_phone_sms_enabled,
        AuthProviderType.PASSKEY: config.is_auth_passkey_enabled,
    }
    is_enabled = provider_map.get(provider, False)
    if not is_enabled:
        http_exceptions.raise_bad_request(E.AUTH_PROVIDER_DISABLED, f"登录方式 {provider.value} 未启用")


async def login_email_password(
        session: AsyncSession,
        request: sqlmodels.UnifiedAuthRequest,
) -> User:
    """邮箱+密码登录"""
    if not request.credential:
        http_exceptions.raise_bad_request(E.USER_PASSWORD_EMPTY, "密码不能为空")

    user: User | None = await User.get(session, cond(User.email == request.identifier), load=rel(User.group))
    if not user or not user.password_hash:
        logger.debug(f"未找到邮箱密码身份: {request.identifier}")
        http_exceptions.raise_unauthorized(E.AUTH_INVALID_CREDENTIALS, "邮箱或密码错误")

    if Password.verify(user.password_hash, request.credential) != PasswordStatus.VALID:
        logger.debug(f"密码验证失败: {request.identifier}")
        http_exceptions.raise_unauthorized(E.AUTH_INVALID_CREDENTIALS, "邮箱或密码错误")

    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden(E.AUTH_ACCOUNT_DISABLED, "账户已被禁用")

    # 检查两步验证
    if user.two_factor_secret:
        if not request.two_fa_code:
            logger.debug(f"需要两步验证: {request.identifier}")
            http_exceptions.raise_precondition_required(E.AUTH_TWO_FA_REQUIRED, "需要两步验证")
        if Password.verify_totp(user.two_factor_secret, request.two_fa_code) != PasswordStatus.VALID:
            logger.debug(f"两步验证失败: {request.identifier}")
            http_exceptions.raise_unauthorized(E.AUTH_TWO_FA_INVALID, "两步验证码错误")

    return user


async def login_oauth(
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
        http_exceptions.raise_bad_request(E.AUTH_PROVIDER_UNSUPPORTED, f"不支持的 OAuth 提供者: {provider.value}")

    if not client_id or not client_secret:
        http_exceptions.raise_bad_request(E.AUTH_OAUTH_NOT_CONFIGURED, f"{provider.value} OAuth 未配置")

    # 根据 provider 创建对应的 OAuth 客户端
    if provider == AuthProviderType.GITHUB:
        from utils.oauth import GithubOAuth
        oauth_client = GithubOAuth(client_id, client_secret)
        token_resp = await oauth_client.get_access_token(code=request.identifier)
        user_info_resp = await oauth_client.get_user_info(token_resp)
        openid = str(user_info_resp.user_data.id)
        nickname = user_info_resp.user_data.name or user_info_resp.user_data.login
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
        email = None
    else:
        http_exceptions.raise_bad_request(E.AUTH_PROVIDER_UNSUPPORTED, f"不支持的 OAuth 提供者: {provider.value}")

    # 按 provider 查找已绑定的用户
    if provider == AuthProviderType.GITHUB:
        user: User | None = await User.get(session, cond(User.github_id == openid), load=rel(User.group))
    elif provider == AuthProviderType.QQ:
        user: User | None = await User.get(session, cond(User.qq_id == openid), load=rel(User.group))
    else:
        http_exceptions.raise_bad_request(E.AUTH_PROVIDER_UNSUPPORTED, f"不支持的 OAuth 提供者: {provider.value}")

    if user:
        if user.status != UserStatus.ACTIVE:
            http_exceptions.raise_forbidden(E.AUTH_ACCOUNT_DISABLED, "账户已被禁用")
        return user

    # 未绑定 → 自动注册
    user = await _auto_register_oauth_user(
        session,
        config,
        provider=provider,
        openid=openid,
        nickname=nickname,
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
    oauth_fields: dict[str, str] = {}
    if provider == AuthProviderType.GITHUB:
        oauth_fields["github_id"] = openid
    elif provider == AuthProviderType.QQ:
        oauth_fields["qq_id"] = openid

    new_user = User(
        email=email,
        nickname=nickname,
        avatar=AvatarType.DEFAULT,
        group_id=default_group_id,
        scopes=default_group.default_scopes,
        **oauth_fields,
    )
    new_user = await new_user.save(session)

    # 创建用户根目录
    default_policy = await sqlmodels.Policy.get(session, sqlmodels.Policy.name == "本地存储")
    if default_policy:
        _ = await sqlmodels.Entry(
            name="/",
            type=sqlmodels.EntryType.FOLDER,
            owner_id=new_user.id,
            parent_id=None,
            policy_id=default_policy.id,
        ).save(session)

    # 重新加载用户（含 group 关系）
    user: User = await User.get_exist_one(session, new_user.id, load=rel(User.group))
    logger.info(f"OAuth 自动注册用户: provider={provider.value}, openid={openid}")
    return user


async def login_passkey(
        session: AsyncSession,
        request: sqlmodels.UnifiedAuthRequest,
        config: ServerConfig,
) -> User:
    """
    Passkey/WebAuthn 登录（Discoverable Credentials 模式）

    identifier 为 challenge_token，credential 为 JSON 格式的 authenticator assertion response。
    """
    if not request.credential:
        http_exceptions.raise_bad_request(E.AUTH_PASSKEY_ASSERTION_EMPTY, "WebAuthn assertion response 不能为空")

    if not request.identifier:
        http_exceptions.raise_bad_request(E.AUTH_PASSKEY_CREDENTIAL_MISSING, "challenge_token 不能为空")

    # 从 ChallengeStore 取出 challenge（一次性，防重放）
    challenge: bytes | None = await ChallengeStore.retrieve_and_delete(f"auth:{request.identifier}")
    if challenge is None:
        http_exceptions.raise_unauthorized(E.AUTH_PASSKEY_CHALLENGE_EXPIRED, "登录会话已过期，请重新获取 options")

    # 从 assertion JSON 中解析 credential_id（Discoverable Credentials 模式）
    credential_dict: dict[str, str] = orjson.loads(request.credential)
    credential_id_b64: str | None = credential_dict.get("id")
    if not credential_id_b64:
        http_exceptions.raise_bad_request(E.AUTH_PASSKEY_CREDENTIAL_MISSING, "缺少凭证 ID")

    # 查找 UserAuthn 记录
    authn: UserAuthn | None = await UserAuthn.get(
        session,
        UserAuthn.credential_id == credential_id_b64,
    )
    if not authn:
        http_exceptions.raise_unauthorized(E.AUTH_PASSKEY_NOT_REGISTERED, "Passkey 凭证未注册")

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
        http_exceptions.raise_unauthorized(E.AUTH_PASSKEY_VERIFICATION_FAILED, "Passkey 验证失败")

    # 更新签名计数
    authn.sign_count = verification.new_sign_count
    authn = await authn.save(session)

    # 加载用户
    user: User = await User.get_exist_one(session, authn.user_id, load=rel(User.group))
    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden(E.AUTH_ACCOUNT_DISABLED, "账户已被禁用")

    return user


async def login_phone_sms(
        session: AsyncSession,
        request: sqlmodels.UnifiedAuthRequest,
        config: ServerConfig,
) -> User:
    """
    手机号 + 短信验证码登录

    identifier 为手机号（E.164 格式），credential 为 6 位验证码。
    如果手机号未注册则自动注册。
    """
    from sqlmodels.sms import SmsProvider, SmsCodeReasonEnum, SmsRateLimitException, SmsCodeInvalidException

    if not request.credential:
        http_exceptions.raise_bad_request(E.SMS_CODE_INVALID, "验证码不能为空")

    phone = request.identifier
    code_ttl = config.sms_code_ttl_minutes * 60

    # 验证短信验证码
    try:
        await SmsProvider.verify_and_enforce(
            phone, request.credential, SmsCodeReasonEnum.login, code_ttl,
        )
    except SmsRateLimitException as e:
        http_exceptions.raise_too_many_requests(E.SMS_RATE_LIMITED, str(e))
    except SmsCodeInvalidException:
        http_exceptions.raise_unauthorized(E.SMS_CODE_INVALID, "验证码无效")

    # 查找用户
    user: User | None = await User.get(session, cond(User.phone == phone), load=rel(User.group))

    if user:
        if user.status != UserStatus.ACTIVE:
            http_exceptions.raise_forbidden(E.AUTH_ACCOUNT_DISABLED, "账户已被禁用")
        return user

    # 未找到 → 自动注册
    user = await _auto_register_phone_user(session, config, phone)
    return user


async def _auto_register_phone_user(
        session: AsyncSession,
        config: ServerConfig,
        phone: str,
) -> User:
    """手机号自动注册用户"""
    if not config.default_group_id:
        logger.error("默认用户组未配置")
        http_exceptions.raise_internal_error()

    default_group = await Group.get_exist_one(session, config.default_group_id)

    new_user = User(
        phone=phone,
        nickname=phone,
        avatar=AvatarType.DEFAULT,
        group_id=config.default_group_id,
        scopes=default_group.default_scopes,
    )
    new_user = await new_user.save(session)

    # 创建用户根目录
    default_policy = await sqlmodels.Policy.get(session, sqlmodels.Policy.name == "本地存储")
    if default_policy:
        _ = await sqlmodels.Entry(
            name="/",
            type=sqlmodels.EntryType.FOLDER,
            owner_id=new_user.id,
            parent_id=None,
            policy_id=default_policy.id,
        ).save(session)

    user: User = await User.get_exist_one(session, new_user.id, load=rel(User.group))
    logger.info(f"手机号自动注册用户: phone={phone}")
    return user
