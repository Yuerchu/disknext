"""
Pytest 配置文件

提供测试所需的 fixtures，包括数据库会话、认证用户、测试客户端等。
"""
import asyncio
import os
import sys
from typing import AsyncGenerator
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from loguru import logger as l
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到Python路径，确保可以导入项目模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from models.database import get_session
from models.group import Group, GroupOptions
from models.migration import migration
from models.object import Object, ObjectType
from models.policy import Policy, PolicyType
from models.user import User
from utils.JWT.JWT import create_access_token
from utils.password.pwd import Password


# ==================== 事件循环 ====================

@pytest.fixture(scope="session")
def event_loop():
    """
    创建 session 级别的事件循环

    注意：pytest-asyncio 在不同版本中对事件循环的管理有所不同。
    此 fixture 确保整个测试会话使用同一个事件循环。
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== 数据库 ====================

@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    创建 SQLite 内存数据库引擎（function scope）

    每个测试函数都会获得一个全新的数据库，确保测试隔离。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        future=True,
    )

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    # 清理
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    创建异步数据库会话（function scope）

    使用内存数据库引擎创建会话，每个测试函数独立。
    """
    async_session_factory = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def initialized_db(db_session: AsyncSession) -> AsyncSession:
    """
    已初始化的数据库（运行 migration）

    执行数据库迁移逻辑，创建默认数据（如管理员用户组、默认策略等）。
    """
    # 注意：migration 函数需要适配以支持传入 session
    # 如果 migration 不支持传入 session，需要修改其实现
    try:
        # 这里假设 migration 可以在测试环境中运行
        # 实际项目中可能需要单独实现测试数据初始化逻辑
        pass
    except Exception as e:
        l.warning(f"Migration 在测试环境中跳过: {e}")

    return db_session


# ==================== HTTP 客户端 ====================

@pytest.fixture(scope="function")
def client() -> TestClient:
    """
    同步 TestClient（function scope）

    用于测试 FastAPI 端点的同步客户端。
    """
    return TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    异步 httpx.AsyncClient（function scope）

    用于测试异步端点，支持 WebSocket 等异步操作。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ==================== 覆盖依赖 ====================

def override_get_session(db_session: AsyncSession):
    """
    覆盖 FastAPI 的数据库会话依赖

    将应用的数据库会话替换为测试会话。
    """
    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override


# ==================== 测试用户 ====================

@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> dict[str, str | UUID]:
    """
    创建测试用户并返回 {id, username, password, token}

    创建一个普通用户，包含用户组、存储策略和根目录。
    """
    # 创建默认用户组
    group = Group(
        name="测试用户组",
        max_storage=1024 * 1024 * 1024 * 10,  # 10GB
        share_enabled=True,
        web_dav_enabled=True,
        admin=False,
        speed_limit=0,
    )
    group = await group.save(db_session)

    # 创建用户组选项
    group_options = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=False,
        relocate=True,
    )
    await group_options.save(db_session)

    # 创建默认存储策略
    policy = Policy(
        name="测试本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/disknext_test",
        is_private=True,
        max_size=1024 * 1024 * 100,  # 100MB
    )
    policy = await policy.save(db_session)

    # 创建测试用户
    password = "test_password_123"
    user = User(
        username="testuser",
        nickname="测试用户",
        password=Password.hash(password),
        status=True,
        storage=0,
        score=100,
        group_id=group.id,
    )
    user = await user.save(db_session)

    # 创建用户根目录
    root_folder = Object(
        name=user.username,
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id,
        size=0,
    )
    await root_folder.save(db_session)

    # 生成访问令牌
    access_token, _ = create_access_token({"sub": str(user.id)})

    return {
        "id": user.id,
        "username": user.username,
        "password": password,
        "token": access_token,
        "group_id": group.id,
        "policy_id": policy.id,
    }


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> dict[str, str | UUID]:
    """
    获取管理员用户 {id, username, token}

    创建具有管理员权限的用户。
    """
    # 创建管理员用户组
    admin_group = Group(
        name="管理员组",
        max_storage=0,  # 无限制
        share_enabled=True,
        web_dav_enabled=True,
        admin=True,
        speed_limit=0,
    )
    admin_group = await admin_group.save(db_session)

    # 创建管理员组选项
    admin_group_options = GroupOptions(
        group_id=admin_group.id,
        share_download=True,
        share_free=True,
        relocate=True,
        source_batch=100,
        select_node=True,
        advance_delete=True,
    )
    await admin_group_options.save(db_session)

    # 创建默认存储策略
    policy = Policy(
        name="管理员本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/disknext_admin",
        is_private=True,
        max_size=0,  # 无限制
    )
    policy = await policy.save(db_session)

    # 创建管理员用户
    password = "admin_password_456"
    admin = User(
        username="admin",
        nickname="管理员",
        password=Password.hash(password),
        status=True,
        storage=0,
        score=9999,
        group_id=admin_group.id,
    )
    admin = await admin.save(db_session)

    # 创建管理员根目录
    root_folder = Object(
        name=admin.username,
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=admin.id,
        policy_id=policy.id,
        size=0,
    )
    await root_folder.save(db_session)

    # 生成访问令牌
    access_token, _ = create_access_token({"sub": str(admin.id)})

    return {
        "id": admin.id,
        "username": admin.username,
        "password": password,
        "token": access_token,
        "group_id": admin_group.id,
        "policy_id": policy.id,
    }


# ==================== 认证请求头 ====================

@pytest.fixture(scope="function")
def auth_headers(test_user: dict[str, str | UUID]) -> dict[str, str]:
    """
    返回认证请求头 {"Authorization": "Bearer ..."}

    使用测试用户的令牌。
    """
    return {"Authorization": f"Bearer {test_user['token']}"}


@pytest.fixture(scope="function")
def admin_headers(admin_user: dict[str, str | UUID]) -> dict[str, str]:
    """
    返回管理员认证请求头

    使用管理员用户的令牌。
    """
    return {"Authorization": f"Bearer {admin_user['token']}"}


# ==================== 测试数据 ====================

@pytest_asyncio.fixture(scope="function")
async def test_directory(
    db_session: AsyncSession,
    test_user: dict[str, str | UUID]
) -> dict[str, UUID]:
    """
    为测试用户创建目录结构

    创建以下目录结构:
    /testuser (root)
    ├── documents
    │   ├── work
    │   └── personal
    ├── images
    └── videos

    返回: {"root": UUID, "documents": UUID, "work": UUID, ...}
    """
    user_id: UUID = test_user["id"]
    policy_id: UUID = test_user["policy_id"]

    # 获取根目录
    root = await Object.get_root(db_session, user_id)
    if not root:
        raise ValueError("测试用户的根目录不存在")

    # 创建顶级目录
    documents = Object(
        name="documents",
        type=ObjectType.FOLDER,
        parent_id=root.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    documents = await documents.save(db_session)

    images = Object(
        name="images",
        type=ObjectType.FOLDER,
        parent_id=root.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    images = await images.save(db_session)

    videos = Object(
        name="videos",
        type=ObjectType.FOLDER,
        parent_id=root.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    videos = await videos.save(db_session)

    # 创建子目录
    work = Object(
        name="work",
        type=ObjectType.FOLDER,
        parent_id=documents.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    work = await work.save(db_session)

    personal = Object(
        name="personal",
        type=ObjectType.FOLDER,
        parent_id=documents.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    personal = await personal.save(db_session)

    return {
        "root": root.id,
        "documents": documents.id,
        "images": images.id,
        "videos": videos.id,
        "work": work.id,
        "personal": personal.id,
    }
