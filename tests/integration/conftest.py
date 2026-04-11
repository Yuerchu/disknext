"""
集成测试配置文件

提供测试数据库、测试客户端、测试用户等 fixtures
"""
import asyncio
import os
from datetime import timedelta
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker

from main import app
from sqlmodels import Group, GroupClaims, GroupOptions, Object, ObjectType, Policy, PolicyType, ServerConfig, User
from sqlmodels.policy import GroupPolicyLink
from sqlmodels.auth_identity import AuthIdentity, AuthProviderType
from sqlmodels.user import UserStatus
from utils import Password
from utils.JWT import create_access_token
import utils.JWT as JWT

# tests/conftest.py 在模块加载阶段已校验并设置 DATABASE_URL / REDIS_URL 环境变量，
# 这里直接读取校验后的 URL 作为测试数据库连接
_TEST_DATABASE_URL: str = os.environ["DATABASE_URL"]


# ==================== 事件循环配置 ====================

@pytest.fixture(scope="session")
def event_loop():
    """提供会话级别的事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== 测试数据库 ====================

@pytest_asyncio.fixture(scope="function")
async def test_db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """创建 PostgreSQL 测试数据库引擎（function scope，每次重建 schema）"""
    engine = create_async_engine(
        _TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """提供测试数据库会话"""
    async_session_factory = sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session


# ==================== 测试数据初始化 ====================

@pytest_asyncio.fixture(scope="function")
async def initialized_db(test_session: AsyncSession) -> AsyncSession:
    """初始化测试数据库（包含基础配置和测试数据）"""

    # 1. 创建 ServerConfig 单例
    server_config = ServerConfig(
        id=1,
        site_name="DiskNext Test",
        site_url="http://localhost:8000",
        site_title="DiskNext",
        home_view_method="list",
        share_view_method="list",
        secret_key="55dd5c582b21b96b81b0421d6e25507877839e64434d704c89db8ef90e4077d8",
    )
    test_session.add(server_config)

    # 2. 创建默认存储策略
    default_policy = Policy(
        id=uuid4(),
        name="本地存储",
        type=PolicyType.LOCAL,
        max_size=0,
        auto_rename=False,
        directory_naming_rule="",
        file_naming_rule="",
        is_origin_link_enabled=False,
        option_serialization={},
    )
    test_session.add(default_policy)

    # 3. 创建用户组
    default_group = Group(
        id=uuid4(),
        name="默认用户组",
        max_storage=1024 * 1024 * 1024,  # 1GB
        share_enabled=True,
        web_dav_enabled=True,
        admin=False,
        speed_limit=0,
    )
    test_session.add(default_group)

    admin_group = Group(
        id=uuid4(),
        name="管理员组",
        max_storage=10 * 1024 * 1024 * 1024,  # 10GB
        share_enabled=True,
        web_dav_enabled=True,
        admin=True,
        speed_limit=0,
    )
    test_session.add(admin_group)

    await test_session.commit()

    # 刷新以获取ID
    await test_session.refresh(default_group)
    await test_session.refresh(admin_group)
    await test_session.refresh(default_policy)

    # 4. 关联用户组与存储策略
    test_session.add(GroupPolicyLink(group_id=default_group.id, policy_id=default_policy.id))
    test_session.add(GroupPolicyLink(group_id=admin_group.id, policy_id=default_policy.id))

    # 5. 创建用户组选项
    default_group_options = GroupOptions(
        group_id=default_group.id,
        share_download=True,
        share_free=False,
        relocate=False,
        source_batch=0,
        select_node=False,
        advance_delete=False,
    )
    test_session.add(default_group_options)

    admin_group_options = GroupOptions(
        group_id=admin_group.id,
        share_download=True,
        share_free=True,
        relocate=True,
        source_batch=10,
        select_node=True,
        advance_delete=True,
    )
    test_session.add(admin_group_options)

    # 5. 更新 ServerConfig 的 default_group_id
    server_config.default_group_id = default_group.id

    await test_session.commit()

    # 6. 创建测试用户
    test_user = User(
        id=uuid4(),
        email="testuser@test.local",
        nickname="测试用户",
        status=UserStatus.ACTIVE,
        storage=0,
        score=0,
        group_id=default_group.id,
        avatar="default",
    )
    test_session.add(test_user)

    admin_user = User(
        id=uuid4(),
        email="admin@disknext.local",
        nickname="管理员",
        status=UserStatus.ACTIVE,
        storage=0,
        score=0,
        group_id=admin_group.id,
        avatar="default",
    )
    test_session.add(admin_user)

    banned_user = User(
        id=uuid4(),
        email="banneduser@test.local",
        nickname="封禁用户",
        status=UserStatus.ADMIN_BANNED,
        storage=0,
        score=0,
        group_id=default_group.id,
        avatar="default",
    )
    test_session.add(banned_user)

    await test_session.commit()

    # 刷新用户对象
    await test_session.refresh(test_user)
    await test_session.refresh(admin_user)
    await test_session.refresh(banned_user)

    # 7. 创建认证身份
    test_user_identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="testuser@test.local",
        credential=Password.hash("testpass123"),
        is_primary=True,
        is_verified=True,
        user_id=test_user.id,
    )
    test_session.add(test_user_identity)

    admin_user_identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="admin@disknext.local",
        credential=Password.hash("adminpass123"),
        is_primary=True,
        is_verified=True,
        user_id=admin_user.id,
    )
    test_session.add(admin_user_identity)

    banned_user_identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="banneduser@test.local",
        credential=Password.hash("banned123"),
        is_primary=True,
        is_verified=True,
        user_id=banned_user.id,
    )
    test_session.add(banned_user_identity)

    await test_session.commit()

    # 8. 创建用户根目录
    test_user_root = Object(
        id=uuid4(),
        name="/",
        type=ObjectType.FOLDER,
        owner_id=test_user.id,
        parent_id=None,
        policy_id=default_policy.id,
        size=0,
    )
    test_session.add(test_user_root)

    admin_user_root = Object(
        id=uuid4(),
        name="/",
        type=ObjectType.FOLDER,
        owner_id=admin_user.id,
        parent_id=None,
        policy_id=default_policy.id,
        size=0,
    )
    test_session.add(admin_user_root)

    await test_session.commit()

    # 9. 设置JWT密钥（从数据库加载）
    JWT.SECRET_KEY = "55dd5c582b21b96b81b0421d6e25507877839e64434d704c89db8ef90e4077d8"

    # 刷新 group options
    await test_session.refresh(default_group_options)
    await test_session.refresh(admin_group_options)

    return test_session


# ==================== 测试用户信息 ====================

@pytest.fixture
def test_user_info() -> dict[str, str]:
    """测试用户信息"""
    return {
        "email": "testuser@test.local",
        "password": "testpass123",
    }


@pytest.fixture
def admin_user_info() -> dict[str, str]:
    """管理员用户信息"""
    return {
        "email": "admin@disknext.local",
        "password": "adminpass123",
    }


@pytest.fixture
def banned_user_info() -> dict[str, str]:
    """封禁用户信息"""
    return {
        "email": "banneduser@test.local",
        "password": "banned123",
    }


# ==================== JWT Token ====================

def _build_group_claims(group: Group, group_options: GroupOptions | None) -> GroupClaims:
    """从 Group 对象构建 GroupClaims"""
    group.options = group_options
    return GroupClaims.from_group(group)


@pytest_asyncio.fixture
async def test_user_token(initialized_db: AsyncSession) -> str:
    """生成测试用户的JWT token"""
    user = await User.get(initialized_db, User.email == "testuser@test.local")
    group = await Group.get(initialized_db, Group.id == user.group_id)
    group_options = await GroupOptions.get(initialized_db, GroupOptions.group_id == group.id)
    group_claims = _build_group_claims(group, group_options)

    result = create_access_token(
        sub=user.id,
        jti=uuid4(),
        status=user.status.value,
        group=group_claims,
        expires_delta=timedelta(hours=1),
    )
    return result.access_token


@pytest_asyncio.fixture
async def admin_user_token(initialized_db: AsyncSession) -> str:
    """生成管理员的JWT token"""
    user = await User.get(initialized_db, User.email == "admin@disknext.local")
    group = await Group.get(initialized_db, Group.id == user.group_id)
    group_options = await GroupOptions.get(initialized_db, GroupOptions.group_id == group.id)
    group_claims = _build_group_claims(group, group_options)

    result = create_access_token(
        sub=user.id,
        jti=uuid4(),
        status=user.status.value,
        group=group_claims,
        expires_delta=timedelta(hours=1),
    )
    return result.access_token


@pytest.fixture
def expired_token() -> str:
    """生成过期的JWT token"""
    group_claims = GroupClaims(
        id=uuid4(),
        name="测试组",
        max_storage=0,
        share_enabled=False,
        web_dav_enabled=False,
        admin=False,
        speed_limit=0,
    )
    result = create_access_token(
        sub=uuid4(),
        jti=uuid4(),
        status="active",
        group=group_claims,
        expires_delta=timedelta(seconds=-1),
    )
    return result.access_token


# ==================== 认证头 ====================

@pytest.fixture
def auth_headers(test_user_token: str) -> dict[str, str]:
    """测试用户的认证头"""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def admin_headers(admin_user_token: str) -> dict[str, str]:
    """管理员的认证头"""
    return {"Authorization": f"Bearer {admin_user_token}"}


# ==================== HTTP 客户端 ====================

@pytest_asyncio.fixture
async def async_client(initialized_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """异步HTTP测试客户端"""

    # 覆盖依赖项，使用测试数据库
    from sqlmodels.database_connection import DatabaseManager

    async def override_get_session():
        yield initialized_db

    app.dependency_overrides[DatabaseManager.get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # 清理
    app.dependency_overrides.clear()


# ==================== 测试目录结构 ====================

@pytest_asyncio.fixture
async def test_directory_structure(initialized_db: AsyncSession) -> dict[str, UUID]:
    """创建测试目录结构"""

    # 获取测试用户和根目录
    test_user = await User.get(initialized_db, User.email == "testuser@test.local")
    test_user_root = await Object.get_root(initialized_db, test_user.id)

    default_policy = await Policy.get(initialized_db, Policy.name == "本地存储")

    # 创建 docs 目录
    docs_folder = Object(
        id=uuid4(),
        name="docs",
        type=ObjectType.FOLDER,
        owner_id=test_user.id,
        parent_id=test_user_root.id,
        policy_id=default_policy.id,
        size=0,
    )
    initialized_db.add(docs_folder)

    # 创建 images 子目录
    images_folder = Object(
        id=uuid4(),
        name="images",
        type=ObjectType.FOLDER,
        owner_id=test_user.id,
        parent_id=docs_folder.id,
        policy_id=default_policy.id,
        size=0,
    )
    initialized_db.add(images_folder)

    # 创建测试文件
    test_file = Object(
        id=uuid4(),
        name="readme.md",
        type=ObjectType.FILE,
        owner_id=test_user.id,
        parent_id=docs_folder.id,
        policy_id=default_policy.id,
        size=1024,
    )
    initialized_db.add(test_file)

    await initialized_db.commit()

    return {
        "root_id": test_user_root.id,
        "docs_id": docs_folder.id,
        "images_id": images_folder.id,
        "file_id": test_file.id,
    }
