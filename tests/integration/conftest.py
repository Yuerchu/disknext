"""
集成测试配置文件

提供测试数据库、测试客户端、测试用户等 fixtures
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from main import app
from models import Group, GroupOptions, Object, ObjectType, Policy, PolicyType, Setting, SettingsType, User
from utils import Password
from utils.JWT import create_access_token
from utils.JWT import JWT


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
    """创建测试数据库引擎（内存SQLite）"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    # 清理
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

    # 1. 创建基础设置
    settings = [
        Setting(type=SettingsType.BASIC, name="siteName", value="DiskNext Test"),
        Setting(type=SettingsType.BASIC, name="siteURL", value="http://localhost:8000"),
        Setting(type=SettingsType.BASIC, name="siteTitle", value="DiskNext"),
        Setting(type=SettingsType.BASIC, name="themes", value='{"default": "#5898d4"}'),
        Setting(type=SettingsType.BASIC, name="defaultTheme", value="default"),
        Setting(type=SettingsType.LOGIN, name="login_captcha", value="0"),
        Setting(type=SettingsType.LOGIN, name="reg_captcha", value="0"),
        Setting(type=SettingsType.LOGIN, name="forget_captcha", value="0"),
        Setting(type=SettingsType.LOGIN, name="email_active", value="0"),
        Setting(type=SettingsType.VIEW, name="home_view_method", value="list"),
        Setting(type=SettingsType.VIEW, name="share_view_method", value="grid"),
        Setting(type=SettingsType.AUTHN, name="authn_enabled", value="0"),
        Setting(type=SettingsType.CAPTCHA, name="captcha_ReCaptchaKey", value=""),
        Setting(type=SettingsType.CAPTCHA, name="captcha_CloudflareKey", value=""),
        Setting(type=SettingsType.REGISTER, name="register_enabled", value="1"),
        Setting(type=SettingsType.AUTH, name="secret_key", value="test_secret_key_for_jwt_token_generation"),
    ]
    for setting in settings:
        test_session.add(setting)

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

    # 4. 创建用户组选项
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

    # 5. 添加默认用户组UUID到设置
    default_group_setting = Setting(
        type=SettingsType.REGISTER,
        name="default_group",
        value=str(default_group.id),
    )
    test_session.add(default_group_setting)

    await test_session.commit()

    # 6. 创建测试用户
    test_user = User(
        id=uuid4(),
        username="testuser",
        password=Password.hash("testpass123"),
        nickname="测试用户",
        status=True,
        storage=0,
        score=0,
        group_id=default_group.id,
        avatar="default",
        theme="system",
    )
    test_session.add(test_user)

    admin_user = User(
        id=uuid4(),
        username="admin",
        password=Password.hash("adminpass123"),
        nickname="管理员",
        status=True,
        storage=0,
        score=0,
        group_id=admin_group.id,
        avatar="default",
        theme="system",
    )
    test_session.add(admin_user)

    banned_user = User(
        id=uuid4(),
        username="banneduser",
        password=Password.hash("banned123"),
        nickname="封禁用户",
        status=False,  # 封禁状态
        storage=0,
        score=0,
        group_id=default_group.id,
        avatar="default",
        theme="system",
    )
    test_session.add(banned_user)

    await test_session.commit()

    # 刷新用户对象
    await test_session.refresh(test_user)
    await test_session.refresh(admin_user)
    await test_session.refresh(banned_user)

    # 7. 创建用户根目录
    test_user_root = Object(
        id=uuid4(),
        name=test_user.username,
        type=ObjectType.FOLDER,
        owner_id=test_user.id,
        parent_id=None,
        policy_id=default_policy.id,
        size=0,
    )
    test_session.add(test_user_root)

    admin_user_root = Object(
        id=uuid4(),
        name=admin_user.username,
        type=ObjectType.FOLDER,
        owner_id=admin_user.id,
        parent_id=None,
        policy_id=default_policy.id,
        size=0,
    )
    test_session.add(admin_user_root)

    await test_session.commit()

    # 8. 设置JWT密钥（从数据库加载）
    JWT.SECRET_KEY = "test_secret_key_for_jwt_token_generation"

    return test_session


# ==================== 测试用户信息 ====================

@pytest.fixture
def test_user_info() -> dict[str, str]:
    """测试用户信息"""
    return {
        "username": "testuser",
        "password": "testpass123",
    }


@pytest.fixture
def admin_user_info() -> dict[str, str]:
    """管理员用户信息"""
    return {
        "username": "admin",
        "password": "adminpass123",
    }


@pytest.fixture
def banned_user_info() -> dict[str, str]:
    """封禁用户信息"""
    return {
        "username": "banneduser",
        "password": "banned123",
    }


# ==================== JWT Token ====================

@pytest.fixture
def test_user_token(test_user_info: dict[str, str]) -> str:
    """生成测试用户的JWT token"""
    token, _ = JWT.create_access_token(
        data={"sub": test_user_info["username"]},
        expires_delta=timedelta(hours=1),
    )
    return token


@pytest.fixture
def admin_user_token(admin_user_info: dict[str, str]) -> str:
    """生成管理员的JWT token"""
    token, _ = JWT.create_access_token(
        data={"sub": admin_user_info["username"]},
        expires_delta=timedelta(hours=1),
    )
    return token


@pytest.fixture
def expired_token() -> str:
    """生成过期的JWT token"""
    token, _ = JWT.create_access_token(
        data={"sub": "testuser"},
        expires_delta=timedelta(seconds=-1),  # 已过期
    )
    return token


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
    from middleware.dependencies import get_session

    async def override_get_session():
        yield initialized_db

    app.dependency_overrides[get_session] = override_get_session

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
    test_user = await User.get(initialized_db, User.username == "testuser")
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
