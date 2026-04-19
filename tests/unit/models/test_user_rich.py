"""
User 充血模型方法的单元测试

覆盖登录业务方法（已迁移到路由层后，此处测试 issue_tokens 等模型方法）：
- issue_tokens JWT 签发

使用 Faker 生成大量随机凭证测试鲁棒性。
"""
from datetime import datetime
from uuid import UUID

import pytest
from faker import Faker
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.auth_identity import AuthProviderType
from sqlmodels.group import Group
from sqlmodels.user import (
    TokenResponse,
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
    two_factor_secret: str | None = None,
) -> User:
    """创建带密码的用户"""
    user = User(
        email=email,
        nickname=email.split("@")[0],
        status=status,
        group_id=group.id,
        password_hash=Password.hash(password),
        two_factor_secret=two_factor_secret,
    )
    user = await user.save(session)
    return user


async def _make_group_with_options(session: AsyncSession, name: str) -> Group:
    """创建带选项字段的用户组（issue_tokens 需要）"""
    group = Group(
        name=name,
        max_storage=10 * 1024 * 1024 * 1024,
        share_enabled=True,
        web_dav_enabled=True,
        admin=False,
        speed_limit=0,
        share_download=True,
        share_free=False,
        relocate=False,
    )
    group = await group.save(session)
    return group


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
        import utils.conf.appmeta as appmeta

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
            appmeta.secret_key,
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
        import utils.conf.appmeta as appmeta

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
            result.access_token, appmeta.secret_key, algorithms=["HS256"]
        )
        refresh_payload = pyjwt.decode(
            result.refresh_token, appmeta.secret_key, algorithms=["HS256"]
        )
        assert access_payload["jti"] != refresh_payload["jti"]
