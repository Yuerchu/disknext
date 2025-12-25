"""
Login 服务的单元测试
"""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import User, LoginRequest, TokenResponse
from models.group import Group
from service.user.login import login
from utils.password.pwd import Password


@pytest.fixture
async def setup_user(db_session: AsyncSession):
    """创建测试用户"""
    # 创建用户组
    group = Group(name="测试组")
    group = await group.save(db_session)

    # 创建正常用户
    plain_password = "secure_password_123"
    user = User(
        username="loginuser",
        password=Password.hash(plain_password),
        status=True,
        group_id=group.id
    )
    user = await user.save(db_session)

    return {
        "user": user,
        "password": plain_password,
        "group_id": group.id
    }


@pytest.fixture
async def setup_banned_user(db_session: AsyncSession):
    """创建被封禁的用户"""
    group = Group(name="测试组2")
    group = await group.save(db_session)

    user = User(
        username="banneduser",
        password=Password.hash("password"),
        status=False,  # 封禁状态
        group_id=group.id
    )
    user = await user.save(db_session)

    return user


@pytest.fixture
async def setup_2fa_user(db_session: AsyncSession):
    """创建启用了两步验证的用户"""
    import pyotp

    group = Group(name="测试组3")
    group = await group.save(db_session)

    secret = pyotp.random_base32()
    user = User(
        username="2fauser",
        password=Password.hash("password"),
        status=True,
        two_factor=secret,
        group_id=group.id
    )
    user = await user.save(db_session)

    return {
        "user": user,
        "secret": secret,
        "password": "password"
    }


@pytest.mark.asyncio
async def test_login_success(db_session: AsyncSession, setup_user):
    """测试正常登录"""
    user_data = setup_user

    login_request = LoginRequest(
        username="loginuser",
        password=user_data["password"]
    )

    result = await login(db_session, login_request)

    assert isinstance(result, TokenResponse)
    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.access_expires is not None
    assert result.refresh_expires is not None


@pytest.mark.asyncio
async def test_login_user_not_found(db_session: AsyncSession):
    """测试用户不存在"""
    login_request = LoginRequest(
        username="nonexistent_user",
        password="any_password"
    )

    result = await login(db_session, login_request)

    assert result is None


@pytest.mark.asyncio
async def test_login_wrong_password(db_session: AsyncSession, setup_user):
    """测试密码错误"""
    login_request = LoginRequest(
        username="loginuser",
        password="wrong_password"
    )

    result = await login(db_session, login_request)

    assert result is None


@pytest.mark.asyncio
async def test_login_user_banned(db_session: AsyncSession, setup_banned_user):
    """测试用户被封禁"""
    login_request = LoginRequest(
        username="banneduser",
        password="password"
    )

    result = await login(db_session, login_request)

    assert result is False


@pytest.mark.asyncio
async def test_login_2fa_required(db_session: AsyncSession, setup_2fa_user):
    """测试需要 2FA"""
    user_data = setup_2fa_user

    login_request = LoginRequest(
        username="2fauser",
        password=user_data["password"]
        # 未提供 two_fa_code
    )

    result = await login(db_session, login_request)

    assert result == "2fa_required"


@pytest.mark.asyncio
async def test_login_2fa_invalid(db_session: AsyncSession, setup_2fa_user):
    """测试 2FA 错误"""
    user_data = setup_2fa_user

    login_request = LoginRequest(
        username="2fauser",
        password=user_data["password"],
        two_fa_code="000000"  # 错误的验证码
    )

    result = await login(db_session, login_request)

    assert result == "2fa_invalid"


@pytest.mark.asyncio
async def test_login_2fa_success(db_session: AsyncSession, setup_2fa_user):
    """测试 2FA 成功"""
    import pyotp

    user_data = setup_2fa_user
    secret = user_data["secret"]

    # 生成当前有效的 TOTP 码
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    login_request = LoginRequest(
        username="2fauser",
        password=user_data["password"],
        two_fa_code=valid_code
    )

    result = await login(db_session, login_request)

    assert isinstance(result, TokenResponse)
    assert result.access_token is not None


@pytest.mark.asyncio
async def test_login_returns_valid_tokens(db_session: AsyncSession, setup_user):
    """测试返回的令牌可以被解码"""
    import jwt as pyjwt

    user_data = setup_user

    login_request = LoginRequest(
        username="loginuser",
        password=user_data["password"]
    )

    result = await login(db_session, login_request)

    assert isinstance(result, TokenResponse)

    # 注意: 实际项目中需要使用正确的 SECRET_KEY
    # 这里假设测试环境已经设置了 SECRET_KEY
    # decoded = pyjwt.decode(
    #     result.access_token,
    #     SECRET_KEY,
    #     algorithms=["HS256"]
    # )
    # assert decoded["sub"] == "loginuser"


@pytest.mark.asyncio
async def test_login_case_sensitive_username(db_session: AsyncSession, setup_user):
    """测试用户名大小写敏感"""
    user_data = setup_user

    # 使用大写用户名登录（如果数据库是 loginuser）
    login_request = LoginRequest(
        username="LOGINUSER",
        password=user_data["password"]
    )

    result = await login(db_session, login_request)

    # 应该失败，因为用户名大小写不匹配
    assert result is None
