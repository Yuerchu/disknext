"""
Login 服务的单元测试

测试 unified_login() 各 provider 路径。
"""
import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.auth_identity import AuthIdentity, AuthProviderType
from sqlmodels.setting import Setting, SettingsType
from sqlmodels.user import User, UnifiedLoginRequest, TokenResponse, UserStatus
from sqlmodels.group import Group, GroupOptions
from service.user.login import unified_login
from utils.password.pwd import Password


@pytest.fixture
async def setup_auth_settings(db_session: AsyncSession):
    """创建认证相关的 Setting 配置"""
    settings = [
        Setting(type=SettingsType.AUTH, name="auth_email_password_enabled", value="1"),
        Setting(type=SettingsType.AUTH, name="auth_phone_sms_enabled", value="0"),
        Setting(type=SettingsType.AUTH, name="auth_passkey_enabled", value="0"),
        Setting(type=SettingsType.AUTH, name="auth_magic_link_enabled", value="0"),
        Setting(type=SettingsType.OAUTH, name="github_enabled", value="0"),
        Setting(type=SettingsType.OAUTH, name="qq_enabled", value="0"),
    ]
    for s in settings:
        await s.save(db_session)


@pytest.fixture
async def setup_user(db_session: AsyncSession, setup_auth_settings):
    """创建测试用户和邮箱密码认证身份"""
    # 创建用户组
    group = Group(name="测试组")
    group = await group.save(db_session)

    # 创建用户组选项
    group_options = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=False,
        relocate=False,
    )
    await group_options.save(db_session)

    # 创建正常用户
    plain_password = "secure_password_123"
    user = User(
        email="loginuser@test.local",
        status=UserStatus.ACTIVE,
        group_id=group.id,
    )
    user = await user.save(db_session)

    # 创建邮箱密码认证身份
    identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="loginuser@test.local",
        credential=Password.hash(plain_password),
        is_primary=True,
        is_verified=True,
        user_id=user.id,
    )
    await identity.save(db_session)

    return {
        "user": user,
        "password": plain_password,
        "group_id": group.id,
    }


@pytest.fixture
async def setup_banned_user(db_session: AsyncSession, setup_auth_settings):
    """创建被封禁的用户"""
    group = Group(name="测试组2")
    group = await group.save(db_session)

    group_options = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=False,
        relocate=False,
    )
    await group_options.save(db_session)

    user = User(
        email="banneduser@test.local",
        status=UserStatus.ADMIN_BANNED,
        group_id=group.id,
    )
    user = await user.save(db_session)

    identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="banneduser@test.local",
        credential=Password.hash("password"),
        is_primary=True,
        is_verified=True,
        user_id=user.id,
    )
    await identity.save(db_session)

    return user


@pytest.fixture
async def setup_2fa_user(db_session: AsyncSession, setup_auth_settings):
    """创建启用了两步验证的用户"""
    import pyotp

    group = Group(name="测试组3")
    group = await group.save(db_session)

    group_options = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=False,
        relocate=False,
    )
    await group_options.save(db_session)

    secret = pyotp.random_base32()
    user = User(
        email="2fauser@test.local",
        status=UserStatus.ACTIVE,
        group_id=group.id,
    )
    user = await user.save(db_session)

    # 创建带 2FA secret 的邮箱密码认证身份
    import orjson
    extra_data = orjson.dumps({"two_factor": secret}).decode('utf-8')
    identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="2fauser@test.local",
        credential=Password.hash("password"),
        extra_data=extra_data,
        is_primary=True,
        is_verified=True,
        user_id=user.id,
    )
    await identity.save(db_session)

    return {
        "user": user,
        "secret": secret,
        "password": "password",
    }


@pytest.mark.asyncio
async def test_login_success(db_session: AsyncSession, setup_user):
    """测试正常登录"""
    user_data = setup_user

    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="loginuser@test.local",
        credential=user_data["password"],
    )

    result = await unified_login(db_session, request)

    assert isinstance(result, TokenResponse)
    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.access_expires is not None
    assert result.refresh_expires is not None


@pytest.mark.asyncio
async def test_login_user_not_found(db_session: AsyncSession, setup_user):
    """测试用户不存在"""
    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="nonexistent@test.local",
        credential="any_password",
    )

    with pytest.raises(HTTPException) as exc_info:
        await unified_login(db_session, request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password(db_session: AsyncSession, setup_user):
    """测试密码错误"""
    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="loginuser@test.local",
        credential="wrong_password",
    )

    with pytest.raises(HTTPException) as exc_info:
        await unified_login(db_session, request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_user_banned(db_session: AsyncSession, setup_banned_user):
    """测试用户被封禁"""
    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="banneduser@test.local",
        credential="password",
    )

    with pytest.raises(HTTPException) as exc_info:
        await unified_login(db_session, request)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_login_2fa_required(db_session: AsyncSession, setup_2fa_user):
    """测试需要 2FA"""
    user_data = setup_2fa_user

    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="2fauser@test.local",
        credential=user_data["password"],
        # 未提供 two_fa_code
    )

    with pytest.raises(HTTPException) as exc_info:
        await unified_login(db_session, request)

    assert exc_info.value.status_code == 428


@pytest.mark.asyncio
async def test_login_2fa_invalid(db_session: AsyncSession, setup_2fa_user):
    """测试 2FA 错误"""
    user_data = setup_2fa_user

    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="2fauser@test.local",
        credential=user_data["password"],
        two_fa_code="000000",
    )

    with pytest.raises(HTTPException) as exc_info:
        await unified_login(db_session, request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_2fa_success(db_session: AsyncSession, setup_2fa_user):
    """测试 2FA 成功"""
    import pyotp

    user_data = setup_2fa_user
    secret = user_data["secret"]

    # 生成当前有效的 TOTP 码
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="2fauser@test.local",
        credential=user_data["password"],
        two_fa_code=valid_code,
    )

    result = await unified_login(db_session, request)

    assert isinstance(result, TokenResponse)
    assert result.access_token is not None


@pytest.mark.asyncio
async def test_login_provider_disabled(db_session: AsyncSession, setup_user):
    """测试未启用的 provider"""
    request = UnifiedLoginRequest(
        provider=AuthProviderType.PHONE_SMS,
        identifier="13800138000",
        credential="123456",
    )

    with pytest.raises(HTTPException) as exc_info:
        await unified_login(db_session, request)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_login_missing_password(db_session: AsyncSession, setup_user):
    """测试邮箱密码登录缺少密码"""
    request = UnifiedLoginRequest(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="loginuser@test.local",
        # 未提供 credential
    )

    with pytest.raises(HTTPException) as exc_info:
        await unified_login(db_session, request)

    assert exc_info.value.status_code == 400
