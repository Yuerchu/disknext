# 集成测试快速参考

## 快速命令

```bash
# 运行所有测试
pytest tests/integration/ -v

# 运行特定类别
pytest tests/integration/api/ -v              # 所有 API 测试
pytest tests/integration/middleware/ -v       # 所有中间件测试

# 运行单个文件
pytest tests/integration/api/test_user.py -v

# 运行单个测试
pytest tests/integration/api/test_user.py::test_user_login_success -v

# 生成覆盖率
pytest tests/integration/ --cov --cov-report=html

# 并行运行
pytest tests/integration/ -n auto

# 显示详细输出
pytest tests/integration/ -vv -s
```

## 测试文件速查

| 文件 | 测试内容 | 端点前缀 |
|------|---------|---------|
| `test_site.py` | 站点配置 | `/api/site/*` |
| `test_user.py` | 用户操作 | `/api/user/*` |
| `test_admin.py` | 管理员功能 | `/api/admin/*` |
| `test_directory.py` | 目录操作 | `/api/directory/*` |
| `test_object.py` | 对象操作 | `/api/object/*` |
| `test_auth.py` | 认证中间件 | - |

## 常用 Fixtures

```python
# HTTP 客户端
async_client: AsyncClient

# 认证
auth_headers: dict[str, str]          # 普通用户
admin_headers: dict[str, str]         # 管理员

# 数据库
initialized_db: AsyncSession          # 预填充的测试数据库
test_session: AsyncSession            # 空的测试会话

# 用户信息
test_user_info: dict                  # {"username": "testuser", "password": "testpass123"}
admin_user_info: dict                 # {"username": "admin", "password": "adminpass123"}

# 测试数据
test_directory_structure: dict        # {"root_id": UUID, "docs_id": UUID, ...}

# Tokens
test_user_token: str                  # 有效的用户 token
admin_user_token: str                 # 有效的管理员 token
expired_token: str                    # 过期的 token
```

## 测试模板

### 基础 API 测试
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_endpoint_name(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试描述"""
    response = await async_client.get(
        "/api/path",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

### 需要测试数据的测试
```python
@pytest.mark.asyncio
async def test_with_data(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """使用预创建的测试数据"""
    folder_id = test_directory_structure["docs_id"]
    # 测试逻辑...
```

### 认证测试
```python
@pytest.mark.asyncio
async def test_requires_auth(async_client: AsyncClient):
    """测试需要认证"""
    response = await async_client.get("/api/protected")
    assert response.status_code == 401
```

### 权限测试
```python
@pytest.mark.asyncio
async def test_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试需要管理员权限"""
    response = await async_client.get(
        "/api/admin/endpoint",
        headers=auth_headers
    )
    assert response.status_code == 403
```

## 测试数据

### 默认用户
- **testuser** / testpass123 (普通用户)
- **admin** / adminpass123 (管理员)
- **banneduser** / banned123 (封禁用户)

### 目录结构
```
testuser/
├── docs/
│   ├── images/
│   └── readme.md (1KB)
```

## 常见断言

```python
# 状态码
assert response.status_code == 200
assert response.status_code == 401  # 未认证
assert response.status_code == 403  # 权限不足
assert response.status_code == 404  # 不存在
assert response.status_code == 409  # 冲突

# 响应数据
data = response.json()
assert "field" in data
assert data["field"] == expected_value
assert isinstance(data["list"], list)

# 列表长度
assert len(data["items"]) > 0
assert len(data["items"]) <= page_size

# 嵌套数据
assert "nested" in data
assert "field" in data["nested"]
```

## 调试技巧

```bash
# 显示完整输出
pytest tests/integration/api/test_user.py -vv -s

# 只运行失败的测试
pytest tests/integration/ --lf

# 遇到第一个失败就停止
pytest tests/integration/ -x

# 显示最慢的 10 个测试
pytest tests/integration/ --durations=10

# 使用 pdb 调试
pytest tests/integration/ --pdb
```

## 故障排查

### 问题: 测试全部失败
```bash
# 检查依赖
pip install -e .

# 检查 Python 路径
python -c "import sys; print(sys.path)"
```

### 问题: JWT 相关错误
```python
# 检查 JWT 密钥是否设置
from utils.JWT import JWT
print(JWT.SECRET_KEY)
```

### 问题: 数据库错误
```python
# 确保所有模型都已导入
from models import *
```

## 性能基准

预期测试时间（参考）:
- 单个测试: < 1s
- 整个文件: < 10s
- 所有集成测试: < 1min

如果超过这些时间，检查:
1. 数据库连接
2. 异步配置
3. Fixtures 作用域

## 相关文档

- [README.md](README.md) - 详细的测试文档
- [conftest.py](conftest.py) - Fixtures 定义
- [../../INTEGRATION_TESTS_SUMMARY.md](../../INTEGRATION_TESTS_SUMMARY.md) - 实现总结
