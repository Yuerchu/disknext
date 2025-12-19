# 测试快速参考

## 常用命令

```bash
# 运行所有测试
pytest

# 运行特定文件
pytest tests/unit/models/test_user.py

# 运行特定测试
pytest tests/unit/models/test_user.py::test_user_create

# 带详细输出
pytest -v

# 带覆盖率
pytest --cov

# 生成 HTML 覆盖率报告
pytest --cov --cov-report=html

# 并行运行（需要 pytest-xdist）
pytest -n auto

# 只运行失败的测试
pytest --lf

# 显示所有输出（包括 print）
pytest -s

# 停在第一个失败
pytest -x
```

## 使用测试脚本

```bash
# 检查环境
python tests/check_imports.py

# 运行所有测试
python run_tests.py

# 运行特定模块
python run_tests.py models
python run_tests.py utils
python run_tests.py service

# 带覆盖率
python run_tests.py --cov
```

## 常用 Fixtures

### 数据库

```python
async def test_example(db_session: AsyncSession):
    """使用数据库会话"""
    pass
```

### 测试用户

```python
async def test_with_user(db_session: AsyncSession, test_user: dict):
    """使用测试用户"""
    user_id = test_user["id"]
    username = test_user["username"]
    password = test_user["password"]
    token = test_user["token"]
```

### 认证请求头

```python
def test_api(auth_headers: dict):
    """使用认证请求头"""
    headers = auth_headers  # {"Authorization": "Bearer ..."}
```

## 编写新测试模板

```python
"""
模块名称的单元测试
"""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from models.your_model import YourModel


@pytest.mark.asyncio
async def test_feature_description(db_session: AsyncSession):
    """测试功能的简短描述"""
    # 准备: 创建测试数据
    instance = YourModel(field="value")
    instance = await instance.save(db_session)

    # 执行: 调用被测试的方法
    result = await YourModel.get(
        db_session,
        YourModel.id == instance.id
    )

    # 验证: 断言结果符合预期
    assert result is not None
    assert result.field == "value"
```

## 常见断言

```python
# 相等
assert value == expected

# 不相等
assert value != expected

# 真假
assert condition is True
assert condition is False

# 包含
assert item in collection
assert item not in collection

# 类型检查
assert isinstance(value, int)

# 异常检查
import pytest
with pytest.raises(ValueError):
    function_that_raises()

# 近似相等（浮点数）
assert abs(value - expected) < 0.001

# 多个条件
assert all([
    condition1,
    condition2,
    condition3,
])
```

## 数据库操作示例

```python
# 创建
user = User(username="test", password="pass")
user = await user.save(db_session)

# 查询
user = await User.get(
    db_session,
    User.username == "test"
)

# 更新
update_data = UserBase(username="new_name")
user = await user.update(db_session, update_data)

# 删除
await User.delete(db_session, user)

# 批量创建
users = [User(...), User(...)]
await User.add(db_session, users)

# 加载关系
user = await User.get(
    db_session,
    User.id == user_id,
    load=User.group  # 加载关系
)
```

## 测试组织

```
tests/
├── conftest.py              # 共享 fixtures
├── unit/                    # 单元测试
│   ├── models/              # 模型测试
│   ├── utils/               # 工具测试
│   └── service/             # 服务测试
└── integration/             # 集成测试（待添加）
```

## 调试技巧

```bash
# 显示 print 输出
pytest -s

# 进入 pdb 调试器
pytest --pdb

# 在第一个失败处停止
pytest -x --pdb

# 显示详细错误信息
pytest -vv

# 显示最慢的 10 个测试
pytest --durations=10
```

## 标记测试

```python
# 标记为慢速测试
@pytest.mark.slow
def test_slow_operation():
    pass

# 跳过测试
@pytest.mark.skip(reason="暂未实现")
def test_future_feature():
    pass

# 条件跳过
@pytest.mark.skipif(condition, reason="...")
def test_conditional():
    pass

# 预期失败
@pytest.mark.xfail
def test_known_bug():
    pass
```

运行特定标记:

```bash
pytest -m slow        # 只运行慢速测试
pytest -m "not slow"  # 排除慢速测试
```

## 覆盖率报告

```bash
# 终端输出
pytest --cov

# HTML 报告（推荐）
pytest --cov --cov-report=html
# 打开 htmlcov/index.html

# XML 报告（CI/CD）
pytest --cov --cov-report=xml

# 只看未覆盖的行
pytest --cov --cov-report=term-missing
```

## 性能提示

```bash
# 并行运行（快 2-4 倍）
pytest -n auto

# 只运行上次失败的
pytest --lf

# 先运行失败的
pytest --ff

# 禁用输出捕获（略快）
pytest --capture=no
```

## 常见问题排查

### 导入错误

```bash
# 检查导入
python tests/check_imports.py

# 确保从项目根目录运行
cd c:\Users\Administrator\Documents\Code\Server
pytest
```

### 数据库错误

所有测试使用内存数据库,不需要外部数据库。如果遇到错误:

```python
# 检查 conftest.py 是否正确配置
# 检查是否使用了正确的 fixture
async def test_example(db_session: AsyncSession):
    pass
```

### Fixture 未找到

```python
# 确保 conftest.py 在正确位置
# 确保 fixture 名称拼写正确
# 检查 fixture 的 scope
```

## 资源

- [pytest 文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [SQLModel 文档](https://sqlmodel.tiangolo.com/)
- [FastAPI 测试文档](https://fastapi.tiangolo.com/tutorial/testing/)
