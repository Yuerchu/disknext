"""
User 充血模型方法的单元测试

覆盖从 service/user/login.py 迁入 User 类的登录业务方法：
- unified_login 分派逻辑
- _login_email_password 边界情况
- issue_tokens JWT 签发
- _check_provider_enabled 开关校验

使用 Faker 生成大量随机凭证测试鲁棒性。
"""
import uuid
from datetime import datetime
from uuid import UUID

import pytest
from faker import Faker
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.auth_identity import AuthIdentity, AuthProviderType
from sqlmodels.group import Group, GroupOptions
from sqlmodels.server_config import ServerConfig
from sqlmodels.user import (
    TokenResponse,
    UnifiedLoginRequest,
    User,
    UserStatus,
)
from utils.password.pwd import Password


# ==================== 辅助函数 ====================

async def _make_user_with_password(
    session: AsyncSession,
    group: Group,
    email: str,
    password: str,
    status: UserStatus = UserStatus.ACTIVE,
    extra_data: str | None = None,
) -> User:
    """创建用户并挂上 EMAIL_PASSWORD 身份"""
    user = User(
        email=email,
        nickname=email.split("@")[0],
        status=status,
        group_id=group.id,
    )
    user = await user.save(session)

    identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier=email,
        credential=Password.hash(password),
        is_primary=True,
        is_verified=True,
        user_id=user.id,
        extra_data=extra_data,
    )
    await identity.save(session)
    return user


async def _make_group_with_options(session: AsyncSession, name: str) -> Group:
    """创建带 GroupOptions 的用户组（issue_tokens 需要）"""
    group = Group(
        name=name,
        max_storage=10 * 1024 * 1024 * 1024,
        share_enabled=True,
        web_dav_enabled=True,
        admin=False,
        speed_limit=0,
    )
    group = await group.save(session)

    opts = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=False,
        relocate=False,
    )
    await opts.save(session)
    return group


def _make_config(
    email_password: bool = True,
    github: bool = False,
    qq: bool = False,
    passkey: bool = False,
    magic_link: bool = False,
    phone_sms: bool = False,
) -> ServerConfig:
    """构造一个 ServerConfig（不写数据库）"""
    return ServerConfig(
        is_auth_email_password_enabled=email_password,
        is_github_enabled=github,
        is_qq_enabled=qq,
        is_auth_passkey_enabled=passkey,
        is_auth_magic_link_enabled=magic_link,
        is_auth_phone_sms_enabled=phone_sms,
    )


# ==================== _check_provider_enabled ====================

class TestCheckProviderEnabled:
    """User._check_provider_enabled() 的静态校验测试"""

    def test_email_password_enabled_passes(self):
        config = _make_config(email_password=True)
        # 不抛异常
        User._check_provider_enabled(config, AuthProviderType.EMAIL_PASSWORD)

    def test_email_password_disabled_raises(self):
        config = _make_config(email_password=False)
        with pytest.raises(HTTPException) as exc_info:
            User._check_provider_enabled(config, AuthProviderType.EMAIL_PASSWORD)
        assert exc_info.value.status_code == 400

    def test_github_disabled_raises(self):
        config = _make_config(github=False)
        with pytest.raises(HTTPException) as exc_info:
            User._check_provider_enabled(config, AuthProviderType.GITHUB)
        assert exc_info.value.status_code == 400

    def test_github_enabled_passes(self):
        config = _make_config(github=True)
        User._check_provider_enabled(config, AuthProviderType.GITHUB)

    def test_qq_disabled_raises(self):
        config = _make_config(qq=False)
        with pytest.raises(HTTPException):
            User._check_provider_enabled(config, AuthProviderType.QQ)

    def test_passkey_disabled_raises(self):
        config = _make_config(passkey=False)
        with pytest.raises(HTTPException):
            User._check_provider_enabled(config, AuthProviderType.PASSKEY)

    def test_magic_link_disabled_raises(self):
        config = _make_config(magic_link=False)
        with pytest.raises(HTTPException):
            User._check_provider_enabled(config, AuthProviderType.MAGIC_LINK)

    def test_all_providers_disabled_each_raises(self, faker: Faker):
        """穷举所有 provider，在全部关闭时都应抛异常"""
        config = _make_config()  # all False
        providers = [
            AuthProviderType.GITHUB,
            AuthProviderType.QQ,
            AuthProviderType.PASSKEY,
            AuthProviderType.MAGIC_LINK,
            AuthProviderType.PHONE_SMS,
        ]
        for p in providers:
            with pytest.raises(HTTPException):
                User._check_provider_enabled(config, p)


# ==================== _login_email_password ====================

class TestLoginEmailPassword:
    """User._login_email_password() 的边界测试"""

    @pytest.mark.asyncio
    async def test_successful_login(
        self, db_session: AsyncSession, faker: Faker
    ):
        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        password = faker.password(length=16)

        await _make_user_with_password(db_session, group, email, password)

        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential=password,
        )
        user = await User._login_email_password(db_session, request)
        assert user.email == email
        assert user.status == UserStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_missing_credential_raises_400(
        self, db_session: AsyncSession, faker: Faker
    ):
        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=faker.email(),
            credential=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_credential_raises_400(
        self, db_session: AsyncSession, faker: Faker
    ):
        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=faker.email(),
            credential="",
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_email_raises_401(
        self, db_session: AsyncSession, faker: Faker
    ):
        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=faker.email(),  # 数据库里没有
            credential="any_password",
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_password_raises_401(
        self, db_session: AsyncSession, faker: Faker
    ):
        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        await _make_user_with_password(db_session, group, email, "correct_password")

        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential="wrong_password",
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_banned_user_raises_403(
        self, db_session: AsyncSession, faker: Faker
    ):
        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        password = faker.password()
        await _make_user_with_password(
            db_session, group, email, password,
            status=UserStatus.ADMIN_BANNED,
        )

        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential=password,
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_system_banned_user_raises_403(
        self, db_session: AsyncSession, faker: Faker
    ):
        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        password = faker.password()
        await _make_user_with_password(
            db_session, group, email, password,
            status=UserStatus.SYSTEM_BANNED,
        )

        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential=password,
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_two_factor_required_without_code_raises_428(
        self, db_session: AsyncSession, faker: Faker
    ):
        import orjson
        import pyotp

        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        password = faker.password()

        totp_secret = pyotp.random_base32()
        extra_data = orjson.dumps({"two_factor": totp_secret}).decode()

        await _make_user_with_password(
            db_session, group, email, password, extra_data=extra_data,
        )

        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential=password,
            two_fa_code=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 428

    @pytest.mark.asyncio
    async def test_two_factor_wrong_code_raises_401(
        self, db_session: AsyncSession, faker: Faker
    ):
        import orjson
        import pyotp

        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        password = faker.password()

        totp_secret = pyotp.random_base32()
        extra_data = orjson.dumps({"two_factor": totp_secret}).decode()

        await _make_user_with_password(
            db_session, group, email, password, extra_data=extra_data,
        )

        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential=password,
            two_fa_code="000000",  # 错误 TOTP 码
        )
        with pytest.raises(HTTPException) as exc_info:
            await User._login_email_password(db_session, request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_two_factor_valid_code_passes(
        self, db_session: AsyncSession, faker: Faker
    ):
        import orjson
        import pyotp

        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        password = faker.password()

        totp_secret = pyotp.random_base32()
        extra_data = orjson.dumps({"two_factor": totp_secret}).decode()

        await _make_user_with_password(
            db_session, group, email, password, extra_data=extra_data,
        )

        totp = pyotp.TOTP(totp_secret)
        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential=password,
            two_fa_code=totp.now(),
        )
        user = await User._login_email_password(db_session, request)
        assert user.email == email


# ==================== issue_tokens ====================

class TestIssueTokens:
    """User.issue_tokens() JWT 签发测试"""

    @pytest.mark.asyncio
    async def test_returns_valid_token_response(
        self, db_session: AsyncSession, faker: Faker
    ):
        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        user = User(
            email=email,
            nickname=faker.name(),
            group_id=group.id,
            status=UserStatus.ACTIVE,
        )
        user = await user.save(db_session)

        user = await User.get(db_session, User.id == user.id, load=User.group)

        result = await user.issue_tokens(db_session)

        assert isinstance(result, TokenResponse)
        assert result.access_token
        assert result.refresh_token
        assert isinstance(result.access_expires, datetime)
        assert isinstance(result.refresh_expires, datetime)
        # access_token 应短于 refresh_token
        assert result.access_expires < result.refresh_expires

    @pytest.mark.asyncio
    async def test_access_token_decodable(
        self, db_session: AsyncSession, faker: Faker
    ):
        import jwt as pyjwt
        from utils import JWT as JWTModule

        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        user = User(
            email=email,
            nickname=faker.name(),
            group_id=group.id,
            status=UserStatus.ACTIVE,
        )
        user = await user.save(db_session)
        user = await User.get(db_session, User.id == user.id, load=User.group)

        result = await user.issue_tokens(db_session)

        # 解码 access_token 看 payload 是否合法
        payload = pyjwt.decode(
            result.access_token,
            JWTModule.SECRET_KEY,
            algorithms=["HS256"],
        )
        assert payload["sub"] == str(user.id)
        assert payload["status"] == UserStatus.ACTIVE.value
        assert "group" in payload
        assert "jti" in payload

    @pytest.mark.asyncio
    async def test_access_and_refresh_have_different_jti(
        self, db_session: AsyncSession, faker: Faker
    ):
        import jwt as pyjwt
        from utils import JWT as JWTModule

        group = await _make_group_with_options(db_session, faker.unique.company())
        user = User(
            email=faker.unique.email(),
            nickname=faker.name(),
            group_id=group.id,
            status=UserStatus.ACTIVE,
        )
        user = await user.save(db_session)
        user = await User.get(db_session, User.id == user.id, load=User.group)

        result = await user.issue_tokens(db_session)

        access_payload = pyjwt.decode(
            result.access_token, JWTModule.SECRET_KEY, algorithms=["HS256"]
        )
        refresh_payload = pyjwt.decode(
            result.refresh_token, JWTModule.SECRET_KEY, algorithms=["HS256"]
        )
        assert access_payload["jti"] != refresh_payload["jti"]


# ==================== unified_login 分派 ====================

class TestUnifiedLoginDispatch:
    """User.unified_login() 分派到不同 provider 的测试"""

    @pytest.mark.asyncio
    async def test_dispatches_to_email_password(
        self, db_session: AsyncSession, faker: Faker
    ):
        group = await _make_group_with_options(db_session, faker.unique.company())
        email = faker.unique.email()
        password = faker.password()
        await _make_user_with_password(db_session, group, email, password)

        config = _make_config(email_password=True)
        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=email,
            credential=password,
        )
        result = await User.unified_login(db_session, request, config)
        assert isinstance(result, TokenResponse)
        assert result.access_token

    @pytest.mark.asyncio
    async def test_disabled_provider_raises_400(
        self, db_session: AsyncSession, faker: Faker
    ):
        config = _make_config(email_password=False)
        request = UnifiedLoginRequest(
            provider=AuthProviderType.EMAIL_PASSWORD,
            identifier=faker.email(),
            credential="any",
        )
        with pytest.raises(HTTPException) as exc_info:
            await User.unified_login(db_session, request, config)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_phone_sms_raises_501(
        self, db_session: AsyncSession, faker: Faker
    ):
        config = _make_config(phone_sms=True)
        request = UnifiedLoginRequest(
            provider=AuthProviderType.PHONE_SMS,
            identifier=faker.phone_number(),
            credential="123456",
        )
        with pytest.raises(HTTPException) as exc_info:
            await User.unified_login(db_session, request, config)
        assert exc_info.value.status_code == 501


# ==================== 压力测试 ====================

class TestLoginFuzz:
    """使用 Faker 批量测试登录逻辑的健壮性"""

    @pytest.mark.asyncio
    async def test_fuzz_random_credentials_all_rejected(
        self, db_session: AsyncSession, faker: Faker
    ):
        """10 个随机邮箱 + 随机密码，不存在于数据库 → 全部 401"""
        for _ in range(10):
            request = UnifiedLoginRequest(
                provider=AuthProviderType.EMAIL_PASSWORD,
                identifier=faker.unique.email(),
                credential=faker.password(length=20),
            )
            with pytest.raises(HTTPException) as exc_info:
                await User._login_email_password(db_session, request)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_fuzz_varying_password_lengths(
        self, db_session: AsyncSession, faker: Faker
    ):
        """各种长度的密码都能正确往返（hash→verify）"""
        group = await _make_group_with_options(db_session, faker.unique.company())

        for length in [8, 12, 16, 32, 64, 128]:
            email = faker.unique.email()
            password = faker.password(length=length)
            await _make_user_with_password(db_session, group, email, password)

            request = UnifiedLoginRequest(
                provider=AuthProviderType.EMAIL_PASSWORD,
                identifier=email,
                credential=password,
            )
            user = await User._login_email_password(db_session, request)
            assert user.email == email

    @pytest.mark.asyncio
    async def test_fuzz_unicode_passwords(
        self, db_session: AsyncSession, faker: Faker
    ):
        """Unicode 密码（含中文/emoji）也能正确处理"""
        group = await _make_group_with_options(db_session, faker.unique.company())

        unicode_passwords = [
            "密码123密码",
            "パスワード456",
            "пароль789",
            "🔑secret🔒",
            "混合 English 中文 🎉",
        ]

        for password in unicode_passwords:
            email = faker.unique.email()
            await _make_user_with_password(db_session, group, email, password)

            request = UnifiedLoginRequest(
                provider=AuthProviderType.EMAIL_PASSWORD,
                identifier=email,
                credential=password,
            )
            user = await User._login_email_password(db_session, request)
            assert user.email == email
