"""
Pytest 配置文件

提供测试所需的 fixtures，包括数据库会话、认证用户、测试客户端等。

**环境要求**：DiskNext 只支持 PostgreSQL + Redis，测试必须连到真实实例。
通过环境变量 `TEST_DATABASE_URL` 和 `TEST_REDIS_URL` 指定测试后端。

**安全约束**（破坏性操作安全规则）：
- `TEST_DATABASE_URL` 的数据库名必须包含 ``test`` 或 ``dev``，
  否则拒绝连接以防误伤生产库
- URL 前缀必须为 ``postgresql``
- `TEST_REDIS_URL` 的 db index 必须 >= 1（避免 flushdb 把 db0 的生产数据清掉）
"""
import asyncio
import os
import sys
from typing import AsyncGenerator
from uuid import UUID, uuid4

from dotenv import load_dotenv

# 先把项目根目录加入 sys.path 以便导入 main 等顶层模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# 先加载 .env 到环境变量，再做后续校验（main.py/appmeta.py 也依赖这些变量）
load_dotenv()


def _validate_test_database_url() -> str:
    """
    校验并返回 TEST_DATABASE_URL，不满足条件则立即 skip 整个测试 session。

    破坏性操作安全规则：
    - 前缀必须是 postgresql（拒绝 SQLite/MySQL 等）
    - 数据库名必须包含 'test' 或 'dev'，防止误伤生产库
    """
    import pytest

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "未设置 TEST_DATABASE_URL，跳过测试。"
            "示例: postgresql+asyncpg://user:pass@localhost:5432/disknext_test",
            allow_module_level=True,
        )
    if not url.startswith("postgresql"):
        pytest.skip(
            f"TEST_DATABASE_URL 必须是 PostgreSQL（asyncpg），当前前缀无效: {url.split('://', 1)[0]}",
            allow_module_level=True,
        )
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0].lower()
    if "test" not in db_name and "dev" not in db_name:
        pytest.skip(
            f"拒绝连接：TEST_DATABASE_URL 数据库名 '{db_name}' 不包含 test/dev，"
            "为防止误伤生产库拒绝运行测试",
            allow_module_level=True,
        )
    return url


def _validate_test_redis_url() -> str:
    """
    校验并返回 TEST_REDIS_URL。

    要求 db index >= 1，防止 flushdb 清掉 db0 的生产数据。
    """
    import pytest

    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip(
            "未设置 TEST_REDIS_URL，跳过测试。"
            "示例: redis://localhost:6379/15（db index 必须 >= 1）",
            allow_module_level=True,
        )
    tail = url.rsplit("/", 1)[-1].split("?", 1)[0]
    try:
        db_index = int(tail)
    except ValueError:
        pytest.skip(
            f"TEST_REDIS_URL 必须指定 db index（如 /15），当前无法解析: {url}",
            allow_module_level=True,
        )
    if db_index < 1:
        pytest.skip(
            f"拒绝连接：TEST_REDIS_URL 的 db index 必须 >= 1（当前 {db_index}），"
            "为防止 flushdb 清掉生产数据",
            allow_module_level=True,
        )
    return url


# 模块加载阶段：先校验测试环境变量，再强制覆盖应用所需的 DATABASE_URL / REDIS_URL，
# 最后才能导入 main.py（它在导入期会读取这些配置）。
# 必须用赋值而非 setdefault，否则 .env 里的生产 URL 会被 appmeta 读到，
# 导致测试连到生产 Redis/DB（严重安全风险）。
_TEST_DATABASE_URL = _validate_test_database_url()
_TEST_REDIS_URL = _validate_test_redis_url()
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ["REDIS_URL"] = _TEST_REDIS_URL

import pytest
import pytest_asyncio
from faker import Faker
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from main import app
from utils.redis import RedisManager
from sqlmodels.database_connection import DatabaseManager
from sqlmodels.group import Group, GroupClaims
from sqlmodels.file import File, FileType
from sqlmodels.policy import Policy, PolicyType
from sqlmodels.user import User, UserStatus
import utils.conf.appmeta as appmeta
from utils.JWT import create_access_token
from utils.password.pwd import Password

# 设置测试用 JWT 密钥
appmeta.secret_key = "55dd5c582b21b96b81b0421d6e25507877839e64434d704c89db8ef90e4077d8"


# ==================== Faker ====================

@pytest.fixture(scope="session")
def faker() -> Faker:
    """
    Session 级共享的 Faker 实例

    使用中文 locale 生成姓名、地址等本地化数据，同时自带所有英文 provider。
    固定 seed 保证可重现（调试失败时换一个 seed 即可 reproduce 边界场景）。
    """
    fake = Faker(['zh_CN', 'en_US'])
    Faker.seed(20260411)
    return fake


@pytest.fixture(scope="function")
def faker_random(faker: Faker) -> Faker:
    """
    Function 级 Faker，但使用随机 seed（每次调用生成不同数据）

    用于压力/随机化测试，验证方法在任意输入下都健壮。
    """
    faker.unique.clear()
    return faker


# ==================== 事件循环 ====================

@pytest.fixture(scope="session")
def event_loop():
    """创建 session 级别的事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== 数据库 ====================

@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    PostgreSQL 测试引擎（function scope）

    每个测试函数都会 drop_all + create_all 重建所有表，保证测试隔离。
    """
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
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """异步数据库会话（function scope）"""
    async_session_factory = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session


# ==================== Redis ====================

@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_redis() -> AsyncGenerator[None, None]:
    """
    测试 Redis（function scope，autouse）

    每个测试函数自动连接 Redis 并在结束时 flushdb + 断开。
    db index 在模块加载时已校验 >= 1，不会误伤生产数据。
    """
    await RedisManager.connect()
    client = RedisManager.get_client()
    await client.flushdb()

    yield

    try:
        await client.flushdb()
    finally:
        await RedisManager.disconnect()


@pytest_asyncio.fixture(scope="function")
async def initialized_db(db_session: AsyncSession) -> AsyncSession:
    """
    已初始化的数据库（运行 migration）

    TODO: 接入真实 migration 逻辑，当前仅为占位兼容旧测试。
    """
    return db_session


# ==================== HTTP 客户端 ====================

@pytest.fixture(scope="function")
def client() -> TestClient:
    """同步 TestClient（function scope）"""
    return TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """异步 httpx.AsyncClient（function scope）"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ==================== 覆盖依赖 ====================

def override_get_session(db_session: AsyncSession):
    """将应用的数据库会话替换为测试会话"""
    async def _override():
        yield db_session

    app.dependency_overrides[DatabaseManager.get_session] = _override


# ==================== 测试用户 ====================

@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> dict[str, str | UUID]:
    """创建测试用户并返回 {id, email, password, token}"""
    group = Group(
        name="测试用户组",
        max_storage=1024 * 1024 * 1024 * 10,
        share_enabled=True,
        web_dav_enabled=True,
        admin=False,
        speed_limit=0,
        share_download=True,
        share_free=False,
        relocate=True,
    )
    group = await group.save(db_session)

    policy = Policy(
        name="测试本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/disknext_test",
        is_private=True,
        max_size=1024 * 1024 * 100,
    )
    policy = await policy.save(db_session)

    password = "test_password_123"
    user = User(
        email="testuser@test.local",
        nickname="测试用户",
        status=UserStatus.ACTIVE,
        storage=0,
        score=100,
        group_id=group.id,
        password_hash=Password.hash(password),
    )
    user = await user.save(db_session)

    root_folder = File(
        name="/",
        type=FileType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id,
        size=0,
    )
    await root_folder.save(db_session)

    group_claims = GroupClaims.from_group(group)

    access_token_obj = create_access_token(
        sub=user.id,
        jti=uuid4(),
        status=user.status.value,
        group=group_claims,
    )

    return {
        "id": user.id,
        "email": user.email,
        "password": password,
        "token": access_token_obj.access_token,
        "group_id": group.id,
        "policy_id": policy.id,
    }


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> dict[str, str | UUID]:
    """获取管理员用户 {id, email, token}"""
    admin_group = Group(
        name="管理员组",
        max_storage=0,
        share_enabled=True,
        web_dav_enabled=True,
        admin=True,
        speed_limit=0,
        share_download=True,
        share_free=True,
        relocate=True,
        source_batch=100,
        select_node=True,
        advance_delete=True,
    )
    admin_group = await admin_group.save(db_session)

    policy = Policy(
        name="管理员本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/disknext_admin",
        is_private=True,
        max_size=0,
    )
    policy = await policy.save(db_session)

    password = "admin_password_456"
    admin = User(
        email="admin@yxqi.cn",
        nickname="管理员",
        status=UserStatus.ACTIVE,
        storage=0,
        score=9999,
        group_id=admin_group.id,
        password_hash=Password.hash(password),
    )
    admin = await admin.save(db_session)

    root_folder = File(
        name="/",
        type=FileType.FOLDER,
        parent_id=None,
        owner_id=admin.id,
        policy_id=policy.id,
        size=0,
    )
    await root_folder.save(db_session)

    admin_group_claims = GroupClaims.from_group(admin_group)

    access_token_obj = create_access_token(
        sub=admin.id,
        jti=uuid4(),
        status=admin.status.value,
        group=admin_group_claims,
    )

    return {
        "id": admin.id,
        "email": admin.email,
        "password": password,
        "token": access_token_obj.access_token,
        "group_id": admin_group.id,
        "policy_id": policy.id,
    }


# ==================== 认证请求头 ====================

@pytest.fixture(scope="function")
def auth_headers(test_user: dict[str, str | UUID]) -> dict[str, str]:
    """返回认证请求头 {"Authorization": "Bearer ..."}"""
    return {"Authorization": f"Bearer {test_user['token']}"}


@pytest.fixture(scope="function")
def admin_headers(admin_user: dict[str, str | UUID]) -> dict[str, str]:
    """返回管理员认证请求头"""
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
    """
    user_id: UUID = test_user["id"]
    policy_id: UUID = test_user["policy_id"]

    root = await File.get_root(db_session, user_id)
    if not root:
        raise ValueError("测试用户的根目录不存在")

    documents = File(
        name="documents",
        type=FileType.FOLDER,
        parent_id=root.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    documents = await documents.save(db_session)

    images = File(
        name="images",
        type=FileType.FOLDER,
        parent_id=root.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    images = await images.save(db_session)

    videos = File(
        name="videos",
        type=FileType.FOLDER,
        parent_id=root.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    videos = await videos.save(db_session)

    work = File(
        name="work",
        type=FileType.FOLDER,
        parent_id=documents.id,
        owner_id=user_id,
        policy_id=policy_id,
        size=0,
    )
    work = await work.save(db_session)

    personal = File(
        name="personal",
        type=FileType.FOLDER,
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


# ==================== 通用最小化 setup（用于单元测试） ====================

@pytest_asyncio.fixture(scope="function")
async def minimal_setup(db_session: AsyncSession, faker: Faker) -> dict[str, object]:
    """
    最小化测试环境：1 个 Group + 1 个 User + 1 个 Policy + User 的根目录

    用于需要快速创建一个合法上下文的单元测试，避免每个 test 重复 30 行
    fixture 代码。返回的字段均为已持久化的模型实例。
    """
    group = Group(
        name=faker.unique.company(),
        max_storage=10 * 1024 * 1024 * 1024,
        share_enabled=True,
        web_dav_enabled=True,
        admin=False,
        speed_limit=0,
    )
    group = await group.save(db_session)

    policy = Policy(
        name=f"test_policy_{uuid4().hex[:8]}",
        type=PolicyType.LOCAL,
        server=f"/tmp/{faker.uuid4()}",
        is_private=True,
        max_size=0,
    )
    policy = await policy.save(db_session)

    user = User(
        email=faker.unique.email(),
        nickname=faker.name(),
        status=UserStatus.ACTIVE,
        storage=0,
        score=0,
        group_id=group.id,
    )
    user = await user.save(db_session)

    root = File(
        name="/",
        type=FileType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id,
        size=0,
    )
    root = await root.save(db_session)

    return {
        "group": group,
        "policy": policy,
        "user": user,
        "root": root,
    }
