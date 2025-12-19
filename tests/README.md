# DiskNext Server 单元测试文档

## 测试结构

```
tests/
├── conftest.py              # Pytest 配置和 fixtures
├── unit/                    # 单元测试
│   ├── models/              # 模型层测试
│   │   ├── test_base.py     # TableBase/UUIDTableBase 测试
│   │   ├── test_user.py     # User 模型测试
│   │   ├── test_group.py    # Group/GroupOptions 测试
│   │   ├── test_object.py   # Object 模型测试
│   │   └── test_setting.py  # Setting 模型测试
│   ├── utils/               # 工具层测试
│   │   ├── test_password.py # Password 工具测试
│   │   └── test_jwt.py      # JWT 工具测试
│   └── service/             # 服务层测试
│       └── test_login.py    # Login 服务测试
└── README.md                # 本文档

```

## 运行测试

### 安装依赖

```bash
# 使用 uv (推荐)
uv sync

# 或使用 pip
pip install -e .
```

### 运行所有测试

```bash
pytest
```

### 运行特定测试文件

```bash
# 测试模型层
pytest tests/unit/models/test_base.py

# 测试用户模型
pytest tests/unit/models/test_user.py

# 测试工具层
pytest tests/unit/utils/test_password.py

# 测试服务层
pytest tests/unit/service/test_login.py
```

### 运行特定测试函数

```bash
pytest tests/unit/models/test_base.py::test_table_base_add_single
```

### 运行带覆盖率的测试

```bash
# 生成覆盖率报告
pytest --cov

# 生成 HTML 覆盖率报告
pytest --cov --cov-report=html

# 查看 HTML 报告
# 打开 htmlcov/index.html
```

### 并行测试

```bash
# 使用所有 CPU 核心
pytest -n auto

# 使用指定数量的核心
pytest -n 4
```

## Fixtures 说明

### 数据库相关

- `test_engine`: 内存 SQLite 数据库引擎
- `initialized_db`: 已初始化表结构的数据库
- `db_session`: 数据库会话（每个测试函数独立）

### 用户相关（在 conftest.py 中已提供）

- `test_user`: 创建测试用户，返回 {id, username, password, token, group_id, policy_id}
- `admin_user`: 创建管理员用户
- `auth_headers`: 测试用户的认证请求头
- `admin_headers`: 管理员的认证请求头

### 数据相关

- `test_directory`: 为测试用户创建目录结构

## 测试覆盖范围

### 模型层 (tests/unit/models/)

#### test_base.py - TableBase/UUIDTableBase
- ✅ 单条记录创建
- ✅ 批量创建
- ✅ save() 方法
- ✅ update() 方法
- ✅ delete() 方法
- ✅ get() 三种 fetch_mode
- ✅ offset/limit 分页
- ✅ get_exist_one() 存在/不存在场景
- ✅ UUID 自动生成
- ✅ 时间戳自动维护

#### test_user.py - User 模型
- ✅ 创建用户
- ✅ 用户名唯一约束
- ✅ to_public() DTO 转换
- ✅ 用户与用户组关系
- ✅ status 默认值
- ✅ storage 默认值
- ✅ ThemeType 枚举

#### test_group.py - Group/GroupOptions 模型
- ✅ 创建用户组
- ✅ 用户组与选项一对一关系
- ✅ to_response() DTO 转换
- ✅ 多对多关系（policies）

#### test_object.py - Object 模型
- ✅ 创建目录
- ✅ 创建文件
- ✅ is_file 属性
- ✅ is_folder 属性
- ✅ get_root() 方法
- ✅ get_by_path() 根目录
- ✅ get_by_path() 嵌套路径
- ✅ get_by_path() 路径不存在
- ✅ get_children() 方法
- ✅ 父子关系
- ✅ 同目录名称唯一约束

#### test_setting.py - Setting 模型
- ✅ 创建设置
- ✅ type+name 唯一约束
- ✅ SettingsType 枚举
- ✅ 更新设置值

### 工具层 (tests/unit/utils/)

#### test_password.py - Password 工具
- ✅ 默认长度生成密码
- ✅ 自定义长度生成密码
- ✅ 密码哈希
- ✅ 正确密码验证
- ✅ 错误密码验证
- ✅ TOTP 密钥生成
- ✅ TOTP 验证正确
- ✅ TOTP 验证错误

#### test_jwt.py - JWT 工具
- ✅ 访问令牌创建
- ✅ 自定义过期时间
- ✅ 刷新令牌创建
- ✅ 令牌解码
- ✅ 令牌过期
- ✅ 无效签名

### 服务层 (tests/unit/service/)

#### test_login.py - Login 服务
- ✅ 正常登录
- ✅ 用户不存在
- ✅ 密码错误
- ✅ 用户被封禁
- ✅ 需要 2FA
- ✅ 2FA 错误
- ✅ 2FA 成功

## 常见问题

### 1. 数据库连接错误

所有测试使用内存 SQLite 数据库，不需要外部数据库服务。

### 2. 导入错误

确保从项目根目录运行测试：

```bash
cd c:\Users\Administrator\Documents\Code\Server
pytest
```

### 3. 异步测试错误

项目已配置 `pytest-asyncio`，使用 `@pytest.mark.asyncio` 装饰器即可。

### 4. Fixture 依赖错误

检查 conftest.py 中是否定义了所需的 fixture，确保使用正确的参数名。

## 编写新测试

### 模板

```python
"""
模块名称的单元测试
"""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from models.xxx import YourModel


@pytest.mark.asyncio
async def test_your_feature(db_session: AsyncSession):
    """测试功能描述"""
    # 准备数据
    instance = YourModel(field="value")
    instance = await instance.save(db_session)

    # 执行操作
    result = await YourModel.get(db_session, YourModel.id == instance.id)

    # 断言验证
    assert result is not None
    assert result.field == "value"
```

## 持续集成

项目配置了覆盖率要求（80%），确保新代码有足够的测试覆盖。

```bash
# 检查覆盖率是否达标
pytest --cov --cov-fail-under=80
```
