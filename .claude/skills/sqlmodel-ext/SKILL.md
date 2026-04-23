---
name: sqlmodel-ext
description: |
    sqlmodel-ext 库开发参考。当代码 import sqlmodel_ext，或涉及 SQLModelBase、ExtraIgnoreModelBase、
    TableBaseMixin、UUIDTableBaseMixin、PolymorphicBaseMixin、AutoPolymorphicIdentityMixin、
    OptimisticLockMixin、CachedTableBaseMixin、RelationPreloadMixin、requires_relations、
    字段类型（Str64、HttpUrl、SafeHttpUrl、IPAddress、Array、NumpyVector 等）、
    分页（ListResponse、TableViewRequest）、响应 DTO（UUIDIdDatetimeInfoMixin 等）时使用。
user-invocable: false
paths: "**/*.py"
---

# sqlmodel-ext 开发参考

> SQLModel 增强库（v0.3.0）：智能元类、异步 CRUD Mixin、多态继承、乐观锁、关系预加载、Redis 缓存、可复用字段类型。

详细 API 参考见 [reference.md](./reference.md)。

## 核心约束（强制）

### MRO 顺序

Mixin 继承顺序影响行为，必须遵守：

- `CachedTableBaseMixin` 必须在 `UUIDTableBaseMixin` **之前**
- `OptimisticLockMixin` 必须在 `UUIDTableBaseMixin` **之前**
- JTI 子类中 `SubclassIdMixin` 必须在继承列表**第一位**

```python
# 正确
class Order(OptimisticLockMixin, UUIDTableBaseMixin, table=True): ...
class Character(CachedTableBaseMixin, CharacterBase, UUIDTableBaseMixin, table=True, cache_ttl=1800): ...
class MyTool(ToolSubclassIdMixin, Tool, AutoPolymorphicIdentityMixin, table=True): ...

# 错误
class Order(UUIDTableBaseMixin, OptimisticLockMixin, table=True): ...
class MyTool(Tool, ToolSubclassIdMixin, AutoPolymorphicIdentityMixin, table=True): ...
```

### 异步 API

- 所有 CRUD 方法均为 `async`，需要 `AsyncSession`
- `save()` 和 `update()` 返回刷新后的实例，**必须使用返回值**
- commit 后 session 中所有对象过期，之后访问属性可能报错

### 禁止事项

- 禁止使用 `from __future__ import annotations`
- 不要在异步上下文中访问未加载的关系（会触发 `MissingGreenlet`）
- `jti_subclasses` 参数必须与 `load` 参数配合使用

## 模型定义模式

### 基础模式

```python
from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str64

# Base 类（仅字段，不建表）
class UserBase(SQLModelBase):
    name: Str64
    email: str

# Table 类（自动获得 id + created_at + updated_at + 异步 CRUD）
class User(UserBase, UUIDTableBaseMixin, table=True):
    pass

# Update DTO（所有字段变为可选，保留 Annotated 约束）
class UserUpdate(UserBase, all_fields_optional=True):
    pass
```

### 两种基类

| 基类                   | `extra` 策略 | 用途                         |
| ---------------------- | ------------ | ---------------------------- |
| `SQLModelBase`         | `'forbid'`   | 默认，拒绝未知字段           |
| `ExtraIgnoreModelBase` | `'ignore'`   | 忽略未知字段（记录 WARNING） |

两者均启用 `use_attribute_docstrings=True` 和 `validate_by_name=True`。

### 两种主键 Mixin

| Mixin                | 主键类型            | 自动字段                         |
| -------------------- | ------------------- | -------------------------------- |
| `TableBaseMixin`     | `int`（自增）       | `id`, `created_at`, `updated_at` |
| `UUIDTableBaseMixin` | `UUID4`（自动生成） | `id`, `created_at`, `updated_at` |

`created_at` 和 `updated_at` 均为 UTC 带时区的 `DateTime`。

## CRUD 速查

```python
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel_ext import rel, cond

# ── 创建 ──
user = await user.save(session)                     # 插入或更新
users = await User.add(session, [user1, user2])     # 批量插入

# ── 查询 ──
user = await User.get(session, cond(User.email == "a@b.com"))           # 单条（first）
users = await User.get(session, fetch_mode="all")                       # 所有
user = await User.get(session, cond(User.id == uid), fetch_mode="one")  # 恰好一条
user = await User.get_exist_one(session, user_id)                       # 按 ID 查找或 404

# ── 分页 ──
from sqlmodel_ext import ListResponse, TableViewRequest
result = await User.get_with_count(session, table_view=table_view)
# result.count -> 总数, result.items -> 当前页

# ── 更新 ──
user = await user.update(session, UserUpdate(name="Bob"))
user = await user.update(session, data, extra_data={"updated_by": uid})

# ── 删除 ──
count = await User.delete(session, user)                                    # 按实例
count = await User.delete(session, condition=cond(User.is_active == False)) # 按条件

# ── 计数 ──
total = await User.count(session)
active = await User.count(session, condition=cond(User.is_active == True))

# ── 关系加载 ──
user = await User.get(session, cond(User.id == uid), load=rel(User.profile))
user = await User.get(session, cond(User.id == uid), load=[rel(User.profile), rel(User.orders)])

# ── FOR UPDATE 行锁 ──
user = await User.get(session, cond(User.id == uid), with_for_update=True)

# ── 类型安全辅助 ──
scope = cond(UserFile.user_id == current_user.id)          # ColumnElement[bool] 窄化
condition = scope & cond(UserFile.status == StatusEnum.ok)  # & / | 类型安全
loaded = rel(Character.llm)                                 # QueryableAttribute 窄化
```

### `get()` 的 `fetch_mode`

| 模式              | 返回类型    | 行为                       |
| ----------------- | ----------- | -------------------------- |
| `"first"`（默认） | `T \| None` | 返回第一条或 `None`        |
| `"one"`           | `T`         | 恰好一条；0 条或多条抛异常 |
| `"all"`           | `list[T]`   | 返回所有匹配记录           |

## 多态继承速查

### JTI（联表继承）

每个子类拥有独立表，通过外键关联父表。适合子类字段差异大的场景。

```python
from abc import ABC, abstractmethod
from sqlmodel_ext import (
    SQLModelBase, UUIDTableBaseMixin,
    PolymorphicBaseMixin, AutoPolymorphicIdentityMixin,
    create_subclass_id_mixin,
)

class Tool(ToolBase, UUIDTableBaseMixin, PolymorphicBaseMixin, ABC):
    @abstractmethod
    async def execute(self) -> str: ...

ToolSubclassId = create_subclass_id_mixin('tool')

class WebSearch(ToolSubclassId, Tool, AutoPolymorphicIdentityMixin, table=True):
    search_url: str
    async def execute(self) -> str: return f"Searching {self.search_url}"
```

### STI（单表继承）

所有子类共享父表。子类独有列作为 nullable 添加到父表。适合子类额外字段少的场景。

```python
class UserFile(SQLModelBase, UUIDTableBaseMixin, PolymorphicBaseMixin, table=True):
    filename: str

class PendingFile(UserFile, AutoPolymorphicIdentityMixin, table=True):
    upload_deadline: datetime | None = None

# 所有模型定义完成后：
register_sti_columns_for_all_subclasses()              # configure_mappers() 之前
register_sti_column_properties_for_all_subclasses()    # configure_mappers() 之后
```

### 查询多态模型

```python
# 返回具体子类实例
tools = await Tool.get(session, fetch_mode="all")

# 加载多态关系 + 所有子类数据
tool_set = await ToolSet.get(
    session, cond(ToolSet.id == ts_id),
    load=rel(ToolSet.tools), jti_subclasses='all',
)
```

## 乐观锁速查

```python
from sqlmodel_ext import OptimisticLockMixin, OptimisticLockError

# MRO：OptimisticLockMixin 在 UUIDTableBaseMixin 之前
class Order(OptimisticLockMixin, UUIDTableBaseMixin, table=True):
    status: str
    amount: int
# 自动添加 version: int = 0 字段

# 手动处理冲突
try:
    order = await order.save(session)
except OptimisticLockError as e:
    print(f"冲突: {e.model_class} id={e.record_id}, 期望版本: {e.expected_version}")

# 自动重试（推荐）
order = await order.save(session, optimistic_retry_count=3)
order = await order.update(session, data, optimistic_retry_count=3)
```

## 关系预加载速查

```python
from sqlmodel_ext.mixins import RelationPreloadMixin, requires_relations, requires_for_update

class MyFunction(SQLModelBase, UUIDTableBaseMixin, RelationPreloadMixin, table=True):
    generator: Generator = Relationship()

    @requires_relations('generator', Generator.config)
    async def calculate_cost(self, session) -> int:
        # generator 和 generator.config 在执行前自动加载
        return self.generator.config.price * 10

    @requires_for_update
    async def adjust_balance(self, session, *, amount: int) -> None:
        # 必须先用 get(with_for_update=True) 获取实例
        self.balance += amount
        await self.save(session)
```

**特性：**

- 声明式：调用方无需关心关系加载
- 增量式：已加载的关系不重复加载
- 导入时验证：字符串关系名在类创建时即被校验
- 支持异步生成器

## 字段类型速查

### 字符串约束

| 类型      | 最大长度 | 类型       | 最大长度  |
| --------- | -------- | ---------- | --------- |
| `Str16`   | 16       | `Text1K`   | 1,000     |
| `Str24`   | 24       | `Text1024` | 1,024     |
| `Str32`   | 32       | `Text2K`   | 2,000     |
| `Str36`   | 36       | `Text2500` | 2,500     |
| `Str48`   | 48       | `Text3K`   | 3,000     |
| `Str64`   | 64       | `Text5K`   | 5,000     |
| `Str100`  | 100      | `Text10K`  | 10,000    |
| `Str128`  | 128      | `Text32K`  | 32,000    |
| `Str255`  | 255      | `Text60K`  | 60,000    |
| `Str256`  | 256      | `Text64K`  | 65,536    |
| `Str500`  | 500      | `Text100K` | 100,000   |
| `Str512`  | 512      | `Text1M`   | 1,000,000 |
| `Str2048` | 2,048    |            |           |

### 数值约束

| 类型                | 范围      | SA 类型    |
| ------------------- | --------- | ---------- |
| `Port`              | 1--65535  | Integer    |
| `Percentage`        | 0--100    | Integer    |
| `PositiveInt`       | 1--2^31-1 | Integer    |
| `NonNegativeInt`    | 0--2^31-1 | Integer    |
| `PositiveBigInt`    | 1--2^53-1 | BigInteger |
| `NonNegativeBigInt` | 0--2^53-1 | BigInteger |
| `PositiveFloat`     | > 0.0     | Float      |
| `NonNegativeFloat`  | >= 0.0    | Float      |

常量：`INT32_MAX = 2^31-1`, `INT64_MAX = 2^63-1`, `JS_MAX_SAFE_INTEGER = 2^53-1`

### 其他类型

| 类型                | 说明                           | SSRF 防护              |
| ------------------- | ------------------------------ | ---------------------- |
| `Url`               | 任意协议 URL                   | 无                     |
| `HttpUrl`           | HTTP/HTTPS                     | 无                     |
| `WebSocketUrl`      | WS/WSS                         | 无                     |
| `SafeHttpUrl`       | HTTP/HTTPS                     | 阻止内网/回环/保留地址 |
| `IPAddress`         | IPv4/IPv6，`is_private()` 方法 | -                      |
| `FilePathType`      | 文件路径（含文件名）           | -                      |
| `DirectoryPathType` | 目录路径（无扩展名）           | -                      |

### PostgreSQL 类型（需额外安装）

```python
from sqlmodel_ext.field_types.dialects.postgresql import (
    Array,          # list[T] -> ARRAY (str/int/dict/UUID/Enum)
    JSON100K,       # dict -> JSONB (max 100K chars, requires orjson)
    JSONList100K,   # list[dict] -> JSONB (max 100K chars, requires orjson)
    NumpyVector,    # ndarray -> pgvector Vector (requires numpy + pgvector)
)

tags: Array[str] = Field(default_factory=list)          # TEXT[]
scores: Array[int] = Field(default_factory=list)        # INTEGER[]
limited: Array[dict, 20] = Field(default_factory=list)  # JSONB[], max 20 items
embedding: NumpyVector[1024, np.float32] = Field(...)   # 1024 维 float32 向量
```

## 常见错误

1. **忘记使用 `save()`/`update()` 的返回值** -- 对象已过期，后续属性访问报错
2. **MRO 顺序错误** -- 字段覆盖失败、缓存不生效、或乐观锁不工作
3. **STI 忘记调用注册函数** -- 子类列未添加到父表，查询时缺少字段
4. **异步访问未加载的关系** -- 触发 `MissingGreenlet` 错误
5. **JTI `SubclassIdMixin` 不在第一位** -- `id` 字段不会被正确覆盖
6. **`jti_subclasses` 不配合 `load`** -- 会抛出 `ValueError`
7. **commit 后直接访问 session 对象属性** -- 对象已过期，需先 refresh/重新查询
8. **`all_fields_optional` 不在 Table 类上使用** -- 它仅用于 DTO/Request 类

