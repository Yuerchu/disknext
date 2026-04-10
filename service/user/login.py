"""
统一登录服务

支持多种认证方式：邮箱密码、GitHub OAuth、QQ OAuth、Passkey、Magic Link、手机短信（预留）。
"""
import hashlib
from uuid import UUID, uuid4

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from loguru import logger as l
from sqlmodel.ext.asyncio.session import AsyncSession

from service.redis.token_store import TokenStore
from sqlmodels.auth_identity import AuthIdentity, AuthProviderType
from sqlmodels.group import GroupClaims, GroupOptions
from sqlmodels.object import Object, ObjectType
from sqlmodels.policy import Policy
from sqlmodels.server_config import ServerConfig
from sqlmodels.user import TokenResponse, UnifiedLoginRequest, User, UserStatus
from utils import JWT, http_exceptions
from utils.password.pwd import Password, PasswordStatus


async def unified_login(
    session: AsyncSession,
    request: UnifiedLoginRequest,
    config: ServerConfig,
) -> TokenResponse:
    """
    统一登录入口，根据 provider 分发到不同的登录逻辑。

    :param session: 数据库会话
    :param request: 统一登录请求
    :param config: 服务器配置
    :return: TokenResponse
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

    return await _issue_tokens(session, user)


def _check_provider_enabled(
    config: ServerConfig,
    provider: AuthProviderType,
) -> None:
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
    request: UnifiedLoginRequest,
) -> User:
    """邮箱+密码登录"""
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
    user: User = await User.get(session, User.id == identity.user_id, load=User.group)
    if not user:
        http_exceptions.raise_unauthorized("用户不存在")

    # 验证用户状态
    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    # 检查两步验证（从 AuthIdentity.extra_data 中读取 2FA secret）
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


async def _login_oauth(
    session: AsyncSession,
    request: UnifiedLoginRequest,
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
        from service.oauth import GithubOAuth
        oauth_client = GithubOAuth(client_id, client_secret)
        token_resp = await oauth_client.get_access_token(code=request.identifier)
        user_info_resp = await oauth_client.get_user_info(token_resp)
        openid = str(user_info_resp.user_data.id)
        nickname = user_info_resp.user_data.name or user_info_resp.user_data.login
        avatar_url = user_info_resp.user_data.avatar_url
        email = user_info_resp.user_data.email
    elif provider == AuthProviderType.QQ:
        from service.oauth import QQOAuth
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

        user: User = await User.get(session, User.id == identity.user_id, load=User.group)
        if not user:
            http_exceptions.raise_unauthorized("用户不存在")
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
        l.error("默认用户组未配置")
        http_exceptions.raise_internal_error()

    default_group_id = config.default_group_id

    # 创建用户
    new_user = User(
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
    user: User = await User.get(session, User.id == new_user_id, load=User.group)
    l.info(f"OAuth 自动注册用户: provider={provider.value}, openid={openid}")
    return user


async def _login_passkey(
    session: AsyncSession,
    request: UnifiedLoginRequest,
    config: ServerConfig,
) -> User:
    """
    Passkey/WebAuthn 登录（Discoverable Credentials 模式）

    identifier 为 challenge_token（前端从 ``POST /authn/options`` 获取），
    credential 为 JSON 格式的 authenticator assertion response。
    """
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes

    from service.redis.challenge_store import ChallengeStore
    from service.webauthn import get_rp_config
    from sqlmodels.user_authn import UserAuthn

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
    rp_id, _rp_name, origin = get_rp_config(config)

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
    user: User = await User.get(session, User.id == authn.user_id, load=User.group)
    if not user:
        http_exceptions.raise_unauthorized("用户不存在")
    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    return user


async def _login_magic_link(
    session: AsyncSession,
    request: UnifiedLoginRequest,
) -> User:
    """
    Magic Link 登录

    identifier 为签名 token，由 itsdangerous 生成。
    """
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

    user: User = await User.get(session, User.id == identity.user_id, load=User.group)
    if not user:
        http_exceptions.raise_unauthorized("用户不存在")
    if user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    # 标记邮箱已验证
    if not identity.is_verified:
        identity.is_verified = True
        identity = await identity.save(session)

    return user


async def _issue_tokens(session: AsyncSession, user: User) -> TokenResponse:
    """
    签发 JWT 双令牌（access + refresh）

    提取自原 login.py 的签发逻辑，供所有 provider 共用。
    """
    # 加载 GroupOptions
    group_options: GroupOptions | None = await GroupOptions.get(
        session,
        GroupOptions.group_id == user.group_id,
    )

    # 构建权限快照
    user.group.options = group_options
    group_claims = GroupClaims.from_group(user.group)

    # 创建令牌
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

    return TokenResponse(
        access_token=access_token.access_token,
        access_expires=access_token.access_expires,
        refresh_token=refresh_token.refresh_token,
        refresh_expires=refresh_token.refresh_expires,
    )
