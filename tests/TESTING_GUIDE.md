# DiskNext Server 测试基础设施使用指南

本文档介绍如何使用新的测试基础设施进行单元测试和集成测试。

## 目录结构

```
tests/
├── conftest.py              # Pytest 配置和全局 fixtures
├── fixtures/                # 测试数据工厂
│   ├── __init__.py
│   ├── users.py            # 用户工厂
│   ├── groups.py           # 用户组工厂
│   └── objects.py          # 对象（文件/目录）工厂
├── unit/                   # 单元测试
│   ├── models/             # 模型测试
│   ├── utils/              # 工具测试
│   └── service/            # 服务测试
├── integration/            # 集成测试
│   ├── api/                # API 测试
│   └── middleware/         # 中间件测试
├── example_test.py         # 示例测试（展示用法）
├── README.md               # 原有文档
└── TESTING_GUIDE.md        # 本文档
```

## 快速开始

### 1. 安装依赖

```bash
# 使用 uv 安装依赖
uv sync

### 2. 运行示例测试

```bash
# 运行示例测试，查看输出
pytest tests/example_test.py -v
```

### 3. 查看可用的 fixtures

```bash
# 列出所有可用的 fixtures
pytest --fixtures tests/conftest.py
```

## 可用的 Fixtures

### 数据库相关

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `test_engine` | function | SQLite 内存数据库引擎 |
| `db_session` | function | 异步数据库会话 |
| `initialized_db` | function | 已初始化的数据库（运行了 migration） |

### HTTP 客户端

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `client` | function | 同步 TestClient（FastAPI） |
| `async_client` | function | 异步 httpx.AsyncClient |

### 测试用户

| Fixture | 作用域 | 返回值 | 说明 |
|---------|--------|--------|------|
| `test_user` | function | `dict[str, str \| UUID]` | 创建普通测试用户 |
| `admin_user` | function | `dict[str, str \| UUID]` | 创建管理员用户 |

返回的字典包含以下键：
- `id`: 用户 UUID
- `username`: 用户名
- `password`: 明文密码
- `token`: JWT 访问令牌
- `group_id`: 用户组 UUID
- `policy_id`: 存储策略 UUID

### 认证相关

| Fixture | 作用域 | 返回值 | 说明 |
|---------|--------|--------|------|
| `auth_headers` | function | `dict[str, str]` | 测试用户的认证请求头 |
| `admin_headers` | function | `dict[str, str]` | 管理员的认证请求头 |

### 测试数据

| Fixture | 作用域 | 返回值 | 说明 |
|---------|--------|--------|------|
| `test_directory` | function | `dict[str, UUID]` | 为测试用户创建目录结构 |

## 使用测试数据工厂

### UserFactory

```python
from tests.fixtures import UserFactory

# 创建普通用户
user = await UserFactory.create(
    session,
    group_id=group.id,
    username="testuser",
    password="password123",
    nickname="测试用户",
    score=100
)

# 创建管理员
admin = await UserFactory.create_admin(
    session,
    admin_group_id=admin_group.id,
    username="admin"
)

# 创建被封禁用户
banned = await UserFactory.create_banned(
    session,
    group_id=group.id
)

# 创建有存储使用记录的用户
storage_user = await UserFactory.create_with_storage(
    session,
    group_id=group.id,
    storage_bytes=1024 * 1024 * 100  # 100MB
)
```

### GroupFactory

```python
from tests.fixtures import GroupFactory

# 创建普通用户组（带选项）
group = await GroupFactory.create(
    session,
    name="测试组",
    max_storage=1024 * 1024 * 1024 * 10,  # 10GB
    create_options=True,  # 同时创建 GroupOptions
    share_enabled=True,
    web_dav_enabled=True
)

# 创建管理员组（自动创建完整的管理员选项）
admin_group = await GroupFactory.create_admin_group(
    session,
    name="管理员组"
)

# 创建有限制的用户组
limited_group = await GroupFactory.create_limited_group(
    session,
    max_storage=1024 * 1024 * 100,  # 100MB
    name="受限组"
)

# 创建免费用户组（最小权限）
free_group = await GroupFactory.create_free_group(session)
```

### ObjectFactory

```python
from tests.fixtures import ObjectFactory

# 创建用户根目录
root = await ObjectFactory.create_user_root(
    session,
    user,
    policy.id
)

# 创建目录
folder = await ObjectFactory.create_folder(
    session,
    owner_id=user.id,
    policy_id=policy.id,
    parent_id=root.id,
    name="documents"
)

# 创建文件
file = await ObjectFactory.create_file(
    session,
    owner_id=user.id,
    policy_id=policy.id,
    parent_id=folder.id,
    name="test.txt",
    size=1024
)

# 创建目录树（递归创建多层目录）
folders = await ObjectFactory.create_directory_tree(
    session,
    owner_id=user.id,
    policy_id=policy.id,
    root_id=root.id,
    depth=3,              # 3层深度
    folders_per_level=2   # 每层2个目录
)

# 在目录中批量创建文件
files = await ObjectFactory.create_files_in_folder(
    session,
    owner_id=user.id,
    policy_id=policy.id,
    parent_id=folder.id,
    count=10,                            # 创建10个文件
    size_range=(1024, 1024 * 1024)      # 1KB - 1MB
)

# 创建大文件（用于测试存储限制）
large_file = await ObjectFactory.create_large_file(
    session,
    owner_id=user.id,
    policy_id=policy.id,
    parent_id=folder.id,
    size_mb=100
)

# 创建完整的嵌套结构（文档、媒体等）
structure = await ObjectFactory.create_nested_structure(
    session,
    owner_id=user.id,
    policy_id=policy.id,
    root_id=root.id
)
# 返回: {"documents": UUID, "work": UUID, "report": UUID, ...}
```

## 编写测试示例

### 单元测试

```python
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession
from tests.fixtures import UserFactory, GroupFactory

@pytest.mark.unit
async def test_user_creation(db_session: AsyncSession):
    """测试用户创建功能"""
    # 准备数据
    group = await GroupFactory.create(db_session)

    # 执行操作
    user = await UserFactory.create(
        db_session,
        group_id=group.id,
        username="testuser"
    )

    # 断言
    assert user.id is not None
    assert user.username == "testuser"
    assert user.group_id == group.id
    assert user.status is True
```

### 集成测试（API）

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
async def test_user_login_api(
    async_client: AsyncClient,
    test_user: dict
):
    """测试用户登录 API"""
    response = await async_client.post(
        "/api/user/session",
        json={
            "username": test_user["username"],
            "password": test_user["password"]
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["access_token"] == test_user["token"]
```

### 需要认证的测试

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
async def test_protected_endpoint(
    async_client: AsyncClient,
    auth_headers: dict
):
    """测试需要认证的端点"""
    response = await async_client.get(
        "/api/user/me",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
```

### 使用 test_directory fixture

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
async def test_list_directory(
    async_client: AsyncClient,
    auth_headers: dict,
    test_directory: dict
):
    """测试获取目录列表"""
    # test_directory 已创建了目录结构
    response = await async_client.get(
        f"/api/directory/{test_directory['documents']}",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert "objects" in data
    # 验证子目录存在
    assert any(obj["name"] == "work" for obj in data["objects"])
    assert any(obj["name"] == "personal" for obj in data["objects"])
```

## 运行测试

### 基本命令

```bash
# 运行所有测试
pytest

# 显示详细输出
pytest -v

# 运行特定测试文件
pytest tests/unit/models/test_user.py

# 运行特定测试函数
pytest tests/unit/models/test_user.py::test_user_creation
```

### 使用标记

```bash
# 只运行单元测试
pytest -m unit

# 只运行集成测试
pytest -m integration

# 运行慢速测试
pytest -m slow

# 运行除了慢速测试外的所有测试
pytest -m "not slow"

# 运行单元测试或集成测试
pytest -m "unit or integration"
```

### 测试覆盖率

```bash
# 生成覆盖率报告
pytest --cov=models --cov=routers --cov=middleware --cov=service --cov=utils

# 生成 HTML 覆盖率报告
pytest --cov=models --cov=routers --cov=utils --cov-report=html

# 查看 HTML 报告
# 在浏览器中打开 htmlcov/index.html

# 检查覆盖率是否达标（80%）
pytest --cov --cov-fail-under=80
```

### 并行运行

```bash
# 使用所有 CPU 核心
pytest -n auto

# 使用指定数量的核心
pytest -n 4

# 并行运行且显示详细输出
pytest -n auto -v
```

### 调试测试

```bash
# 显示更详细的输出
pytest -vv

# 显示 print 输出
pytest -s

# 进入调试模式（遇到失败时）
pytest --pdb

# 只运行上次失败的测试
pytest --lf

# 先运行上次失败的，再运行其他的
pytest --ff
```

## 测试标记

使用 pytest 标记来组织和筛选测试：

```python
# 单元测试
@pytest.mark.unit
async def test_something():
    pass

# 集成测试
@pytest.mark.integration
async def test_api_endpoint():
    pass

# 慢速测试（运行时间较长）
@pytest.mark.slow
async def test_large_dataset():
    pass

# 组合标记
@pytest.mark.unit
@pytest.mark.slow
async def test_complex_calculation():
    pass

# 跳过测试
@pytest.mark.skip(reason="暂时跳过")
async def test_work_in_progress():
    pass

# 条件跳过
import sys

@pytest.mark.skipif(sys.platform == "win32", reason="仅限 Linux")
async def test_linux_only():
    pass
```

## 测试最佳实践

### 1. 测试隔离

每个测试应该独立，不依赖其他测试的执行结果：

```python
# ✅ 好的实践
@pytest.mark.unit
async def test_user_creation(db_session: AsyncSession):
    group = await GroupFactory.create(db_session)
    user = await UserFactory.create(db_session, group_id=group.id)
    assert user.id is not None

# ❌ 不好的实践（依赖全局状态）
global_user = None

@pytest.mark.unit
async def test_create_user(db_session: AsyncSession):
    global global_user
    group = await GroupFactory.create(db_session)
    global_user = await UserFactory.create(db_session, group_id=group.id)

@pytest.mark.unit
async def test_update_user(db_session: AsyncSession):
    # 依赖前一个测试的结果
    assert global_user is not None
    global_user.nickname = "Updated"
    await global_user.save(db_session)
```

### 2. 使用工厂而非手动创建

```python
# ✅ 好的实践
user = await UserFactory.create(db_session, group_id=group.id)

# ❌ 不好的实践
user = User(
    username="test",
    password=Password.hash("password"),
    group_id=group.id,
    status=True,
    storage=0,
    score=100,
    # ... 更多字段
)
user = await user.save(db_session)
```

### 3. 清晰的断言

```python
# ✅ 好的实践
assert user.username == "testuser", "用户名应该是 testuser"
assert user.status is True, "新用户应该是激活状态"

# ❌ 不好的实践
assert user  # 不清楚在验证什么
```

### 4. 测试异常情况

```python
import pytest

@pytest.mark.unit
async def test_duplicate_username(db_session: AsyncSession):
    """测试创建重复用户名"""
    group = await GroupFactory.create(db_session)

    # 创建第一个用户
    await UserFactory.create(
        db_session,
        group_id=group.id,
        username="duplicate"
    )

    # 尝试创建同名用户应该失败
    with pytest.raises(Exception):  # 或更具体的异常类型
        await UserFactory.create(
            db_session,
            group_id=group.id,
            username="duplicate"
        )
```

### 5. 适当的测试粒度

```python
# ✅ 好的实践：一个测试验证一个行为
@pytest.mark.unit
async def test_user_creation(db_session: AsyncSession):
    """测试用户创建"""
    # 只测试创建

@pytest.mark.unit
async def test_user_authentication(db_session: AsyncSession):
    """测试用户认证"""
    # 只测试认证

# ❌ 不好的实践：一个测试做太多事
@pytest.mark.unit
async def test_user_everything(db_session: AsyncSession):
    """测试用户的所有功能"""
    # 创建、更新、删除、认证...全都在一个测试里
```

## 常见问题

### Q: 测试失败时如何调试？

```bash
# 使用 -vv 显示更详细的输出
pytest -vv

# 使用 -s 显示 print 语句
pytest -s

# 使用 --pdb 在失败时进入调试器
pytest --pdb

# 组合使用
pytest -vvs --pdb
```

### Q: 如何只运行某些测试？

```bash
# 按标记运行
pytest -m unit

# 按文件运行
pytest tests/unit/models/

# 按测试名称模糊匹配
pytest -k "user"  # 运行所有名称包含 "user" 的测试

# 组合条件
pytest -m unit -k "not slow"
```

### Q: 数据库会话相关错误？

确保使用正确的 fixture：

```python
# ✅ 正确
async def test_something(db_session: AsyncSession):
    user = await User.get(db_session, User.id == some_id)

# ❌ 错误：没有传入 session
async def test_something():
    user = await User.get(User.id == some_id)  # 会失败
```

### Q: 异步测试不工作？

确保使用 pytest-asyncio 标记或配置了 asyncio_mode：

```python
# pyproject.toml 中已配置 asyncio_mode = "auto"
# 所以不需要 @pytest.mark.asyncio

async def test_async_function(db_session: AsyncSession):
    # 会自动识别为异步测试
    pass
```

### Q: 如何测试需要认证的端点？

使用 `auth_headers` fixture：

```python
async def test_protected_route(
    async_client: AsyncClient,
    auth_headers: dict
):
    response = await async_client.get(
        "/api/protected",
        headers=auth_headers
    )
    assert response.status_code == 200
```

## 参考资料

- [Pytest 官方文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [FastAPI 测试指南](https://fastapi.tiangolo.com/tutorial/testing/)
- [httpx 测试客户端](https://www.python-httpx.org/advanced/#calling-into-python-web-apps)
- [SQLModel 文档](https://sqlmodel.tiangolo.com/)

## 贡献

如果您发现文档中的错误或有改进建议，请：

1. 在项目中创建 Issue
2. 提交 Pull Request
3. 更新相关文档

---

更新时间: 2025-12-19
