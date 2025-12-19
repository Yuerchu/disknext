# 集成测试文档

## 概述

本目录包含 DiskNext Server 的集成测试，测试覆盖主要的 API 端点和中间件功能。

## 测试结构

```
tests/integration/
├── conftest.py                    # 测试配置和 fixtures
├── api/                           # API 端点测试
│   ├── test_site.py              # 站点配置测试
│   ├── test_user.py              # 用户相关测试
│   ├── test_admin.py             # 管理员端点测试
│   ├── test_directory.py         # 目录操作测试
│   └── test_object.py            # 对象操作测试
└── middleware/                    # 中间件测试
    └── test_auth.py              # 认证中间件测试
```

## 运行测试

### 运行所有集成测试

```bash
pytest tests/integration/
```

### 运行特定测试文件

```bash
# 测试站点端点
pytest tests/integration/api/test_site.py

# 测试用户端点
pytest tests/integration/api/test_user.py

# 测试认证中间件
pytest tests/integration/middleware/test_auth.py
```

### 运行特定测试函数

```bash
pytest tests/integration/api/test_user.py::test_user_login_success
```

### 显示详细输出

```bash
pytest tests/integration/ -v
```

### 生成覆盖率报告

```bash
# 生成终端报告
pytest tests/integration/ --cov

# 生成 HTML 报告
pytest tests/integration/ --cov --cov-report=html
```

### 并行运行测试

```bash
pytest tests/integration/ -n auto
```

## 测试 Fixtures

### 数据库相关

- `test_db_engine`: 测试数据库引擎（内存 SQLite）
- `test_session`: 测试数据库会话
- `initialized_db`: 已初始化的测试数据库（包含基础数据）

### 用户相关

- `test_user_info`: 测试用户信息（username, password）
- `admin_user_info`: 管理员用户信息
- `banned_user_info`: 封禁用户信息

### 认证相关

- `test_user_token`: 测试用户的 JWT token
- `admin_user_token`: 管理员的 JWT token
- `expired_token`: 过期的 JWT token
- `auth_headers`: 测试用户的认证头
- `admin_headers`: 管理员的认证头

### 客户端

- `async_client`: 异步 HTTP 测试客户端

### 测试数据

- `test_directory_structure`: 测试目录结构（包含文件夹和文件）

## 测试覆盖范围

### API 端点测试

#### `/api/site/*` (test_site.py)
- ✅ Ping 端点
- ✅ 站点配置端点
- ✅ 配置字段验证

#### `/api/user/*` (test_user.py)
- ✅ 用户登录（成功、失败、封禁用户）
- ✅ 用户注册（成功、重复用户名）
- ✅ 获取用户信息（需要认证）
- ✅ 获取存储信息
- ✅ 两步验证初始化和启用
- ✅ 用户设置

#### `/api/admin/*` (test_admin.py)
- ✅ 认证检查（需要管理员权限）
- ✅ 获取用户列表（带分页）
- ✅ 获取用户信息
- ✅ 创建用户
- ✅ 用户组管理
- ✅ 文件管理
- ✅ 设置管理

#### `/api/directory/*` (test_directory.py)
- ✅ 获取根目录
- ✅ 获取嵌套目录
- ✅ 权限检查（不能访问他人目录）
- ✅ 创建目录（成功、重名、无效父目录）
- ✅ 目录名验证（不能包含斜杠）

#### `/api/object/*` (test_object.py)
- ✅ 删除对象（单个、批量、他人对象）
- ✅ 移动对象（成功、无效目标、移动到文件）
- ✅ 权限检查（不能操作他人对象）
- ✅ 重名检查

### 中间件测试

#### 认证中间件 (test_auth.py)
- ✅ AuthRequired: 无 token、无效 token、过期 token
- ✅ AdminRequired: 非管理员用户返回 403
- ✅ Token 格式验证
- ✅ 用户不存在处理

## 测试数据

### 默认用户

1. **测试用户**
   - 用户名: `testuser`
   - 密码: `testpass123`
   - 用户组: 默认用户组
   - 状态: 正常

2. **管理员**
   - 用户名: `admin`
   - 密码: `adminpass123`
   - 用户组: 管理员组
   - 状态: 正常

3. **封禁用户**
   - 用户名: `banneduser`
   - 密码: `banned123`
   - 用户组: 默认用户组
   - 状态: 封禁

### 测试目录结构

```
testuser/                # 根目录
├── docs/               # 文件夹
│   ├── images/        # 子文件夹
│   └── readme.md      # 文件 (1KB)
```

## 注意事项

1. **测试隔离**: 每个测试使用独立的内存数据库，互不影响
2. **异步测试**: 所有测试使用 `@pytest.mark.asyncio` 装饰器
3. **依赖覆盖**: 测试客户端自动覆盖数据库依赖，使用测试数据库
4. **JWT 密钥**: 测试环境使用固定密钥 `test_secret_key_for_jwt_token_generation`

## 添加新测试

### 1. 创建测试文件

在 `tests/integration/api/` 或 `tests/integration/middleware/` 下创建新的测试文件。

### 2. 导入必要的依赖

```python
import pytest
from httpx import AsyncClient
```

### 3. 编写测试函数

```python
@pytest.mark.asyncio
async def test_your_feature(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试描述"""
    response = await async_client.get(
        "/api/your/endpoint",
        headers=auth_headers
    )
    assert response.status_code == 200
```

### 4. 使用 fixtures

利用 `conftest.py` 提供的 fixtures：

```python
@pytest.mark.asyncio
async def test_with_directory_structure(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """使用测试目录结构"""
    root_id = test_directory_structure["root_id"]
    # ... 测试逻辑
```

## 故障排除

### 测试失败：数据库初始化错误

检查是否所有必要的模型都已导入到 `conftest.py` 中。

### 测试失败：JWT 密钥未设置

确保 `initialized_db` fixture 正确设置了 `JWT.SECRET_KEY`。

### 测试失败：认证失败

检查 token 生成逻辑是否使用正确的密钥和用户名。

## 持续集成

建议在 CI/CD 流程中运行集成测试：

```yaml
# .github/workflows/test.yml
- name: Run integration tests
  run: |
    pytest tests/integration/ -v --cov --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```
