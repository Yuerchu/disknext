# DiskNext Server 开发规范

> `CLAUDE.md` 是本项目开发规范的唯一真相源。

## 项目环境

- 项目路径: `C:\Users\Administrator\Documents\Code\disknext`
- 虚拟环境: `.venv\Scripts\python.exe` (Python 3.14.0)
  - 重要: 虚拟环境目录名是`.venv`，不是其他变体
- 运行Python命令:

  ```bash
  # 单行命令
  .venv/Scripts/python.exe -c "print('hello')"
  # 运行脚本
  .venv/Scripts/python.exe script.py
  ```

- 运行pytest:

  ```bash
  .venv/Scripts/python.exe -m pytest ...
  ```

- 安装依赖: `uv add <package>` (自动更新pyproject.toml和uv.lock)
- 同步依赖: `uv sync`

### Docker 基础设施端口分配

| 服务       | 开发 |
|------------|------|
| PostgreSQL | 5432 |
| Redis      | 6379 |

### 数据库迁移

项目目前不使用 Alembic，启动时通过 `DatabaseManager.init()` + `SQLModel.metadata.create_all()` 创建表，`migration.py` 负责初始化种子数据。

### 进程管理（Windows）

- `taskkill /f /pid <PID>` 对 uvicorn multiworker 主进程可能无效（子进程持有 socket 句柄导致主进程不可终止）
- 正确做法：`wmic process where "CommandLine like '%main.py%'" delete`（WMI 内核接口，绕过句柄保护）
- 验证端口释放：`netstat -aon | grep ":8000" | grep LISTEN || echo "free"`

## 设计哲学

### 1. 严格的类型安全与显式优于隐式

- 拒绝泛型（dict/list），须具体类型（dict[str, str]）
- 拒绝Any类型，除非真的无法确定（需TODO标记）
- Python 3.10+语法强制（int | None而非Optional[int]）
- 所有参数、返回值、变量都须有类型注解
- 引用任何属性前须先查看类实现确认存在

### 2. 充血模型与运行时状态管理

- 充血模型：SQLModel实例同时含数据库字段和业务方法
- 运行时状态：`model_post_init()`初始化运行时属性（`_`开头），不存数据库
- ClassVar管理跨实例状态：用于全局单例或共享状态管理
- 严禁动态添加属性：所有属性须在`model_post_init()`或类定义中声明
- 会话参数化：方法接收`session: AsyncSession`参数，不存储session引用

### 3. 单一真相来源（Single Source of Truth）

- 代码规范只有本文档
- SQLModelBase定义了model_config，子类勿重复定义
- ServerConfig直接存属性（port），非嵌套结构（server.port）
- 配置从数据库读取 + 环境变量（`utils/conf/appmeta.py`）

### 4. 异步优先，IO绝不阻塞

- 所有IO操作须是async/await
- 禁止创建新的事件循环（用FastAPI管理的）
- 同步库须用to_thread或Celery Worker隔离
- 数据库、HTTP、文件操作都是异步（AsyncSession, aiohttp, aiofiles）

### 5. 组合优于继承，聚合优于散布

- 组合而非继承
- Mixin用于横切关注点
- 联表继承仅在数据库多态时用
- 逻辑聚合在实体类中：避免分散到辅助类

### 6. 目录结构即API结构

- URL路径/api/v1/user须对应routers/api/v1/user/__init__.py
- 禁止独立.py文件，只允许__init__.py和子目录
- 每个目录的__init__.py负责定义该层级的路由

### 7. 错误快速失败，而非隐藏

- 禁止返回None来表示错误（会隐藏问题）
- 须抛出异常，让FastAPI捕获并统一返回500
- 端点勿自己处理异常（除非有特殊逻辑）

### 8. 模块内聚，跨模块松耦合

- 通过__init__.py明确导出API，隐藏内部实现
- 依赖注入而非全局变量（SessionDep, ServerConfigDep）

### 9. 约定优于配置

- SQLModelBase自动配置use_attribute_docstrings
- 字段用docstring描述，而非Field(description=...)

### 10. 清晰的所有权和生命周期

- 传输层独立管理（HTTP由routers管理，WebDAV由routers/dav管理）
- ClassVar管理全局单例（如DatabaseManager.engine）
- `@asynccontextmanager`管理资源生命周期
- 断开时清理资源（取消任务、关闭连接、保存状态）

### 11. 文档即代码

- Docstring不是可选的，复杂逻辑须写
- 类型注解本身就是文档
- 字段描述用docstring（自动生成API文档）

### 12. Breaking Changes优先，不维护向后兼容

- 拒绝兼容层：重构时直接删除旧代码，更新所有引用
- 不保留废弃代码：避免deprecated目录积累技术债务
- 一次性更新所有引用：重命名/移动模块时同时更新所有import

## 代码规范

### 基础格式规范

- UTF-8编码，4空格缩进（不用Tab），文件末尾须有换行符
- PR/commit时勿有任何语法错误（红线）

### 类型注解规范

- Python 3.10+语法：`dict[str, Any] | None`非`Optional[Dict[str, Any]]`
- 字符串可空类型用单引号包裹整体：`'TypeName | None'`（非`"TypeName" | None`）
- 用内置类型：`type[ClassName]`非`Type[ClassName]`，`list[int]`非`List[int]`
- 参数、类变量、实例变量、函数返回都须类型注解
- 禁用Any/object，除非无法确定（需TODO标注）
- 禁用字符串类型，除非前向引用（类型未定义）
- SQLModel Relationship例外：可空前向引用须用`Optional['TypeName']`非`'TypeName' | None`

```python
# ❌ 错误：SQLModel Relationship不支持这些形式
admin: 'User' | None = Relationship(...)  # 语法错误
admin: 'User | None' = Relationship(...)  # SQLModel无法解析
# ✅ 正确：使用Optional
from typing import Optional
admin: Optional['User'] = Relationship(...)
```

### 异步编程规范

- 用FastAPI管理的事件循环，禁止新建事件循环（任何线程/子进程都不行）
- IO操作用协程，非CPU密集/IO操作不用协程，按需用to_thread/Celery Worker
- 数据库用异步驱动（AsyncSession）、HTTP用aiohttp、文件用aiofiles、子进程用anyio
- 第三方库用异步版本，没有则视cpu负载用to_thread/Celery Worker

### 函数与参数规范

一个方法最多五个参数，多了考虑拆分方法或合并参数（SQLModel），勿简单用tuple或dict

### 代码格式规范

- 容器类型定义：单行不加尾逗号，多行加尾逗号
- 括号换行：要么不换行，要么换行且一行最多一个变量

```python
from loguru import logger as l
from api_client_models import (
    AgentModelsRequest,
    ReportRequest,
    SaveMemoryRequest,
    UserInfoResponse,
)
async def lookup_user_info(
        session: AsyncSession,
        user_id: int,
        short_name: str,
        data_1_with_a_long_name: dict[str, Any] | None,
        data_2_with_a_even_longer_name: CustomType
) -> UserInfoResponse:
    user = await User.get(session, User.id == user_id)
    new_dict = { user_id, short_name }
    l.debug(f"查到的数据: {new_dict}")
    result = UserInfoResponse(
        user.id,
        user.a_long_attribute,
        data_1_with_a_long_name,
        data_2_with_a_even_longer_name,
    )
    return result
```

### 文档与注释规范

复杂的类或函数（无法从名字推断明确操作，如`handle_connection()`）一律写docstring，采用reStructuredText风格

### 字符串处理规范

- 引号：单引号`'`用于给电脑看的文本（字典键），双引号`"`用于给人看的文本（用户提示、log信息等）
- 格式化：所有字符串用f-string格式化，不用`%`或`.format()`
- 多行字符串：`"""`给人看(如docstring)，`'''`给机器看（如SQL、HTML）

### 命名规范

- 禁止拼音变量名（专有名词除外），须英文
- 变量/函数/方法/参数用snake_case，类用PascalCase，常量用UPPER_SNAKE_CASE
- 私有用`_`前缀，非常私有用`__`前缀
- 布尔变量用is_/has_/can_/should_前缀，须是形容词或动词短语

### 禁止生产代码使用 assert

生产代码禁止 `assert`：`assert` 在 `python -O` 模式下被跳过，不适合做运行时守卫。

```python
# ❌ 错误：assert 在优化模式下被跳过，守卫失效
assert user is not None, "用户不存在"

# ✅ 正确：显式 raise，任何模式下都执行
if user is None:
    raise ValueError("用户不存在")
```

例外：测试代码（tests/）可以使用 `assert`；`ClassVar` 全局单例的初始化检查保持现有 `assert`（见全局状态管理规范）。

### 异常处理规范

- 所有异常须被捕获，且有明确处理逻辑
- 出现错误勿return None，须明确抛出异常

### 全局状态管理规范

严格禁止用`global`关键字。对于需要跨函数/模块共享的状态（全局单例），须用纯classmethod模式：

```python
from typing import ClassVar
class ServiceName:
    """纯classmethod模式，全局单例。此类永不实例化"""
    _resource: ClassVar[ResourceType | None] = None
    def __new__(cls, *args, **kwargs) -> 'ServiceName':
        raise RuntimeError(f"{cls.__name__} 是纯classmethod单例，禁止实例化")
    @classmethod
    def init(cls, config: ConfigType) -> None:
        if cls._resource is not None:
            return  # 已初始化，幂等返回
        cls._resource = create_resource(config)
    @classmethod
    def shutdown(cls) -> None:
        if cls._resource is None:
            return
        cls._resource.close()
        cls._resource = None
    @classmethod
    def get_resource(cls) -> ResourceType:
        assert cls._resource is not None, f"{cls.__name__} 未初始化，请先调用 init()"
        return cls._resource
```

项目实例：`DatabaseManager`、`RedisManager`、`S3StorageService`

### 日志处理规范

- 用`from loguru import logger as l`，不用print
- 日志须有明确上下文和级别

### 框架使用规范

- SQLModel（禁止从future导入annotations），而非Pydantic或SQLAlchemy
- FastAPI而非Flask或Django
- Aiohttp而非Requests
- Aiofiles而非内置open：

```python
import os as sync_os
from aiofiles import os, open
async with open('file.txt', 'r') as f:
    content = await f.read()
path = sync_os.path(...)
```

- Anyio而非内置subprocess
- Loguru而非内置logging：`from loguru import logger as l`

### JSON处理规范

永远用SQLModel/Pydantic的内置序列化方法，不手动调用json库：

```python
# ✅ 正确：使用 model_dump_json()
message = TextEchoMessage(text="你好", msg_id="123")
json_str: str = message.model_dump_json()  # 直接返回JSON字符串
message_dict: dict = message.model_dump()  # 如果需要字典
# ✅ 原始JSON处理用orjson
import orjson
data: dict = orjson.loads(json_bytes)  # 解析
json_bytes: bytes = orjson.dumps(data)  # 生成
# ❌ 错误：使用标准库json
import json
json_str = json.dumps(message.model_dump())
```

### 安全规范

- 敏感信息：存放在 `.env` 文件（不进版本控制），通过 `utils/conf/appmeta.py` 使用 `python-dotenv` 加载
- SQL注入防护：用参数化查询，禁止拼接SQL
- JWT认证：WebSocket和敏感端点须验证token
- CORS配置：生产环境须正确配置（当前仅debug模式启用全开放CORS）

### SQLModel规范

用字段后面的"""..."""（docstring）而非description="..."来写字段描述：

```python
class User(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True, description="用户ID")  # ❌ 错误
    name: str = Field(description="用户名")  # ❌ 错误
    email: str = Field(unique=True)  # ✅ 正确
    """用户邮箱"""
```

Field使用原则：

- 只有default时：直接赋值，不用Field
- 有其他参数时（ge, le, foreign_key, unique等）：须用Field

```python
# ❌ 错误
class CharacterConfig(SQLModelBase):
    vad_frame_ms: int = Field(default=20)  # 只有default，不应该用Field
# ✅ 正确
class CharacterConfig(SQLModelBase):
    vad_frame_ms: int = 20  # 只有default，直接赋值
    """VAD帧大小（毫秒）"""
    vad_aggressiveness: int = Field(default=2, ge=0, le=3)  # 有约束，使用Field
    """VAD激进程度（0-3）"""
    llm_id: UUID = Field(..., foreign_key='llm.id')  # 有foreign_key，使用Field
    """LLM配置ID"""
```

其他规范：

- 勿重复定义model_config：SQLModelBase已定义`model_config = ConfigDict(use_attribute_docstrings=True, validate_by_name=True)`，子类无需重复定义
- 一律用TableBase系列类提供的CRUD，不直接操作session
- 所有SQLModel类须继承自SQLModelBase或其子类
- 存数据库的类须继承自TableBase的子类并且table=True
- 不存数据库的类须继承自SQLModelBase
- 枚举类用`StrEnum`而非`(str, Enum)`

### TableBase CRUD方法返回值规范

须用返回值：`save()`/`update()`后session中对象过期，须用返回值：

```python
# ✅ 正确：使用返回值
device = ClientDevice(...)
device = await device.save(session)
return device

# ❌ 错误：不使用返回值（device对象已过期）
device = ClientDevice(...)
await device.save(session)
return device  # 此时device已过期，访问属性会报错
```

sqlmodel_ext 提供了 cond 和 rel 对 crud 进行适配，在编写这些端点时，必须使用他们：

```python
from sqlmodel_ext import cond, rel

user = User.get(session, User.email == email, load=[User.group, User.tags])                 # 错误
user = User.get(session, cond(User.email == email), load=[rel(User.group), rel(User.tags)]) # 正确
```

### `__init__.py`模块组织规范

根据场景用不同组织模式。

__模式一：模块导出（SQLModel/业务模块）__
从子模块收集重新导出公共API。

```python
# sqlmodels/user/__init__.py
from .user import (
    User,
    UserInfoResponse,
    UserLoginOrRegisterRequest,
)
```

__模式二：FastAPI路由聚合（中间节点）__
构建层级化API路由结构。

```python
# routers/__init__.py
from fastapi import APIRouter
from .api import router as api_router
router = APIRouter()
router.include_router(api_router)
```

__模式三：FastAPI端点实现（叶子节点）__
在`__init__.py`中直接定义端点。

```python
# routers/api/v1/user/__init__.py
from fastapi import APIRouter
from middleware.dependencies import SessionDep
from sqlmodels.user import User

router = APIRouter(prefix="/user", tags=["user"])

@router.post("")
async def create_user(session: SessionDep, ...):
    """创建用户"""
    pass
```

路由层次：

```
routers/                → /
├── api/                → /api
│   └── v1/             → /api/v1
│       ├── user/       → /api/v1/user
│       ├── file/       → /api/v1/file
│       ├── share/      → /api/v1/share
│       ├── admin/      → /api/v1/admin
│       └── ...
├── dav/                → /dav (WebDAV)
└── wopi/               → /wopi (WOPI协议)
```

命名约定：

- 相对导入用`from .xxx import ...`
- 子路由用`from .子目录 import router as 子目录_router`
- 禁止`__all__`

导入顺序规范（符合PEP 8）：

```python
# 1. 标准库导入
from typing import Any
from uuid import UUID

# 2. 第三方库导入
from fastapi import APIRouter
from loguru import logger as l

# 3. 本地应用导入
from middleware.dependencies import SessionDep
from sqlmodels.user import User

# 4. 相对导入
from .base import BaseClass
```

每组之间用一个空行分隔，同组内按字母顺序排序，相对导入永远放在最后。

### 项目目录结构说明

| 目录 | 职责 |
|------|------|
| `routers/` | HTTP路由（FastAPI端点） |
| `routers/api/v1/` | REST API v1 端点 |
| `routers/dav/` | WebDAV协议端点 |
| `routers/wopi/` | WOPI协议端点（Office在线编辑） |
| `sqlmodels/` | 数据模型（SQLModel类、DTO、枚举） |
| `middleware/` | 中间件（认证、依赖注入） |
| `service/` | 业务服务层 |
| `utils/` | 工具函数和通用组件 |
| `tests/` | 测试目录 |

---

此规范持续更新，未提到的参考 [PEP 8](https://peps.python.org/pep-0008/)
